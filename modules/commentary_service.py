#!/usr/bin/env python3
"""
模块说明：Z哥点评服务（v4.3+ 状态：仅 API 消费；CLI 无 caller）。
当前 caller：api/routes/commentary.py；simulator.narrator 借鉴模式但独立实现。
Z哥点评服务

基于 SKILL.md 和知识库，调用 LLM 生成 Z哥风格的股票分析点评。
"""

import os
import re
import sqlite3
import time
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 缓存 ──

_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = int(os.getenv("COMMENTARY_CACHE_TTL", "3600"))
_CACHE_MAX = 100

# ── SKILL.md 精简缓存 ──

_skill_cache: str | None = None
_skill_mtime: float = 0

# ── 知识库路径 ──

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
_SKILL_PATH = Path(__file__).parent.parent / "SKILL.md"


def _load_skill_sections() -> str:
    """从 SKILL.md 提取点评相关的关键章节"""
    global _skill_cache, _skill_mtime

    if not _SKILL_PATH.exists():
        return ""

    mtime = _SKILL_PATH.stat().st_mtime
    if _skill_cache and mtime == _skill_mtime:
        return _skill_cache

    text = _SKILL_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")

    # 需要提取的章节（header → 结束条件）
    target_sections = [
        "## 角色扮演规则（最重要）",
        "## 身份卡",
        "## 表达 DNA",
        "## 决策启发式",
        "## 价值观与反模式",
        "## 诚实边界",
    ]

    extracted: list[str] = []
    in_section = False
    section_depth = 0

    for line in lines:
        # 检测二级标题
        if line.startswith("## "):
            header = line.strip()
            if header in target_sections:
                in_section = True
                section_depth = 2
                extracted.append(f"\n{header}\n")
                continue
            elif in_section and section_depth == 2:
                # 遇到下一个二级标题，结束当前章节
                in_section = False

        # 检测三级标题（在决策启发式内部需要保留子章节）
        if in_section and line.startswith("### "):
            extracted.append(f"\n{line}\n")
            continue

        if in_section:
            extracted.append(line)

    _skill_cache = "\n".join(extracted).strip()
    _skill_mtime = mtime
    return _skill_cache


def _load_knowledge_snippets(analysis: dict[str, Any]) -> str:
    """根据股票状态条件注入相关知识片段"""
    indicators = analysis.get("indicators", {})
    diagnosis = analysis.get("diagnosis", {})
    signals = analysis.get("signals", [])

    snippets: list[str] = []
    max_bytes = 3000

    def _read_section(filepath: str, section_header: str) -> str:
        path = _KNOWLEDGE_DIR / filepath
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        in_section = False
        result: list[str] = []
        for line in lines:
            if line.strip() == section_header or line.strip().startswith(f"### {section_header}"):
                in_section = True
                result.append(line)
                continue
            if in_section:
                if line.startswith("## ") or (line.startswith("### ") and section_header not in line):
                    break
                result.append(line)
        return "\n".join(result).strip()

    macd = indicators.get("macd", {})
    if macd.get("veto"):
        s = _read_section("indicators.md", "MACD")
        if s:
            snippets.append(f"【MACD 规则】\n{s[:800]}")

    if macd.get("top_divergence") or macd.get("bottom_divergence"):
        s = _read_section("indicators.md", "背离")
        if s:
            snippets.append(f"【背离规则】\n{s[:600]}")

    sell_score = diagnosis.get("sell_score", 0)
    if sell_score >= 3:
        s = _read_section("sell-discipline.md", "防卖飞")
        if s:
            snippets.append(f"【防卖飞规则】\n{s[:600]}")

    kirin_phase = diagnosis.get("kirin_phase", "")
    if kirin_phase in ("派发", "回落"):
        s = _read_section("indicators.md", "麒麟会")
        if s:
            snippets.append(f"【麒麟会规则】\n{s[:600]}")

    has_sell_signal = any(s.get("action") == "SELL" for s in signals[:10])
    if has_sell_signal:
        s = _read_section("exit-strategies.md", "S1")
        if s:
            snippets.append(f"【逃顶规则】\n{s[:600]}")

    signal = indicators.get("signal", "")
    if signal in ("B1", "B2"):
        s = _read_section("trading-core.md", "B1")
        if s:
            snippets.append(f"【B1 买点规则】\n{s[:600]}")

    brick = indicators.get("brick", {})
    if brick.get("trend") == "FANBAO" or brick.get("is_fanbao"):
        s = _read_section("indicators.md", "砖形图")
        if s:
            snippets.append(f"【砖形图规则】\n{s[:600]}")

    # 始终注入信号字典中的解读提示
    s = _read_section("signal_dictionary.md", "KDJ")
    if s:
        snippets.append(f"【KDJ 解读】\n{s[:400]}")

    # 合并并限制总大小
    combined = "\n\n".join(snippets)
    if len(combined.encode("utf-8")) > max_bytes:
        combined = combined[:max_bytes] + "\n...(截断)"

    return combined


