#!/usr/bin/env python3
"""
CLI 扩展命令模块（待集成到 cli.py）

提供三个新命令：
  - backtest  : 少妇战法 / 多策略融合 / 组合回测（支持 JSON 输出）
  - trade     : 交易记录的增删查改 + 复盘
  - daily     : 每日五步工作流（观察池 + 选股 + 持仓检查 + 信号汇总 + 报告）

用法示例：
    python -m modules.cli_commands backtest shaofu 600487.SH --days 250 --json
    python -m modules.cli_commands trade add "4月25号买了100股茅台，1800块"
    python -m modules.cli_commands daily --json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any, NoReturn

from modules.core.paths import REPORTS_DIR

logger = logging.getLogger(__name__)


# ==================== 工具函数 ====================


def _json_output(data: Any) -> None:
    """将数据序列化为 JSON 并打印到 stdout"""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _error(msg: str) -> NoReturn:
    """打印错误信息到 stderr 并退出"""
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(1)


def _warn(msg: str) -> None:
    """打印警告信息到 stderr"""
    print(f"警告: {msg}", file=sys.stderr)


# ==================== 1. cmd_backtest ====================


def _shaofu_result_to_dict(result: Any) -> dict:
    """
    将 ShaofuBacktestResult 转换为可序列化的字典

    输出格式与需求文档一致：
    {
        "ts_code", "total_trades", "win_count", "win_rate",
        "avg_pnl", "max_win", "max_loss", "profit_factor",
        "total_return", "max_drawdown", "sharpe_ratio",
        "avg_holding_days", "trades": [...]
    }
    """
    trades = []
    for t in result.trades:
        trades.append(
            {
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "pnl_pct": round(t.pnl_pct * 100, 2),  # 转为百分比数值
                "holding_days": t.holding_days,
            }
        )

    return {
        "ts_code": result.ts_code,
        "total_trades": result.total_trades,
        "win_count": result.win_count,
        "win_rate": round(result.win_rate, 3),
        "avg_pnl": round(result.avg_pnl * 100, 2),
        "max_win": round(result.max_win * 100, 2),
        "max_loss": round(result.max_loss * 100, 2),
        "profit_factor": round(result.profit_factor, 2),
        "total_return": round(result.total_return * 100, 2),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "avg_holding_days": round(result.avg_holding_days, 1),
        "trades": trades,
    }


def _portfolio_result_to_dict(result: Any) -> dict:
    """
    将 PortfolioBacktestResult 转换为可序列化的字典

    包含资金曲线摘要（不输出完整 equity_curve 以控制体积）
    """
    trades = []
    for t in result.trades:
        trades.append(
            {
                "ts_code": t.ts_code,
                "entry_date": t.entry_date,
                "entry_price": round(t.entry_price, 2),
                "exit_date": t.exit_date,
                "exit_price": round(t.exit_price, 2) if t.exit_price else None,
                "exit_reason": t.exit_reason,
                "pnl_pct": round(t.pnl_pct * 100, 2),
            }
        )

    return {
        "initial_capital": result.initial_capital,
        "final_value": round(result.final_value, 2),
        "total_return": round(result.total_return * 100, 2),
        "annualized_return": round(result.annualized_return * 100, 2),
        "sharpe_ratio": round(result.sharpe_ratio, 2),
        "max_drawdown": round(result.max_drawdown * 100, 2),
        "win_rate": round(result.win_rate, 3),
        "profit_factor": round(result.profit_factor, 2),
        "total_trades": result.total_trades,
        "trades": trades,
    }


def _shaofu_portfolio_to_dict(result: dict) -> dict:
    """
    将 backtest_shaofu_portfolio 返回的 dict 清理为可序列化格式

    去掉 results 中不可序列化的对象，只保留摘要
    """
    per_stock = []
    for r in result.get("results", []):
        per_stock.append(_shaofu_result_to_dict(r))

    return {
        "per_stock": per_stock,
        "total_return": round(result.get("total_return", 0) * 100, 2),
        "total_trades": result.get("total_trades", 0),
        "overall_win_rate": round(result.get("overall_win_rate", 0), 3),
        "max_drawdown": round(result.get("max_drawdown", 0) * 100, 2),
        "sharpe_ratio": round(result.get("sharpe_ratio", 0), 2),
    }


def _print_shaofu_summary(ts_code: str, dict_result: dict) -> None:
    """Rust 路径的 shaofu 回测结果 → 人类可读摘要（与 Python summary_text 等价）。"""
    print(f"\n{'=' * 60}")
    print(f"回测结果: {ts_code}  [Rust 路径]")
    print(f"{'=' * 60}")
    print(f"总交易次数: {dict_result['total_trades']}")
    print(f"盈利次数:   {dict_result['win_count']}")
    print(f"胜率:       {dict_result['win_rate']:.1%}")
    print(f"盈亏比:     {dict_result['profit_factor']:.2f}")
    print(f"最大回撤:   {dict_result['max_drawdown']:.2f}%")
    print(f"总收益率:   {dict_result['total_return']:+.2f}%")
    print(f"夏普比率:   {dict_result['sharpe_ratio']:.2f}")
    print(f"平均持仓:   {dict_result['avg_holding_days']:.1f}天")
    print(f"{'=' * 60}")
    last_trades = dict_result.get("trades", [])[-5:]
    if last_trades:
        print("最近5笔交易:")
        for t in last_trades:
            status = "[+]" if t.get("pnl_pct", 0) > 0 else "[-]"
            print(
                f"  {status} {t.get('entry_date', '?')}→{t.get('exit_date') or '持有中'} "
                f"{t.get('pnl_pct', 0):+.2f}% ({t.get('exit_reason', '')})"
            )


def cmd_backtest(args) -> None:
    """
    回测命令

    子命令：
        shaofu   <ts_code>  [--days N] [--json]          少妇战法单股回测
        multi    <ts_code>  [--days N] [--json]          多策略融合回测
        portfolio <c1,c2,..> [--days N] [--json]         组合回测

    示例：
        zt backtest shaofu 600487.SH --days 250 --json
        zt backtest multi 600487.SH --strategy b1,b2 --days 120 --json
        zt backtest portfolio 600487.SH,601318.SH --days 120 --json
    """
    sub = getattr(args, "backtest_sub", None)
    use_json = getattr(args, "json", False)
    days = getattr(args, "days", 250)

    if not sub:
        _error("请指定回测子命令: shaofu / multi / portfolio")

    ts_code = getattr(args, "ts_code", None)

    # ── shaofu: 少妇战法单股回测 ──
    if sub == "shaofu":
        if not ts_code:
            _error("请指定股票代码，如: backtest shaofu 600487.SH")

        # Rust 路径：bridge 内 silent fallback；ZETTARANC_BACKTEST_IMPL=python 时
        # compute_func 返回 None 直接走 Python 分支。
        from modules.backtest._rust_bridge import bridge_shaofu_single

        dict_result = bridge_shaofu_single(ts_code, days=days)
        # bridge_shaofu_single 内部：
        #   - Rust 可用：调 _core_compute.run_single_strategy_backtest_py，
        #                schema 映射后返回 CLI dict
        #   - Rust 不可用 / 失败：fallback 到 Python backtest_shaofu_single，
        #                        返回 _shaofu_result_to_dict(ShaofuBacktestResult)
        #   - ZETTARANC_BACKTEST_IMPL=python：compute_func 返回 None 直接走 Python

        if dict_result.get("total_trades", 0) == 0:
            _warn(
                f"{ts_code} 在 {days} 天内无交易记录（数据不足或无信号触发）"
            )
        if use_json:
            _json_output(dict_result)
        else:
            _print_shaofu_summary(ts_code, dict_result)
        return

    # ── multi: 多策略融合回测 ──
    elif sub == "multi":
        if not ts_code:
            _error("请指定股票代码，如: backtest multi 600487.SH")

        from .backtest import backtest_multi_strategy

        # --strategy 参数暂不传给底层（底层用全部策略融合）
        # 未来可扩展为按策略过滤
        result_multi = backtest_multi_strategy(ts_code, days=days)

        if result_multi.total_trades == 0:
            _warn(f"{ts_code} 在 {days} 天内无交易记录")

        if use_json:
            _json_output(_portfolio_result_to_dict(result_multi))
        else:
            print(result_multi.summary())

    # ── portfolio: 组合回测 ──
    elif sub == "portfolio":
        codes_str = getattr(args, "codes", None)
        if not codes_str:
            _error("请指定股票代码列表（逗号分隔），如: backtest portfolio 600487.SH,601318.SH")

        ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]
        if not ts_codes:
            _error("股票代码列表为空")

        # 单股票时走少妇单股回测（也走 bridge，Rust 优先），多股票走少妇组合回测
        if len(ts_codes) == 1:
            from modules.backtest._rust_bridge import bridge_shaofu_single

            dict_single = bridge_shaofu_single(ts_codes[0], days=days)
            if dict_single.get("total_trades", 0) == 0:
                _warn(
                    f"{ts_codes[0]} 在 {days} 天内无交易记录（数据不足或无信号触发）"
                )
            if use_json:
                _json_output(dict_single)
            else:
                _print_shaofu_summary(ts_codes[0], dict_single)
        else:
            from .backtest_six_step import backtest_shaofu_portfolio

            result_port = backtest_shaofu_portfolio(ts_codes, days=days)
            if use_json:
                _json_output(_shaofu_portfolio_to_dict(result_port))
            else:
                print(f"{'=' * 60}")
                print("少妇战法组合回测结果")
                print(f"{'=' * 60}")
                print(f"股票数量:     {len(ts_codes)}")
                print(f"总交易次数:   {result_port['total_trades']}")
                print(f"整体胜率:     {result_port['overall_win_rate']:.1%}")
                print(f"累计收益:     {result_port['total_return']:+.2%}")
                print(f"最大回撤:     {result_port['max_drawdown']:.2%}")
                print(f"夏普比率:     {result_port['sharpe_ratio']:.2f}")
                print(f"{'=' * 60}")
                for r in result_port.get("results", []):
                    status = "有交易" if r.total_trades > 0 else "无交易"
                    print(f"  {r.ts_code}: {status} {r.total_trades}笔 胜率{r.win_rate:.0%} 收益{r.total_return:+.2%}")

    else:
        _error(f"未知回测子命令: {sub}")


# ==================== 2. cmd_trade ====================


def cmd_trade(args) -> None:
    """
    交易记录管理命令

    子命令：
        add   "口语化交易描述"           解析并保存交易记录
        list  [--json]                   列出最近交易记录
        review [--json]                  构建复盘上下文（给 LLM 的 prompt）
        stats [--json]                   交易统计摘要

    示例：
        zt trade add "4月25号买了100股茅台，1800块"
        zt trade list --json
        zt trade review --json
        zt trade stats --json
    """
    sub = getattr(args, "trade_sub", None)
    use_json = getattr(args, "json", False)

    if not sub:
        _error("请指定交易子命令: add / list / review / stats")

    # ── add: 解析并保存交易 ──
    if sub == "add":
        text = getattr(args, "text", None)
        if not text:
            _error('请输入交易描述，如: trade add "4月25号买了100股茅台，1800块"')

        from .trade_parser import TradeParser
        from .trade_manager import TradeManager

        parser = TradeParser()
        result = parser.parse(text)

        if not result.success:
            _error(f"解析失败: {result.error_message}")

        data = result.data
        if not data:
            _error("解析结果为空")

        # 展示解析结果
        if use_json:
            _json_output(
                {
                    "parsed": data,
                    "confidence": result.confidence,
                    "missing_fields": result.missing_fields,
                }
            )
            return

        # 文本模式：显示解析确认
        confirm_msg = parser.generate_confirm_message(data)
        print(confirm_msg)
        print(f"  置信度: {result.confidence:.0%}")

        if result.missing_fields:
            print(f"  缺失字段: {', '.join(result.missing_fields)}")

        # 检查必填字段
        required = ["ts_code", "action", "price", "quantity"]
        missing_required = [f for f in required if f not in data or not data.get(f)]
        if missing_required:
            _warn(f"缺少必填字段 {missing_required}，无法保存。请补充后重试。")
            return

        # 自动补充金额
        if "amount" not in data and data.get("price") and data.get("quantity"):
            data["amount"] = round(float(data["price"]) * int(data["quantity"]), 2)

        # 保存到数据库
        manager = TradeManager()
        trade_id = manager.add_trade(data)
        print(f"\n已保存交易记录 (ID={trade_id})")

    # ── list: 列出交易记录 ──
    elif sub == "list":
        from .trade_manager import TradeManager

        manager = TradeManager()
        limit = getattr(args, "limit", 20)
        trades = manager.get_recent_trades(limit=limit)

        if use_json:
            _json_output(trades)
        else:
            if not trades:
                print("暂无交易记录")
                return
            print(f"\n最近 {len(trades)} 条交易记录:")
            print(f"{'=' * 70}")
            for t in trades:
                action_text = "买入" if t.get("action") == "BUY" else "卖出"
                print(
                    f"  [{t.get('id', '?'):>3}] {t.get('trade_date', '?')}"
                    f"  {action_text}  {t.get('ts_code', '?')}"
                    f"  {t.get('quantity', 0)}股 @ {t.get('price', 0)}元"
                )
            print(f"{'=' * 70}")

    # ── review: 构建复盘上下文 ──
    elif sub == "review":
        from .trade_manager import TradeManager
        from .trade_reviewer import TradeReviewer

        manager = TradeManager()
        reviewer = TradeReviewer()

        # 获取最近一笔交易
        trades = manager.get_recent_trades(limit=1)
        if not trades:
            _warn("暂无交易记录，请先添加交易")
            return

        trade = trades[0]
        ctx = reviewer.prepare_review_context(trade)
        ctx = reviewer.enrich_with_indicators(ctx)

        if ctx.action == "SELL":
            ctx = reviewer.enrich_with_buy_info(ctx)
        ctx = reviewer.check_if_complete_trade(ctx)

        if use_json:
            _json_output(
                {
                    "ts_code": ctx.ts_code,
                    "name": ctx.name,
                    "trade_date": ctx.trade_date,
                    "action": ctx.action,
                    "price": ctx.price,
                    "quantity": ctx.quantity,
                    "amount": ctx.amount,
                    "reason": ctx.reason,
                    "avg_cost": ctx.avg_cost,
                    "profit_pct": ctx.profit_pct,
                    "holding_days": ctx.holding_days,
                    "signal_type": ctx.signal_type,
                    "is_complete_trade": ctx.is_complete_trade,
                    "indicators": ctx.indicators,
                    "prompt": ctx.get_full_prompt(),
                }
            )
        else:
            print(ctx.to_llm_prompt())
            print()
            print("--- Z哥点评 Prompt ---")
            print(ctx.get_full_prompt())

    # ── stats: 交易统计 ──
    elif sub == "stats":
        from .trade_manager import TradeManager

        manager = TradeManager()
        summary = manager.get_summary()
        pnl = manager.calculate_pnl()

        stats = {
            "summary": summary,
            "pnl": pnl,
        }

        if use_json:
            _json_output(stats)
        else:
            print(f"\n{'=' * 60}")
            print("交易统计摘要")
            print(f"{'=' * 60}")
            print(f"  买入总额:   {pnl.get('buy_total', 0):,.2f} 元")
            print(f"  卖出总额:   {pnl.get('sell_total', 0):,.2f} 元")
            print(f"  净投入:     {pnl.get('net_invested', 0):,.2f} 元")
            print(f"  买入股数:   {pnl.get('buy_qty', 0)}")
            print(f"  卖出股数:   {pnl.get('sell_qty', 0)}")
            print(f"  当前持仓:   {pnl.get('current_qty', 0)}")
            print(f"  已实现盈亏: {pnl.get('realized_pnl', 0):,.2f} 元")
            print(f"{'=' * 60}")

    else:
        _error(f"未知交易子命令: {sub}")


# ==================== 3. cmd_daily ====================


def cmd_daily(args) -> None:
    """每日五步工作流：观察池扫描 → 选股 → 持仓诊断 → 信号汇总 → 日报

    拆分为 5 个独立步骤函数，每步独立 try/except，互不阻塞。
    """
    use_json = getattr(args, "json", False)
    today = datetime.now().strftime("%Y-%m-%d")

    report: dict[str, Any] = {
        "date": today,
        "watchlist_scan": [],
        "top_picks": [],
        "portfolio_status": [],
        "signals": [],
        "summary": "",
    }

    watches = _daily_step_watchlist(report)
    _daily_step_screener(report)
    _daily_step_portfolio(report, watches)
    _daily_step_signals(report)
    _daily_step_summary(report)

    # ── 输出 ──
    if use_json:
        _json_output(report)
    else:
        _print_daily_report(report, today)


def _daily_step_watchlist(report: dict) -> list:
    """Step 1: 扫描观察池，返回 watchlist 列表供后续步骤使用"""
    try:
        from .watchlist import scan_watchlist, list_watch

        watches = list_watch()
        if not watches:
            report["watchlist_scan"] = {"total": 0, "alerts": []}
            return watches

        scan_result = scan_watchlist()
        alerts = scan_result.get("alerts", [])
        summary = scan_result.get("summary", {})

        watchlist_scan = {
            "total": summary.get("total", 0),
            "b1_count": summary.get("b1_count", 0),
            "b2_count": summary.get("b2_count", 0),
            "exit_count": summary.get("exit_count", 0),
            "break_count": summary.get("break_count", 0),
            "abnormal_count": summary.get("abnormal_count", 0),
            "alerts": [
                {
                    "ts_code": a.ts_code,
                    "name": a.name,
                    "alert_type": a.alert_type,
                    "level": a.level,
                    "message": a.message,
                }
                for a in alerts
            ],
        }
        report["watchlist_scan"] = watchlist_scan

        for a in alerts:
            if a.alert_type in ("B1", "B2", "EXIT"):
                report["signals"].append(
                    {
                        "ts_code": a.ts_code,
                        "name": a.name,
                        "signal": a.alert_type,
                        "message": a.message,
                        "source": "watchlist",
                    }
                )
        return watches
    except Exception as e:
        _warn(f"观察池扫描失败: {e}")
        report["watchlist_scan"] = {"error": str(e)}
        return []


def _daily_step_screener(report: dict) -> None:
    """Step 2: 全市场 B1 选股，取前 10"""
    try:
        from .screener import screen_stocks

        top_picks_raw = screen_stocks(criteria="b1", max_stocks=20)
        top_picks = []
        for s in top_picks_raw[:10]:
            pick = {
                "ts_code": s.ts_code,
                "name": s.name,
                "score": round(s.score, 1),
                "b1_score": round(s.b1_score, 1),
                "trend_score": round(s.trend_score, 1),
                "rating": s.rating,
            }
            top_picks.append(pick)
            if s.b1_score >= 50:
                report["signals"].append(
                    {
                        "ts_code": s.ts_code,
                        "name": s.name,
                        "signal": "B1",
                        "message": f"综合评分 {s.score:.0f}，B1评分 {s.b1_score:.0f}",
                        "source": "screener",
                    }
                )
        report["top_picks"] = top_picks
    except Exception as e:
        _warn(f"全市场选股失败: {e}")
        report["top_picks"] = {"error": str(e)}


def _daily_step_portfolio(report: dict, watches: list) -> None:
    """Step 3: 持仓快速诊断（前 5 只）"""
    try:
        from .portfolio_diagnosis import diagnose_stock

        check_codes: list[str] = []
        wl = report["watchlist_scan"]
        if isinstance(wl, dict):
            for a in wl.get("alerts", [])[:5]:
                if a["ts_code"] not in check_codes:
                    check_codes.append(a["ts_code"])
        if not check_codes and watches:
            check_codes = [w["ts_code"] for w in watches[:5]]

        portfolio_status = []
        for code in check_codes:
            try:
                diag = diagnose_stock(code, days=60)
                portfolio_status.append(
                    {
                        "ts_code": code,
                        "diagnosis": diag[:200] if isinstance(diag, str) else str(diag)[:200],
                    }
                )
            except Exception as e:
                portfolio_status.append({"ts_code": code, "error": str(e)})
        report["portfolio_status"] = portfolio_status
    except Exception as e:
        _warn(f"持仓检查失败: {e}")
        report["portfolio_status"] = {"error": str(e)}


def _daily_step_signals(report: dict) -> None:
    """Step 4: 信号去重"""
    seen: set[tuple] = set()
    unique: list = []
    for sig in report["signals"]:
        key = (sig["ts_code"], sig["signal"])
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    report["signals"] = unique


def _daily_step_summary(report: dict) -> None:
    """Step 5: 生成摘要文本"""
    wl = report["watchlist_scan"]
    is_dict = isinstance(wl, dict)
    b1_count = wl.get("b1_count", 0) if is_dict else 0
    exit_count = wl.get("exit_count", 0) if is_dict else 0
    picks_count = len(report["top_picks"]) if isinstance(report["top_picks"], list) else 0
    sig_count = len(report["signals"])

    parts = [f"今日观察池 {wl.get('total', 0) if is_dict else 0} 只"]
    if b1_count:
        parts.append(f"出现 B1 信号 {b1_count} 只")
    if exit_count:
        parts.append(f"逃顶预警 {exit_count} 只")
    if picks_count:
        parts.append(f"全市场选出 {picks_count} 只潜力股")
    if sig_count:
        parts.append(f"共 {sig_count} 条信号待关注")
    if not any([b1_count, exit_count, picks_count]):
        parts.append("今日无特别信号，继续观察")

    report["summary"] = "，".join(parts) + "。"


def _print_daily_report(report: dict, today: str) -> None:
    """格式化打印每日报告"""
    wl = report["watchlist_scan"]
    print(f"\n{'=' * 60}")
    print(f"Z哥每日工作流报告  {today}")
    print(f"{'=' * 60}")
    print(f"\n{report['summary']}")

    if isinstance(wl, dict) and wl.get("alerts"):
        print(f"\n【观察池信号】({wl.get('total', 0)}只)")
        for a in wl["alerts"][:10]:
            print(f"  [{a['alert_type']}] {a['ts_code']} {a['name']}: {a['message']}")

    if isinstance(report["top_picks"], list) and report["top_picks"]:
        print("\n【B1 潜力股 TOP 10】")
        for i, p in enumerate(report["top_picks"], 1):
            print(
                f"  {i:2}. {p['ts_code']} {p['name']:<8} 评分:{p['score']:5.1f}  B1:{p['b1_score']:5.1f}  {p['rating']}"
            )

    if report["portfolio_status"]:
        print("\n【持仓诊断】")
        for p in report["portfolio_status"]:
            if "error" in p:
                print(f"  {p['ts_code']}: 诊断失败 - {p['error']}")
            else:
                print(f"  {p['ts_code']}: {p['diagnosis']}")

    if report["signals"]:
        print(f"\n【信号汇总】({len(report['signals'])}条)")
        for sig in report["signals"]:
            print(f"  [{sig['signal']}] {sig['ts_code']} {sig['name']}: {sig['message']}")

    print(f"\n{'=' * 60}")


def cmd_monitor(args):
    """自选股监控扫描命令行处理入口"""
    from modules.monitor import run_watchlist_monitor

    use_json = getattr(args, "json", False)
    enable_push = not getattr(args, "no_push", False)
    days = getattr(args, "days", 30)

    # 运行监控扫描
    res = run_watchlist_monitor(sync_days=days, enable_push=enable_push)

    if use_json:
        _json_output(res)
    else:
        # 非 JSON 输出时已经在 run_watchlist_monitor 内部写入了 Markdown 报告，打印简易提示
        print(f"自选股主动扫描监控完成。状态: {res['status']}, 警报总数: {res.get('alerts_count', 0)}")
        print(f"详细警报分析已输出至 {REPORTS_DIR}/monitor_alert.md")


def _simulate_narrate_text(result: Any, wf_payload: dict[str, Any] | None) -> dict[str, Any]:
    """simulate 子命令的 --narrate 适配：单模拟走 narrator；walk-forward 走叙事化摘要。"""
    if result is not None:
        try:
            from .simulator.narrator import generate_simulation_narrative

            return generate_simulation_narrative(result)
        except Exception as exc:
            logger.warning("narrate 失败，使用兜底文案: %s", exc)
            return {
                "simulation_id": "",
                "ts_codes": [],
                "days": 0,
                "narrative_text": f"[narrate 生成失败] {exc}",
                "generated_at": "",
                "model_used": "",
                "cached": False,
                "error": "narrate_failed",
            }

    if wf_payload is not None:
        oos = wf_payload.get("oos_metrics") or {}
        narrative_lines = [
            "【Walk-forward OOS 战绩】",
            f"- 窗口数: {len(wf_payload.get('windows') or [])}",
            f"- 训练/验证窗口: {wf_payload.get('config', {}).get('train_days')}/{wf_payload.get('config', {}).get('test_days')}",
            f"- 目标函数: {wf_payload.get('config', {}).get('objective', 'calmar')}",
            f"- OOS 年化: {oos.get('annualized_return', 0) * 100:+.2f}%",
            f"- OOS 夏普: {oos.get('sharpe_ratio', 0):.2f}",
            f"- OOS Calmar: {oos.get('calmar_ratio', 0):.2f}",
            f"- OOS 最大回撤: {oos.get('max_drawdown', 0) * 100:.2f}%",
            f"- 过拟合比率: {wf_payload.get('overfit_ratio', 1.0):.2f}（接近 1 = 不过拟合）",
            "",
            "（walk-forward 不调 LLM，直接看 OOS 拼接曲线与稳定性）",
        ]
        return {
            "simulation_id": "walk_forward",
            "ts_codes": [],
            "days": wf_payload.get("config", {}).get("train_days", 0)
            + wf_payload.get("config", {}).get("test_days", 0),
            "narrative_text": "\n".join(narrative_lines),
            "generated_at": "",
            "model_used": "",
            "cached": False,
        }

    return {}


def _simulate_print_narrative(narrative: dict[str, Any]) -> None:
    """非 JSON 输出模式：把 narrative 以人类可读形式追加到 stdout。"""
    print("\n" + "=" * 60)
    print("Z哥点评")
    print("=" * 60)
    text = narrative.get("narrative_text") if narrative else ""
    if not text:
        text = narrative.get("error", "点评生成失败") if narrative else "点评生成失败"
    print(text)


def cmd_simulate(args) -> None:
    """
    少女/少妇模拟器 CLI 入口（v0.2）。

    示例：
        zt simulate 600487.SH,601318.SH --days 250 --capital 1000000 --json
        zt simulate --days 120 --max-positions 3 --score 75
        zt simulate 600487.SH --cost-model advanced --slippage dynamic --atr-sizing
        zt simulate 600487.SH --days 250 --narrate --json    # LLM 点评
    """
    from dataclasses import asdict

    from .simulator.simulator import run_simulation, summary_text
    from .simulator import SimulationConfig, CostModel

    use_json = getattr(args, "json", False)
    days = getattr(args, "days", 250)
    codes_str = getattr(args, "codes", None)

    # 成本模型：simple 保持 v0.1 默认（仅佣金），advanced 启用完整成本
    if getattr(args, "cost_model", "simple") == "advanced":
        cost_model = CostModel()
    else:
        cost_model = CostModel(
            commission_rate=0.0003,
            min_commission=0.0,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            apply_stamp_duty_on_sell=False,
        )

    config = SimulationConfig(
        initial_capital=getattr(args, "capital", 1_000_000.0),
        max_positions=getattr(args, "max_positions", 5),
        risk_per_trade=getattr(args, "risk", 0.02),
        position_score_threshold=getattr(args, "score", 70.0),
        signal_min_count=getattr(args, "signals", 2),
        benchmark_code=getattr(args, "benchmark", "000300.SH"),
        cost_model=cost_model,
        use_dynamic_slippage=getattr(args, "slippage", "fixed") == "dynamic",
        use_atr_sizing=getattr(args, "atr_sizing", False),
        max_position_pct=getattr(args, "max_position_pct", 0.20),
        allow_st=not getattr(args, "no_st", False),
        t1_lock=getattr(args, "t1_lock", True),
        strategy_mode=getattr(args, "strategy_mode", "simple"),
        strategy_lookback_days=getattr(args, "strategy_lookback", 5),
        min_resonance_score=getattr(args, "min_resonance_score", 0.35),
    )

    ts_codes = None
    if codes_str:
        ts_codes = [c.strip() for c in codes_str.split(",") if c.strip()]

    # 检查是否启用 walk-forward 参数寻优
    if getattr(args, "walk_forward", False):
        from .simulator.walk_forward import run_walk_forward, WalkForwardConfig
        from .simulator.optimizer_report import summary_text as wf_summary_text, to_dict as wf_to_dict

        wf_config = WalkForwardConfig(
            train_days=getattr(args, "wf_train_days", 120),
            test_days=getattr(args, "wf_test_days", 60),
            objective=getattr(args, "wf_objective", "calmar"),
        )

        wf_result = run_walk_forward(
            ts_codes=ts_codes,
            total_days=days,
            wf_config=wf_config,
            base_config=config,
        )

        if use_json:
            payload = wf_to_dict(wf_result)
            if getattr(args, "narrate", False):
                payload["narrative"] = _simulate_narrate_text(result=None, wf_payload=payload)
            _json_output(payload)
        else:
            print(wf_summary_text(wf_result))
            if getattr(args, "narrate", False):
                _simulate_print_narrative(_simulate_narrate_text(result=None, wf_payload=None))
        return

    result = run_simulation(ts_codes=ts_codes, days=days, config=config)

    metrics_dict = asdict(result.metrics) if result.metrics else None

    if use_json:
        output_dict = {
            "initial_capital": result.initial_capital,
            "final_value": result.final_value,
            "total_return": round(result.total_return * 100, 2),
            "max_drawdown": round(result.max_drawdown * 100, 2),
            "sharpe_ratio": round(result.sharpe_ratio, 2),
            "total_trades": result.total_trades,
            "win_rate": round(result.win_rate, 3),
            "profit_factor": round(result.profit_factor, 2),
            "avg_holding_days": round(result.avg_holding_days, 1),
            "open_positions": len(result.positions),
            "trades": [
                {
                    "ts_code": t.ts_code,
                    "action": t.action,
                    "date": t.date,
                    "price": t.price,
                    "shares": t.shares,
                    "pnl": t.pnl,
                    "pnl_pct": round(t.pnl_pct * 100, 2),
                    "reason": t.reason,
                }
                for t in result.trades
            ],
            "equity_curve_sample": result.equity_curve[:: max(1, len(result.equity_curve) // 30)],
            "metrics": metrics_dict,
            "benchmark_curve_sample": result.benchmark_curve[:: max(1, len(result.benchmark_curve) // 30)],
            "resonance_details": result.resonance_summary,
        }

        if getattr(args, "narrate", False):
            output_dict["narrative"] = _simulate_narrate_text(result=result, wf_payload=None)

        _json_output(output_dict)
    else:
        print(summary_text(result))
        if getattr(args, "narrate", False):
            _simulate_print_narrative(_simulate_narrate_text(result=result, wf_payload=None))


# ==================== 4. cmd_verify_v10（M4 验收 CLI 适配）====================


def cmd_verify_v10(args) -> int:
    """少妇战法 v1.0 验收子命令"""
    from modules.verify.cli import main as verify_main

    # 把 argparse Namespace 转成 main() 接受的 argv 列表
    argv = []
    if args.limit != 50:
        argv.extend(["--limit", str(args.limit)])
    if args.days != 250:
        argv.extend(["--days", str(args.days)])
    if getattr(args, "walk_forward", False):
        argv.append("--walk-forward")
    if getattr(args, "wf_train", 120) != 120:
        argv.extend(["--wf-train", str(args.wf_train)])
    if getattr(args, "wf_test", 60) != 60:
        argv.extend(["--wf-test", str(args.wf_test)])
    if getattr(args, "ts_codes", None):
        argv.extend(["--ts-codes", args.ts_codes])
    if getattr(args, "output", None) and args.output != str(REPORTS_DIR):
        argv.extend(["--output", args.output])
    if getattr(args, "json", False):
        argv.append("--json")
    if getattr(args, "no_markdown", False):
        argv.append("--no-markdown")
    return verify_main(argv)


def add_verify_v10_parser(subparsers) -> None:
    """注册 verify v1.0 验收子命令"""
    p_verify = subparsers.add_parser("verify", help="v1.0 验收")
    p_verify.add_argument("version", choices=["v1.0"], help="验收版本")
    p_verify.add_argument("--limit", type=int, default=50)
    p_verify.add_argument("--days", type=int, default=250)
    p_verify.add_argument("--walk-forward", action="store_true")
    p_verify.add_argument("--wf-train", type=int, default=120)
    p_verify.add_argument("--wf-test", type=int, default=60)
    p_verify.add_argument("--ts-codes", type=str, default=None, help="指定股票列表（逗号分隔）")
    p_verify.add_argument("--output", type=str, default=str(REPORTS_DIR), help="报告输出目录")
    p_verify.add_argument("--json", action="store_true")
    p_verify.add_argument("--no-markdown", action="store_true")
    p_verify.set_defaults(func=cmd_verify_v10)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Z哥量化工具 CLI 扩展命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m modules.cli_commands backtest shaofu 600487.SH --days 250 --json
  python -m modules.cli_commands backtest multi 600487.SH --days 120 --json
  python -m modules.cli_commands backtest portfolio 600487.SH,601318.SH --days 120 --json
  python -m modules.cli_commands trade add "4月25号买了100股茅台，1800块"
  python -m modules.cli_commands trade list --json
  python -m modules.cli_commands trade review --json
  python -m modules.cli_commands trade stats --json
  python -m modules.cli_commands daily --json
  python -m modules.cli_commands simulate 600487.SH --days 250 --json
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令", required=True)

    # ── backtest ──
    p_bt = subparsers.add_parser("backtest", help="回测（shaofu / multi / portfolio）")
    p_bt.add_argument("backtest_sub", choices=["shaofu", "multi", "portfolio"], help="回测类型")
    p_bt.add_argument("ts_code", nargs="?", help="股票代码（shaofu/multi 必填）")
    p_bt.add_argument("codes", nargs="?", help="股票代码列表（portfolio 用，逗号分隔）")
    p_bt.add_argument("--days", type=int, default=250, help="回测天数")
    p_bt.add_argument("--json", action="store_true", help="JSON 输出")
    p_bt.add_argument("--strategy", default=None, help="策略过滤（暂保留）")

    # ── trade ──
    p_tr = subparsers.add_parser("trade", help="交易记录管理（add / list / review / stats）")
    p_tr.add_argument("trade_sub", choices=["add", "list", "review", "stats"], help="操作")
    p_tr.add_argument("text", nargs="?", help="交易描述（add 必填）")
    p_tr.add_argument("--json", action="store_true", help="JSON 输出")
    p_tr.add_argument("--limit", type=int, default=20, help="列出条数（list 用）")

    # ── daily ──
    p_dy = subparsers.add_parser("daily", help="每日工作流")
    p_dy.add_argument("--json", action="store_true", help="JSON 输出")

    # ── simulate ──
    p_sim = subparsers.add_parser("simulate", help="端到端交易模拟回测（择时+选股+仓位+卖出）")
    p_sim.add_argument("codes", nargs="?", help="股票代码，逗号分隔；省略则使用前 500 只")
    p_sim.add_argument("--days", type=int, default=250, help="回测天数")
    p_sim.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    p_sim.add_argument("--max-positions", type=int, default=5, help="最大同时持仓")
    p_sim.add_argument("--risk", type=float, default=0.02, help="单笔风险占净值比例")
    p_sim.add_argument("--score", type=float, default=70.0, help="入选信号最低综合评分")
    p_sim.add_argument("--signals", type=int, default=2, help="最小共振标签数")
    p_sim.add_argument("--benchmark", type=str, default="000300.SH", help="基准指数代码")
    p_sim.add_argument(
        "--cost-model",
        choices=["simple", "advanced"],
        default="simple",
        help="成本模型：simple=仅佣金，advanced=含印花税/过户费",
    )
    p_sim.add_argument("--slippage", choices=["fixed", "dynamic"], default="fixed", help="滑点模型")
    p_sim.add_argument("--atr-sizing", action="store_true", help="启用 ATR 波动率仓位调整")
    p_sim.add_argument("--max-position-pct", type=float, default=0.20, help="单票最大仓位占比")
    p_sim.add_argument("--no-st", action="store_true", help="不允许交易 ST/*ST 股票")
    p_sim.add_argument("--t1-lock", dest="t1_lock", action="store_true", default=True, help="启用 T+1 卖出锁定（默认）")
    p_sim.add_argument("--no-t1-lock", dest="t1_lock", action="store_false", default=True, help="禁用 T+1 卖出锁定")
    # v0.3 新增：战法共振模式参数
    p_sim.add_argument("--strategy-mode", choices=["simple", "resonance"], default="simple", help="选股模式")
    p_sim.add_argument("--strategy-lookback", type=int, default=5, help="战法信号回看交易日数")
    p_sim.add_argument("--min-resonance-score", type=float, default=0.35, help="共振模式最低入选分")
    p_sim.add_argument("--json", action="store_true", help="JSON 输出")

    # ── verify ──
    add_verify_v10_parser(subparsers)

    args = parser.parse_args()

    # 调度
    handlers = {
        "backtest": cmd_backtest,
        "trade": cmd_trade,
        "daily": cmd_daily,
        "simulate": cmd_simulate,
        "verify": cmd_verify_v10,
    }
    handlers[args.command](args)
