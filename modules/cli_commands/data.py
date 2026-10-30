"""CLI 数据/基础设施类（sync / track / self-optimize / monitor / market-timing）子命令。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ._helpers import json_output, warn

logger = logging.getLogger(__name__)


def cmd_sync(args) -> None:
    """数据同步（init / sync / status / stk-factor / index / 0amv）"""
    from datetime import datetime, timedelta

    from modules.data_sync import DataSyncer
    from modules.database import init_database
    from modules.datasource import get_datasource

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    action = args.sync_action

    if action == "init":
        init_database()
        print("数据库初始化完成")

    elif action == "sync":
        # 数据源按统一决议选（与读路径 analyze/screen 走同一套判断），
        # 不再钉死 tushare：默认的 websearch 模式下 tushare 没有数据后端
        # （TushareClient._pro is None），钉死它会让整次同步静默同步 0 行，
        # 却照样打印"同步完成"。
        syncer = DataSyncer()
        if args.ts_code:
            kline_count = syncer.sync_daily_kline(args.ts_code)
            if not args.skip_indicators:
                print(f"正在同步指标缓存: {args.ts_code} ...")
                syncer.sync_indicator_cache(args.ts_code, days=args.days)
            print(f"同步完成：{args.ts_code} K 线 {kline_count} 行")
        else:
            stock_count = syncer.sync_stock_basic()
            kline_counts = syncer.sync_all_daily_kline(days=args.days)
            kline_count = sum(kline_counts.values()) if isinstance(kline_counts, dict) else 0
            if args.indicators and not args.skip_indicators:
                print("正在批量同步指标缓存...")
                syncer.sync_all_indicators()
            print(f"同步完成：股票 {stock_count} 只，K 线 {kline_count} 行")
        print(syncer.get_sync_status())

    elif action == "stk-factor":
        # 技术因子只有 tushare / indevs 提供（hithink 与 a-stock-data 都不支持），
        # 这个命令本身就是"同步 Tushare 官方指标"，因此显式钉死 tushare。
        syncer = DataSyncer(datasource=get_datasource("tushare"))
        if args.ts_code:
            print(f"正在同步 Tushare 官方指标: {args.ts_code} ...")
            start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            count = syncer.sync_stk_factor(args.ts_code, start_date=start_date, end_date=end_date)
            print(f"同步完成，{count} 条")
        else:
            print("正在批量同步 Tushare 官方指标...")
            results = syncer.sync_all_stk_factor(days=args.days)
            success = sum(1 for v in results.values() if v > 0)
            print(f"批量同步完成，成功 {success}/{len(results)}")

    elif action == "index":
        from modules.index_sync import sync_indices_to_duckdb

        duckdb_path = args.duckdb or os.getenv("DUCKDB_PATH", "data/market.duckdb")
        codes = None
        if args.codes:
            codes = [c.strip() for c in args.codes.split(",") if c.strip()]

        print(f"正在通过 hithink 同步指数到 DuckDB: {duckdb_path}")
        result = sync_indices_to_duckdb(
            duckdb_path=duckdb_path,
            index_codes=codes,
            start_date=args.start,
            end_date=args.end,
        )
        print(f"同步完成，共写入 {result['total_rows']} 条")
        for code, info in result["details"].items():
            print(f"  {code}: {info['status']} ({info['rows']} 条)")

    elif action == "0amv":
        from modules.active_market_value import import_0amv_csv_to_duckdb

        duckdb_path = args.duckdb or os.getenv("DUCKDB_PATH", "data/market.duckdb")
        csv_path = args.csv or "data/0amv_active_market_value.csv"

        print(f"正在导入 0AMV 活跃市值到 DuckDB: {duckdb_path}")
        count = import_0amv_csv_to_duckdb(csv_path=csv_path, duckdb_path=duckdb_path)
        print(f"导入完成，共 {count} 条")

    elif action == "status":
        # 状态只读数据库，与数据源无关
        syncer = DataSyncer()
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"  数据库: {status.get('db_path', 'N/A')}")
        print(f"  股票: {status.get('stock_count', 0)}")
        print(f"  K线: {status.get('kline_count', 0)}")
        print("=" * 50)
        if status.get("sync_status"):
            print("同步状态:")
            for s in status["sync_status"]:
                print(f"  {s['data_type']}: {s.get('last_date', 'N/A')} ({s.get('status', 'N/A')})")


def cmd_self_optimize(args) -> int:
    """self-optimize 子命令."""
    from modules.self_optimizer import SelfOptimizer

    opt = SelfOptimizer(
        target=args.target,
        rounds=args.rounds,
        mode="dry_run",
    )
    if args.action == "run":
        result = opt.run()
        print(f"✓ Phase 3 done. {result['rounds']} rounds.")
        print(f"  keep={result['keep']} revert={result['revert']} break={result['break']}")
        print(f"  results.tsv: {result['results_tsv']}")
        print(f"  drafts: {result['drafts_dir']}")
        print("⚠️  请人工 review optimization_drafts/ 后决定合入")
        return 0
    if args.action == "status":
        print(f"target={opt.target} rounds={opt.rounds} mode={opt.mode}")
        return 0
    if args.action == "reset":
        state = Path("logs/self_optimizer_state.json")
        if state.exists():
            state.unlink()
            print("✓ state.json 已删除")
        return 0
    print(f"Unknown action: {args.action}")
    return 1


def add_self_optimize_parser(subparsers) -> None:
    """注册 self-optimize 子命令."""
    p = subparsers.add_parser("self-optimize", help="darwin self-optimizer")
    p.add_argument("action", choices=["run", "status", "reset"])
    p.add_argument("--target", choices=["trading"], default="trading")
    p.add_argument("--rounds", type=int, default=3)
    p.set_defaults(func=cmd_self_optimize)


def cmd_track(args) -> None:
    """跟踪池管理（add / remove / list / info / status / stats）"""
    from modules.tracking_manager import TrackingManager

    manager = TrackingManager()

    action = args.track_action

    if action == "add":
        if not args.ts_code:
            print("错误：添加股票需要指定股票代码")
            return
        success = manager.add_stock(
            ts_code=args.ts_code, name=args.name, reason=args.reason, strategy_tags=args.strategy, notes=args.notes
        )
        if args.json:
            json_output({"success": success})

    elif action == "remove":
        if not args.ts_code:
            print("错误：移除股票需要指定股票代码")
            return
        success = manager.remove_stock(ts_code=args.ts_code, reason=args.reason)
        if args.json:
            json_output({"success": success})

    elif action == "list":
        stocks = manager.list_stocks(status=args.status, strategy_tag=args.strategy[0] if args.strategy else None)
        if args.json:
            json_output(stocks)
        else:
            if not stocks:
                print("跟踪池为空")
                return
            print(f"\n跟踪池（状态：{args.status}）")
            print("-" * 80)
            print(f"{'代码':<12} {'名称':<10} {'添加日期':<12} {'策略标签':<15} {'原因'}")
            print("-" * 80)
            for stock in stocks:
                print(
                    f"{stock['ts_code']:<12} {stock.get('name', '') or '':<10} {stock['add_date']:<12} {stock.get('strategy_tags', '') or '':<15} {stock.get('track_reason', '') or ''}"
                )
            print("-" * 80)
            print(f"共 {len(stocks)} 只股票")

    elif action == "info":
        if not args.ts_code:
            print("错误：查看股票信息需要指定股票代码")
            return
        stock_info: dict[str, Any] | None = manager.get_stock_info(args.ts_code)
        if args.json:
            json_output(stock_info if stock_info else {})
        else:
            if not stock_info:
                print(f"股票 {args.ts_code} 不在跟踪池中")
                return
            print(f"\n股票信息：{stock_info['ts_code']}")
            print("-" * 40)
            print(f"名称：{stock_info.get('name', '') or ''}")
            print(f"状态：{stock_info['status']}")
            print(f"添加日期：{stock_info['add_date']}")
            print(f"移除日期：{stock_info.get('remove_date', '') or '未移除'}")
            print(f"策略标签：{stock_info.get('strategy_tags', '') or ''}")
            print(f"跟踪原因：{stock_info.get('track_reason', '') or ''}")
            print(f"备注：{stock_info.get('notes', '') or ''}")

    elif action == "status":
        if not args.ts_code:
            print("错误：更新状态需要指定股票代码")
            return
        success = manager.update_stock_status(ts_code=args.ts_code, status=args.status, notes=args.notes)
        if args.json:
            json_output({"success": success})

    elif action == "stats":
        stats = manager.get_tracking_stats()
        distribution = manager.get_strategy_distribution()
        if args.json:
            json_output({"stats": stats, "distribution": distribution})
        else:
            print("\n跟踪池统计")
            print("-" * 40)
            print(f"总数量：{stats.get('total', 0)}")
            print(f"活跃：{stats.get('active', 0)}")
            print(f"暂停：{stats.get('paused', 0)}")
            print(f"已移除：{stats.get('removed', 0)}")
            print(f"今日新增：{stats.get('today_added', 0)}")
            if distribution:
                print("\n策略分布：")
                for strategy, count in sorted(distribution.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {strategy}: {count}只")


def cmd_monitor(args) -> None:
    """自选股监控扫描命令行处理入口"""
    from modules.core.paths import REPORTS_DIR
    from modules.monitor import run_watchlist_monitor

    use_json = getattr(args, "json", False)
    enable_push = not getattr(args, "no_push", False)
    days = getattr(args, "days", 30)

    res = run_watchlist_monitor(sync_days=days, enable_push=enable_push)

    if use_json:
        json_output(res)
    else:
        print(f"自选股主动扫描监控完成。状态: {res['status']}, 警报总数: {res.get('alerts_count', 0)}")
        print(f"详细警报分析已输出至 {REPORTS_DIR}/monitor_alert.md")


def cmd_market_timing(args) -> None:
    """市场择时指标命令。"""
    from modules.market_timing import compute_market_timing, format_market_timing

    result = compute_market_timing(
        trade_date=getattr(args, "date", None),
        index_code=getattr(args, "index", "000001.SH"),
        days=getattr(args, "days", 120),
        duckdb_path=getattr(args, "duckdb", None),
    )

    if getattr(args, "json", False):
        json_output(result)
    else:
        print(format_market_timing(result))