def _build_user_prompt(analysis: dict[str, Any]) -> str:
    """将结构化分析数据格式化为可读摘要"""
    ts_code = analysis.get("ts_code", "")
    name = analysis.get("name", "")
    price = analysis.get("price", 0)
    pct_chg = analysis.get("pct_chg", 0)
    trade_date = analysis.get("trade_date", "")

    indicators = analysis.get("indicators", {})
    score = analysis.get("score", {})
    diagnosis = analysis.get("diagnosis", {})
    waves = analysis.get("waves")
    signals = analysis.get("signals", [])

    kdj = indicators.get("kdj", {})
    macd = indicators.get("macd", {})
    ma = indicators.get("ma", {})
    bollinger = indicators.get("bollinger", {})
    rsi = indicators.get("rsi", {})
    double_line = indicators.get("double_line", {})
    brick = indicators.get("brick", {})
    dmi = indicators.get("dmi", {})

    # 构建指标快照
    lines = [
        "请分析以下股票的最新量化数据，用 Z哥的风格给出点评：",
        "",
        f"【基本信息】{ts_code} {name} | 收盘 ¥{price} ({pct_chg:+.2f}%) | 日期 {trade_date}",
        "",
        "【技术指标快照】",
        f"- KDJ: K={kdj.get('k', 0):.2f} D={kdj.get('d', 0):.2f} J={kdj.get('j', 0):.2f}",
        f"- MACD: DIF={macd.get('dif', 0):.4f} DEA={macd.get('dea', 0):.4f} 柱={macd.get('hist', 0):.4f}",
    ]

    macd_flags = []
    if macd.get("veto"):
        macd_flags.append("一票否决")
    if macd.get("gold_cross"):
        macd_flags.append("金叉")
    if macd.get("dead_cross"):
        macd_flags.append("死叉")
    if macd.get("top_divergence"):
        macd_flags.append("顶背离")
    if macd.get("bottom_divergence"):
        macd_flags.append("底背离")
    if macd_flags:
        lines[-1] += f" | {' / '.join(macd_flags)}"

    lines.extend(
        [
            f"- 均线: MA5={ma.get('ma5', 0):.2f} MA20={ma.get('ma20', 0):.2f} MA60={ma.get('ma60', 0):.2f}",
            f"- 布林带位置: {bollinger.get('position', 0):.1f}%",
            f"- RSI: RSI6={rsi.get('rsi6', 0):.2f} RSI12={rsi.get('rsi12', 0):.2f} RSI24={rsi.get('rsi24', 0):.2f}",
            f"- 量比: {indicators.get('vol_ratio', 0):.2f}",
            f"- 双线: 白线={double_line.get('white', 0):.2f} 黄线={double_line.get('yellow', 0):.2f}",
        ]
    )

    dl_flags = []
    if double_line.get("is_gold_cross"):
        dl_flags.append("金叉")
    if double_line.get("is_dead_cross"):
        dl_flags.append("死叉")
    if dl_flags:
        lines[-1] += f" | {' / '.join(dl_flags)}"

    lines.extend(
        [
            f"- 砖形图: {brick.get('trend', 'N/A')} ({brick.get('count', 0)}块)",
            f"- DMI: +DI={dmi.get('plus', 0):.2f} -DI={dmi.get('minus', 0):.2f} ADX={dmi.get('adx', 0):.2f}",
            f"- 交易信号: {indicators.get('signal', 'N/A')}",
            "",
            f"【综合评分】{score.get('total', 0):.1f}分 ({score.get('rating', '')})",
            f"- B1={score.get('b1_score', 0)} 趋势={score.get('trend_score', 0)} 量价={score.get('volume_score', 0)} 风险={score.get('risk_score', 0)}",
        ]
    )

    reasons = score.get("reasons", [])
    if reasons:
        lines.append(f"- 理由: {'; '.join(reasons[:4])}")
    warnings = score.get("warnings", [])
    if warnings:
        lines.append(f"- 警告: {'; '.join(warnings[:4])}")

    lines.extend(
        [
            "",
            "【诊断结果】",
            f"- 风险等级: {diagnosis.get('risk_level', 'N/A')}",
            f"- 趋势: {diagnosis.get('trend_status', 'N/A')}",
            f"- 价格位置: {diagnosis.get('price_position', 'N/A')}",
            f"- 防卖飞: {diagnosis.get('sell_score', 0)}/5 {diagnosis.get('sell_score_desc', '')}",
            f"- 麒麟会: {diagnosis.get('kirin_phase', 'N/A')}",
            f"- 牛绳: {diagnosis.get('bull_rope', 'N/A')}",
        ]
    )

    if waves:
        lines.append(f"- 三波: {waves.get('wave', 'N/A')} (置信度 {waves.get('confidence', 0) * 100:.0f}%)")

    # 战法信号（最近 5 个）
    recent_signals = signals[:5]
    if recent_signals:
        lines.append("")
        lines.append("【最近战法信号】")
        for s in recent_signals:
            lines.append(
                f"- {s.get('strategy', '')} @ {s.get('date', '')} | {s.get('action', '')} | {s.get('description', '')[:60]}"
            )

    # 输出格式指令
    lines.extend(
        [
            "",
            "请按以下结构输出点评（控制在 500-800 字）：",
            "",
            "1. **开盘定性**（1-2句话概括当前状态）",
            "2. **技术面解读**（指标之间的共振/矛盾关系，不是逐个念数字）",
            "3. **战法信号**（当前信号意味着什么）",
            "4. **操作建议**（具体的进场/止损/止盈规则，不要含糊其辞）",
            "5. **Z哥金句**（一句收尾，要有你的风格）",
            "",
            "注意：",
            "- 不要逐个指标念数据，要说指标之间的关系",
            "- 不要说「建议关注」这种废话，给具体的操作规则",
            "- 用你的风格说话，不要像AI",
            "- 不要使用 markdown 标题（#），用加粗（**）标注小标题即可",
        ]
    )

    return "\n".join(lines)


