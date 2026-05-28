"""
自选股观察池模块
支持批量监控、每日报告、信号提醒、破位预警
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 加载项目内的 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# Import 兼容
try:
    from .database import (
        add_watchlist_item, remove_watchlist_item,
        get_watchlist, update_watchlist_item
    )
    from .indicators import analyze_stock, get_kline_data
    from .strategies import (
        detect_all_strategies, analyze_kirin_phase,
        StrategyType, get_kline_data as get_strategy_klines
    )
    from .screener import analyze_stock as screener_analyze
except ImportError:
    from database import (
        add_watchlist_item, remove_watchlist_item,
        get_watchlist, update_watchlist_item
    )
    from indicators import analyze_stock, get_kline_data
    from strategies import (
        detect_all_strategies, analyze_kirin_phase,
        StrategyType, get_kline_data as get_strategy_klines
    )
    from screener import analyze_stock as screener_analyze


@dataclass
class WatchAlert:
    """观察警报"""
    ts_code: str
    name: str
    alert_type: str      # B1/B2/BREAK/EXIT/ABNORMAL
    level: str           # INFO/WARNING/CRITICAL
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


def add_watch(ts_code: str, name: str = "", tags: str = "", notes: str = "") -> int:
    """添加自选股"""
    return add_watchlist_item(ts_code, name=name, tags=tags, notes=notes)


def remove_watch(ts_code: str) -> bool:
    """移除自选股"""
    return remove_watchlist_item(ts_code)


def list_watch(tags: str = None) -> List[Dict]:
    """列出自选股"""
    return get_watchlist(tags=tags)


def scan_watchlist(tags: str = None) -> Dict[str, Any]:
    """
    批量扫描自选股池

    Returns:
        {"alerts": [...], "summary": {...}}
    """
    watches = get_watchlist(tags=tags)
    alerts = []
    summary = {
        "total": len(watches),
        "b1_count": 0,
        "b2_count": 0,
        "exit_count": 0,
        "break_count": 0,
        "abnormal_count": 0,
    }

    for w in watches:
        ts_code = w["ts_code"]
        name = w.get("name", ts_code)

        # 指标分析
        try:
            ind = analyze_stock(ts_code, days=60)
        except Exception:
            continue

        # 战法信号
        try:
            signals = detect_all_strategies(ts_code, days=60)
        except Exception:
            signals = []

        # 1. B1/B2 信号提醒
        for s in signals[:3]:
            if s.strategy == StrategyType.B1 and s.action == "BUY":
                alerts.append(WatchAlert(
                    ts_code=ts_code, name=name,
                    alert_type="B1", level="INFO",
                    message=f"出现B1买点 J={s.details.get('j', 0):.1f}",
                    data={"signal": s}
                ))
                summary["b1_count"] += 1
            elif s.strategy == StrategyType.B2 and s.action == "BUY":
                alerts.append(WatchAlert(
                    ts_code=ts_code, name=name,
                    alert_type="B2", level="INFO",
                    message=f"出现B2确认 涨{s.details.get('pct_chg', 0):.1f}%",
                    data={"signal": s}
                ))
                summary["b2_count"] += 1
            elif s.strategy in (StrategyType.S1, StrategyType.S2, StrategyType.S3):
                alerts.append(WatchAlert(
                    ts_code=ts_code, name=name,
                    alert_type="EXIT", level="CRITICAL",
                    message=f"{s.strategy.value}逃顶信号",
                    data={"signal": s}
                ))
                summary["exit_count"] += 1

        # 2. 破位预警（破白线/黄线/BBI）
        if ind.is_dead_cross:
            alerts.append(WatchAlert(
                ts_code=ts_code, name=name,
                alert_type="BREAK", level="WARNING",
                message="白线死叉黄线，趋势走坏",
                data={"white": ind.zg_white, "yellow": ind.dg_yellow}
            ))
            summary["break_count"] += 1
        elif ind.bbi > 0 and hasattr(ind, 'close') and ind.close < ind.bbi * 0.95:
            alerts.append(WatchAlert(
                ts_code=ts_code, name=name,
                alert_type="BREAK", level="WARNING",
                message="跌破BBI",
                data={"bbi": ind.bbi}
            ))
            summary["break_count"] += 1

        # 3. 异动检测（量比 > 3 或涨跌幅 > 5%）
        if ind.vol_ratio > 3 or (hasattr(ind, 'pct_chg') and abs(ind.pct_chg) > 5):
            alerts.append(WatchAlert(
                ts_code=ts_code, name=name,
                alert_type="ABNORMAL", level="INFO",
                message=f"异动 量比{ind.vol_ratio:.1f}",
                data={"vol_ratio": ind.vol_ratio}
            ))
            summary["abnormal_count"] += 1

    return {
        "alerts": alerts,
        "summary": summary,
    }


def generate_daily_report(tags: str = None) -> str:
    """
    生成每日观察报告（文本格式）
    """
    result = scan_watchlist(tags=tags)
    alerts = result["alerts"]
    summary = result["summary"]

    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"自选股每日观察报告  {today}")
    lines.append(f"{'='*60}")
    lines.append(f"监控总数: {summary['total']}只")
    lines.append(f"B1信号: {summary['b1_count']}只 | B2信号: {summary['b2_count']}只")
    lines.append(f"逃顶信号: {summary['exit_count']}只 | 破位预警: {summary['break_count']}只")
    lines.append(f"异动: {summary['abnormal_count']}只")
    lines.append("")

    level_emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}
    type_labels = {
        "B1": "【买点】", "B2": "【买点】",
        "EXIT": "【逃顶】", "BREAK": "【破位】", "ABNORMAL": "【异动】"
    }

    for a in alerts:
        emoji = level_emoji.get(a.level, "")
        label = type_labels.get(a.alert_type, "")
        lines.append(f"{emoji} {label} {a.ts_code} {a.name}")
        lines.append(f"   {a.message}")

    if not alerts:
        lines.append("今日无特别信号，继续观察。")

    lines.append(f"{'='*60}")
    return "\n".join(lines)


# ==================== 命令行工具 ====================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Z哥 自选股观察池")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="添加自选股")
    p_add.add_argument("ts_code", help="股票代码")
    p_add.add_argument("--name", default="", help="股票名称")
    p_add.add_argument("--tags", default="", help="标签，如 波段/短线")
    p_add.add_argument("--notes", default="", help="备注")

    # remove
    p_remove = sub.add_parser("remove", help="移除自选股")
    p_remove.add_argument("ts_code", help="股票代码")

    # list
    p_list = sub.add_parser("list", help="列出自选股")
    p_list.add_argument("--tags", default=None, help="按标签筛选")

    # scan
    p_scan = sub.add_parser("scan", help="扫描自选股池")
    p_scan.add_argument("--tags", default=None, help="按标签筛选")

    # report
    p_report = sub.add_parser("report", help="生成每日报告")
    p_report.add_argument("--tags", default=None, help="按标签筛选")

    args = parser.parse_args()

    if args.command == "add":
        wid = add_watch(args.ts_code, name=args.name, tags=args.tags, notes=args.notes)
        print(f"已添加: {args.ts_code} (ID={wid})")

    elif args.command == "remove":
        if remove_watch(args.ts_code):
            print(f"已移除: {args.ts_code}")
        else:
            print(f"未找到: {args.ts_code}")

    elif args.command == "list":
        watches = list_watch(tags=args.tags)
        print(f"{'='*60}")
        print(f"自选股列表 (共{len(watches)}只)")
        print(f"{'='*60}")
        for w in watches:
            tags_str = f" [{w['tags']}]" if w['tags'] else ""
            print(f"  {w['ts_code']:<12} {w.get('name', ''):<8}{tags_str}")

    elif args.command == "scan":
        result = scan_watchlist(tags=args.tags)
        print(f"扫描完成: {result['summary']}")
        for a in result["alerts"][:20]:
            print(f"  [{a.alert_type}] {a.ts_code} {a.message}")

    elif args.command == "report":
        print(generate_daily_report(tags=args.tags))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
