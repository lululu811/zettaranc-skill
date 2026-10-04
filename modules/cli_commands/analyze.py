"""CLI analyze + score 命令实现。"""

from __future__ import annotations

import logging
import sys

from ._helpers import json_output

logger = logging.getLogger(__name__)


def analyze_core(ts_code: str, days: int = 120) -> dict:
    """
    核心分析逻辑，返回所有分析结果的字典。
    cmd_analyze 和 cmd_score 共用此函数，避免重复计算。
    """
    from modules.indicators import analyze_stock
    from modules.indicators.data_layer import DailyData
    from modules.strategies import detect_all_strategies
    from modules.strategies.core import get_kline_data as _strat_get_klines  # 返回 dict
    from modules.portfolio_diagnosis import diagnose_stock
    from modules.screener import analyze_stock as screener_analyze

    # 1. 指标分析
    result = analyze_stock(ts_code, days=days)

    # 2. 主力阶段（用 strategies.get_kline_data 的 dict 作为 step-2/3 共用源，避免重复取数）
    wave_data = None
    kirin_data = None
    klines_dict: list[dict] | None = None
    daily_klines: list[DailyData] | None = None  # 供 screener 复用
    try:
        from modules.indicators import detect_three_waves, detect_kirin_stage

        klines_dict = _strat_get_klines(ts_code, days=days)
        if klines_dict:
            daily_klines = []
            for i, d in enumerate(klines_dict):
                prev_close = klines_dict[i - 1]["close"] if i > 0 else d["close"]
                daily_klines.append(
                    DailyData(
                        ts_code=d["ts_code"],
                        trade_date=d["trade_date"],
                        open=d["open"],
                        high=d["high"],
                        low=d["low"],
                        close=d["close"],
                        vol=d["vol"],
                        amount=d["amount"],
                        pct_chg=d["pct_chg"],
                        prev_close=prev_close,
                    )
                )
            wave_data = detect_three_waves(daily_klines)
            kirin_data = detect_kirin_stage(daily_klines)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        # 窄化：仅捕获数据解析 / 属性访问 / 索引越界异常，wave/kirin 为可选字段
        logger.warning("[cli] analyze_core 主力阶段 / 麒麟阶段检测失败 %s: %s", ts_code, e)
        wave_data = None
        kirin_data = None

    # 3. 策略信号（复用 step-2 dict；klines_dict 为 None 时 detect_all_strategies 内部按 days 取数）
    signals = detect_all_strategies(ts_code, days=days, klines=klines_dict)

    # 4. 诊断
    diagnosis = diagnose_stock(ts_code, days=days)

    # 5. screener 评分（复用 step-2 已构造的 daily_klines，不再重复拉取）
    score = screener_analyze(ts_code, klines=daily_klines)

    return {
        "ts_code": ts_code,
        "days": days,
        "result": result,
        "wave_data": wave_data,
        "kirin_data": kirin_data,
        "signals": signals,
        "diagnosis": diagnosis,
        "score": score,
    }