def _get_cache_key(analysis: dict[str, Any]) -> str:
    return f"{analysis.get('ts_code', '')}:{analysis.get('trade_date', '')}"


def generate_commentary(analysis: dict[str, Any]) -> dict[str, Any]:
    """
    生成 Z哥点评

    Returns:
        { ts_code, trade_date, commentary_text, generated_at, model_used, cached }
    """
    cache_key = _get_cache_key(analysis)

    # 检查缓存
    if cache_key in _cache:
        text, ts = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return {
                "ts_code": analysis.get("ts_code", ""),
                "trade_date": analysis.get("trade_date", ""),
                "commentary_text": text,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                "model_used": os.getenv("LLM_MODEL", "MiniMax-M3"),
                "cached": True,
            }

    # 构建提示词
    system_prompt = _load_skill_sections()
    user_prompt = _build_user_prompt(analysis)

    # 注入知识库
    knowledge = _load_knowledge_snippets(analysis)
    if knowledge:
        user_prompt += f"\n\n【参考知识库】\n{knowledge}"

    # 调用 LLM
    ts_code = analysis.get("ts_code", "")
    model_name = os.getenv("LLM_MODEL", "MiniMax-M3")
    start_ts = time.perf_counter()
    try:
        from modules.llm_providers import MiniMaxProvider

        provider = MiniMaxProvider()
        text = provider.generate(system_prompt, user_prompt, temperature=0.7)
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0

        # 记录 LLM 响应耗时
        try:
            from modules.database import record_llm_response

            record_llm_response(
                ts_code=ts_code,
                model=model_name,
                response_time_ms=elapsed_ms,
                success=True,
            )
        except (sqlite3.Error, KeyError, TypeError, ValueError, OSError) as log_exc:
            # 内层日志写入失败：调用方（外层 LLM 成功路径）通过继续返回 text 自然降级
            logger.warning("记录 LLM 响应日志失败: %s", log_exc)

        # 过滤掉模型思考过程标签

        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    except ValueError as e:
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        try:
            from modules.database import record_llm_response

            record_llm_response(
                ts_code=ts_code,
                model=model_name,
                response_time_ms=elapsed_ms,
                success=False,
                error_message=str(e),
            )
        except (sqlite3.Error, KeyError, TypeError, ValueError, OSError) as log_exc:
            # 内层日志写入失败：调用方（外层 ValueError 路径）已在外层返回错误 dict，自然降级
            logger.warning("记录 LLM 失败日志失败: %s", log_exc)
        return {
            "ts_code": analysis.get("ts_code", ""),
            "trade_date": analysis.get("trade_date", ""),
            "commentary_text": f"[LLM 未配置] {e}",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model_used": "",
            "cached": False,
            "error": "llm_not_configured",
        }
    except (ValueError, KeyError, TypeError, AttributeError, OSError, TimeoutError) as e:
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        try:
            from modules.database import record_llm_response

            record_llm_response(
                ts_code=ts_code,
                model=model_name,
                response_time_ms=elapsed_ms,
                success=False,
                error_message=str(e),
            )
        except (sqlite3.Error, KeyError, TypeError, ValueError, OSError) as log_exc:
            # 内层日志写入失败：调用方（外层失败路径）已在外层返回错误 dict，自然降级
            logger.warning("记录 LLM 失败日志失败: %s", log_exc)
        logger.error("LLM 生成失败: %s", e, exc_info=True)
        return {
            "ts_code": analysis.get("ts_code", ""),
            "trade_date": analysis.get("trade_date", ""),
            "commentary_text": f"[生成失败] {e}",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model_used": os.getenv("LLM_MODEL", ""),
            "cached": False,
            "error": "llm_failed",
        }

    # 写入缓存
    if len(_cache) >= _CACHE_MAX:
        # LRU: 删除最旧的
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
    _cache[cache_key] = (text, time.time())

    return {
        "ts_code": analysis.get("ts_code", ""),
        "trade_date": analysis.get("trade_date", ""),
        "commentary_text": text,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_used": os.getenv("LLM_MODEL", "MiniMax-M3"),
        "cached": False,
    }
