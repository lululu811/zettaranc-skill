"""CLI portfolio 类（watchlist / trade / daily）子命令实现。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ._helpers import json_output, warn

logger = logging.getLogger(__name__)


def cmd_watchlist(args) -> None:
    """自选股管理"""
    from modules.watchlist import (
        add_watch,
        remove_watch,
        list_watch,
        scan_watchlist,
        generate_daily_report,
    )

    action = args.action

    if action == "add":
        tags = args.tags if hasattr(args, "tags") and args.tags else ""
        add_watch(args.ts_code, tags=tags)
        print(f"已添加: {args.ts_code}")

    elif action == "remove":
        remove_watch(args.ts_code)
        print(f"已移除: {args.ts_code}")

    elif action == "list":
        stocks = list_watch()
        print(f"\n自选股列表 ({len(stocks)}只):")
        for s in stocks:
            tags = s.get("tags", "") or "无"
            added = s.get("added_date", s.get("updated_at", "未知"))
            print(f"  {s['ts_code']}  标签:{tags}  添加:{added}")

    elif action == "scan":
        result = scan_watchlist()
        alerts = result.get("alerts", [])
        summary = result.get("summary", {})

        # ── JSON 输出 ──
        if hasattr(args, "json") and args.json:
            # 按 ts_code 聚合 alerts
            stock_map: dict[str, dict] = {}
            for a in alerts:
                if a.ts_code not in stock_map:
                    stock_map[a.ts_code] = {"ts_code": a.ts_code, "name": a.name, "signals": [], "alerts": []}
                stock_map[a.ts_code]["alerts"].append(
                    {
                        "alert_type": a.alert_type,
                        "level": a.level,
                        "message": a.message,
                    }
                )
            json_result = {
                "count": len(stock_map),
                "stocks": list(stock_map.values()),
            }
            json_output(json_result)
            return

        # ── 人类可读输出（保持原样） ──
        print(f"\n扫描自选股 ({summary.get('total', 0)}只):")
        print(
            f"  B1={summary.get('b1_count', 0)}  B2={summary.get('b2_count', 0)}  "
            f"逃顶={summary.get('exit_count', 0)}  破位={summary.get('break_count', 0)}  "
            f"异动={summary.get('abnormal_count', 0)}"
        )
        for a in alerts[:20]:
            print(f"  [{a.level}] {a.ts_code} {a.name}  {a.alert_type}: {a.message}")

    elif action == "report":
        print(generate_daily_report())


def cmd_trade(args) -> None:
    """交易记录管理命令

    子命令：
        add   "口语化交易描述"           解析并保存交易记录
        list  [--json]                   列出最近交易记录
        review [--json]                  构建复盘上下文（给 LLM 的 prompt）
        stats [--json]                   交易统计摘要
    """
    from ._helpers import error

    sub = getattr(args, "trade_sub", None)
    use_json = getattr(args, "json", False)

    if not sub:
        error("请指定交易子命令: add / list / review / stats")

    # ── add: 解析并保存交易 ──
    if sub == "add":
        text = getattr(args, "text", None)
        if not text:
            error('请输入交易描述，如: trade add "4月25号买了100股茅台，1800块"')

        from .trade_parser import TradeParser
        from .trade_manager import TradeManager

        parser = TradeParser()
        result = parser.parse(text)

        if not result.success:
            error(f"解析失败: {result.error_message}")

        data = result.data
        if not data:
            error("解析结果为空")

        # 展示解析结果
        if use_json:
            json_output(
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
            warn(f"缺少必填字段 {missing_required}，无法保存。请补充后重试。")
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
            json_output(trades)
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
            warn("暂无交易记录，请先添加交易")
            return

        trade = trades[0]
        ctx = reviewer.prepare_review_context(trade)
        ctx = reviewer.enrich_with_indicators(ctx)

        if ctx.action == "SELL":
            ctx = reviewer.enrich_with_buy_info(ctx)
        ctx = reviewer.check_if_complete_trade(ctx)

        if use_json:
            json_output(
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
            json_output(stats)
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
        error(f"未知交易子命令: {sub}")


def cmd_daily(args) -> None:
    """每日五步工作流：观察池扫描 → 选股 → 持仓诊断 → 信号汇总 → 日报"""
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

    if use_json:
        json_output(report)
    else:
        _print_daily_report(report, today)


def _daily_step_watchlist(report: dict) -> list:
    """Step 1: 扫描观察池，返回 watchlist 列表供后续步骤使用"""
    from modules.core.errors import ErrorCode

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
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(
            "[cli_commands] 观察池扫描失败 (code=%s): %s",
            ErrorCode.CLI_COMMAND_FAILED.value,
            e,
        )
        warn(f"观察池扫描失败: {e}")
        report["watchlist_scan"] = {"error": str(e)}
        return []


def _daily_step_screener(report: dict) -> None:
    """Step 2: 全市场 B1 选股，取前 10"""
    from modules.core.errors import ErrorCode

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
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(
            "[cli_commands] 全市场选股失败 (code=%s): %s",
            ErrorCode.CLI_COMMAND_FAILED.value,
            e,
        )
        warn(f"全市场选股失败: {e}")
        report["top_picks"] = {"error": str(e)}


def _daily_step_portfolio(report: dict, watches: list) -> None:
    """Step 3: 持仓快速诊断（前 5 只）"""
    from modules.core.errors import ErrorCode

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
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
                logger.warning(
                    "[cli_commands] 单股诊断失败 (ts=%s, code=%s): %s",
                    code,
                    ErrorCode.CLI_COMMAND_FAILED.value,
                    e,
                )
                portfolio_status.append({"ts_code": code, "error": str(e)})
        report["portfolio_status"] = portfolio_status
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning(
            "[cli_commands] 持仓检查失败 (code=%s): %s",
            ErrorCode.CLI_COMMAND_FAILED.value,
            e,
        )
        warn(f"持仓检查失败: {e}")
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