def cmd_analyze(args) -> None:
    """分析单只股票（指标 + 主力 + 战法 + 诊断 + 评分）"""
    core = analyze_core(args.ts_code, args.days)

    ts_code = core["ts_code"]
    result = core["result"]
    wave_data = core["wave_data"]
    kirin_data = core["kirin_data"]
    signals = core["signals"]
    diagnosis = core["diagnosis"]
    score = core["score"]

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "ts_code": ts_code,
            "name": getattr(diagnosis, "name", ts_code),
            "price": getattr(diagnosis, "price", 0),
            "indicators": {
                "kdj": {"k": result.k, "d": result.d, "j": result.j},
                "macd": {
                    "dif": result.dif,
                    "dea": result.dea,
                    "hist": result.macd_hist,
                    "veto": getattr(diagnosis, "macd_veto", False),
                },
                "bbi": result.bbi,
                "white_line": getattr(diagnosis, "white_line", 0),
                "yellow_line": getattr(diagnosis, "yellow_line", 0),
                "rsi": {"rsi6": result.rsi6, "rsi12": result.rsi12, "rsi24": result.rsi24},
            },
            "waves": {
                "type": wave_data["wave"] if wave_data else "未知",
                "confidence": wave_data["confidence"] if wave_data else 0,
            },
            "kirin": {
                "phase": kirin_data["stage"] if kirin_data else "未知",
                "confidence": kirin_data["confidence"] if kirin_data else 0,
            },
            "strategies": [
                {
                    "strategy": s.strategy.value,
                    "date": s.trade_date,
                    "confidence": s.confidence,
                    "action": s.action,
                    "description": s.description,
                }
                for s in signals[:10]
            ],
            "diagnosis": {
                "price_position": getattr(diagnosis, "price_position", ""),
                "trend_status": getattr(diagnosis, "trend_status", ""),
                "sell_score": getattr(diagnosis, "sell_score", 0),
                "sell_score_desc": getattr(diagnosis, "sell_score_desc", ""),
                "kirin_phase": getattr(diagnosis, "kirin_phase", ""),
                "bull_rope": getattr(diagnosis, "bull_rope_status", ""),
                "sandglass_score": getattr(diagnosis, "sandglass_score", 0),
                "is_centipede": getattr(diagnosis, "is_centipede", False),
                "risk_level": getattr(diagnosis, "risk_level", ""),
                "recommendation": getattr(diagnosis, "recommendation", ""),
            },
            "score": {
                "total": score.score,
                "b1_score": score.b1_score,
                "trend_score": score.trend_score,
                "volume_score": score.volume_score,
                "risk_score": score.risk_score,
                "rating": score.rating,
                "reasons": score.reasons,
                "warnings": score.warnings,
            },
        }
        json_output(json_result)
        return

    # ── 人类可读输出（保持原样） ──
    print(f"\n{'=' * 60}")
    print(f"股票分析: {ts_code}")
    print(f"{'=' * 60}")

    print("\n【技术指标】")
    print(f"  日期: {result.trade_date}")
    print(f"  KDJ:  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}")
    print(f"  MACD: DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}")
    print(f"  BBI:  {result.bbi:.2f}")
    print(f"  均线: MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}")
    print(f"  RSI:  {result.rsi6:.2f}/{result.rsi12:.2f}/{result.rsi24:.2f}")
    print(f"  砖型图: {result.brick_trend}({result.brick_count}块)  值={result.brick_value:.2f}")

    print("\n【主力阶段】")
    if wave_data:
        print(f"  三波理论: {wave_data['wave']} (conf={wave_data['confidence']}) → {wave_data['b1_suggestion']}")
        if wave_data["stats"]:
            s = wave_data["stats"]
            print(f"    低点→当前: {s['low_price']:.1f}→{s['high_price']:.1f} 涨幅{s['gain_pct']:.1f}%")
            print(f"    涨停{s['limit_up_count']}次 阳线占比{s['red_ratio'] * 100:.0f}% 日均{s['avg_daily_gain']:.2f}%")
    if kirin_data:
        print(f"  麒麟会: {kirin_data['stage']} (conf={kirin_data['confidence']}) → {kirin_data['operation']}")
        if kirin_data["sub_type"] != "未知":
            print(f"    子类型: {kirin_data['sub_type']}")
        if kirin_data.get("scores"):
            sc = kirin_data["scores"]
            print(f"    评分: 吸{sc['xishou']} 拉{sc['lasheng']} 派{sc['paifa']} 落{sc['luoluo']}")
    if not wave_data and not kirin_data:
        print("  无 K 线数据，跳过主力阶段分析")

    print("\n【战法信号】")
    if not signals:
        print("  无信号")
    else:
        critical = [s for s in signals if s.priority.value == 3]
        opportunity = [s for s in signals if s.priority.value == 2]
        observe = [s for s in signals if s.priority.value == 1]

        if critical:
            print(f"  🔴 紧急 ({len(critical)}个):")
            for s in critical[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")
        if opportunity:
            print(f"  🟢 机会 ({len(opportunity)}个):")
            for s in opportunity[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")
        if observe:
            print(f"  ⚪ 观察 ({len(observe)}个):")
            for s in observe[:3]:
                print(f"     {s.trade_date} {s.strategy.value}: {s.description}")

    print("\n【综合评分】")
    print(f"  总分: {score.score:.1f}  {score.rating}")
    print(
        f"  B1评分: {score.b1_score:.1f}  趋势: {score.trend_score:.1f}  量价: {score.volume_score:.1f}  风险: {score.risk_score:.1f}"
    )
    if score.reasons:
        print(f"  理由: {', '.join(score.reasons[:5])}")
    if score.warnings:
        print(f"  警告: {', '.join(score.warnings[:3])}")

    print("\n【持仓诊断】")
    from modules.portfolio_diagnosis import format_report

    print(format_report(diagnosis))


def cmd_score(args) -> None:
    """单只股票综合评分（复用 analyze_core，不重复计算）"""
    from modules.screener import format_stock_score

    if not args.ts_code:
        print("请指定股票代码: zt score <ts_code>")
        sys.exit(1)

    core = analyze_core(args.ts_code, days=60)
    score = core["score"]

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "ts_code": score.ts_code,
            "name": score.name,
            "score": score.score,
            "b1_score": score.b1_score,
            "trend_score": score.trend_score,
            "volume_score": score.volume_score,
            "risk_score": score.risk_score,
            "rating": score.rating,
            "reasons": score.reasons,
            "warnings": score.warnings,
        }
        json_output(json_result)
        return

    # ── 人类可读输出 ──
    print(format_stock_score(score))
