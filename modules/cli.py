#!/usr/bin/env python3
"""
Z哥量化工具 CLI（v2.10.0 统一入口）

用法：
    python -m modules.cli analyze 600487.SH
    python -m modules.cli screen --strategy B1
    python -m modules.cli score 600487.SH
    python -m modules.cli workflow
    python -m modules.cli watchlist add 600487.SH --tags 通信设备
    python -m modules.cli diagnose 600487.SH
    python -m modules.cli sync init
    python -m modules.cli sync sync 600487.SH
    python -m modules.cli sync status
    python -m modules.cli sync stk-factor 600487.SH

设计：所有命令通过 `zt` entry point（已在 pyproject.toml 注册）暴露。
本文件取代 v2.9.0 散落在 5 个模块的独立 main()（screener / data_sync /
portfolio_diagnosis / watchlist / indicators.data_layer）。
"""

import argparse
import sys
import os
from typing import List, Optional

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）


# CLI 中文别名 → screener 英文 criteria 的统一映射
STRATEGY_ALIAS = {
    "B1": "b1",
    "B2": "b2_breakout",
    "B3": "b3_consensus",
    "完美图形": "perfect",
    "超级B1": "super_b1",
    "长安战法": "changan",
    "建仓波": "build_wave",
    "吸筹": "xishou",
    "安全": "safe",
    "超跌": "oversold",
    "突破": "breakout",
}

STRATEGY_CHOICES = list(STRATEGY_ALIAS.keys())


def cmd_analyze(args):
    """分析单只股票"""
    from modules.indicators import analyze_stock
    from modules.indicators.data_layer import get_kline_data, DailyData
    from modules.strategies import detect_all_strategies, StrategyType
    from modules.portfolio_diagnosis import diagnose_stock

    ts_code = args.ts_code
    days = args.days

    print(f"\n{'='*60}")
    print(f"股票分析: {ts_code}")
    print(f"{'='*60}")

    # 1. 指标分析
    print("\n【技术指标】")
    result = analyze_stock(ts_code, days=days)
    print(f"  日期: {result.trade_date}")
    print(f"  KDJ:  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}")
    print(f"  MACD: DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}")
    print(f"  BBI:  {result.bbi:.2f}")
    print(f"  均线: MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}")
    print(f"  RSI:  {result.rsi6:.2f}/{result.rsi12:.2f}/{result.rsi24:.2f}")
    print(f"  砖型图: {result.brick_trend}({result.brick_count}块)  值={result.brick_value:.2f}")

    # 2. P2 指标：三波理论 + 麒麟会（需要原始 K 线数据）
    print("\n【主力阶段】")
    try:
        from modules.indicators import detect_three_waves, detect_kirin_stage
        klines = get_kline_data(ts_code, days=days)
        if not klines:
            print("  无 K 线数据，跳过主力阶段分析")
        else:
            daily_klines = []
            for i, k in enumerate(klines):
                prev_close = klines[i-1].close if i > 0 else k.close
                daily_klines.append(DailyData(
                    ts_code=k.ts_code,
                    trade_date=k.trade_date,
                    open=k.open,
                    high=k.high,
                    low=k.low,
                    close=k.close,
                    vol=k.vol,
                    amount=k.amount,
                    pct_chg=k.pct_chg,
                    prev_close=prev_close,
                ))
            wave = detect_three_waves(daily_klines)
            kirin = detect_kirin_stage(daily_klines)

            print(f"  三波理论: {wave['wave']} (conf={wave['confidence']}) → {wave['b1_suggestion']}")
            if wave['stats']:
                s = wave['stats']
                print(f"    低点→当前: {s['low_price']:.1f}→{s['high_price']:.1f} 涨幅{s['gain_pct']:.1f}%")
                print(f"    涨停{s['limit_up_count']}次 阳线占比{s['red_ratio']*100:.0f}% 日均{s['avg_daily_gain']:.2f}%")

            print(f"  麒麟会: {kirin['stage']} (conf={kirin['confidence']}) → {kirin['operation']}")
            if kirin['sub_type'] != '未知':
                print(f"    子类型: {kirin['sub_type']}")
            if kirin.get('scores'):
                sc = kirin['scores']
                print(f"    评分: 吸{sc['xishou']} 拉{sc['lasheng']} 派{sc['paifa']} 落{sc['luoluo']}")
    except Exception as e:
        print(f"  检测失败: {e}")

    # 3. 策略信号
    print("\n【战法信号】")
    signals = detect_all_strategies(ts_code, days=days)
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

    # 4. 诊断
    print("\n【持仓诊断】")
    diagnosis = diagnose_stock(ts_code, days=days)
    print(diagnosis)


def cmd_screen(args):
    """筛选股票（调 screener.screen_stocks）"""
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(args.strategy, args.strategy)

    print(f"\n{'='*60}")
    print(f"股票筛选 (criteria={criteria}, 上限={args.limit or '全市场'})")
    print(f"{'='*60}")

    results = screen_stocks(
        criteria=criteria,
        max_stocks=args.limit if args.limit > 0 else 0,
        use_parallel=not args.no_parallel,
    )
    print(f"\n扫描完成，命中: {len(results)} 只\n")

    # 输出前 limit 只（limit=0 时输出全部 500 上限内的命中）
    output_limit = args.limit if args.limit > 0 else len(results)
    for r in results[:output_limit]:
        print(f"  {r.ts_code:<12} {r.name:<8} score={r.score:.1f}  {r.rating}")
        reasons = getattr(r, 'reasons', []) or []
        warnings = getattr(r, 'warnings', []) or []
        if reasons:
            print(f"    reasons: {','.join(reasons[:3])}")
        if warnings:
            print(f"    warnings: {','.join(warnings[:3])}")


def cmd_score(args):
    """单只股票综合评分（来自 screener.py score action）"""
    from modules.screener import analyze_stock, format_stock_score
    if not args.ts_code:
        print("请指定股票代码: zt score <ts_code>")
        sys.exit(1)
    score = analyze_stock(args.ts_code)
    print(format_stock_score(score))


def cmd_workflow(args):
    """每日五步工作流（来自 screener.py workflow action）"""
    from modules.screener import daily_workflow
    daily_workflow()


def cmd_watchlist(args):
    """自选股管理"""
    from modules.watchlist import (
        add_watch, remove_watch, list_watch,
        scan_watchlist, generate_daily_report,
    )

    action = args.action

    if action == 'add':
        tags = args.tags if hasattr(args, 'tags') and args.tags else ""
        add_watch(args.ts_code, tags=tags)
        print(f"已添加: {args.ts_code}")

    elif action == 'remove':
        remove_watch(args.ts_code)
        print(f"已移除: {args.ts_code}")

    elif action == 'list':
        stocks = list_watch()
        print(f"\n自选股列表 ({len(stocks)}只):")
        for s in stocks:
            tags = s.get('tags', '') or '无'
            added = s.get('added_date', s.get('updated_at', '未知'))
            print(f"  {s['ts_code']}  标签:{tags}  添加:{added}")

    elif action == 'scan':
        result = scan_watchlist()
        alerts = result.get('alerts', [])
        summary = result.get('summary', {})
        print(f"\n扫描自选股 ({summary.get('total', 0)}只):")
        print(f"  B1={summary.get('b1_count', 0)}  B2={summary.get('b2_count', 0)}  "
              f"逃顶={summary.get('exit_count', 0)}  破位={summary.get('break_count', 0)}  "
              f"异动={summary.get('abnormal_count', 0)}")
        for a in alerts[:20]:
            print(f"  [{a.level}] {a.ts_code} {a.name}  {a.alert_type}: {a.message}")

    elif action == 'report':
        print(generate_daily_report())


def cmd_diagnose(args):
    """持仓诊断"""
    from modules.portfolio_diagnosis import diagnose_stock, format_report

    ts_code = args.ts_code
    diagnosis = diagnose_stock(ts_code, days=args.days)
    print(format_report(diagnosis))


def cmd_sync(args):
    """数据同步（init / sync / status / stk-factor）"""
    import logging
    from datetime import datetime, timedelta
    from modules.data_sync import DataSyncer
    from modules.database import init_database

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    action = args.sync_action

    if action == "init":
        init_database()
        print("数据库初始化完成")

    elif action == "sync":
        syncer = DataSyncer()
        if args.ts_code:
            # 同步单只股票
            syncer.sync_daily_kline(args.ts_code)
            if not args.skip_indicators:
                print(f"正在同步指标缓存: {args.ts_code} ...")
                syncer.sync_indicator_cache(args.ts_code, days=args.days)
        else:
            # 批量同步所有股票
            syncer.sync_stock_basic()
            syncer.sync_all_daily_kline(days=args.days)
            if args.indicators and not args.skip_indicators:
                print("正在批量同步指标缓存...")
                syncer.sync_all_indicators()
        print("同步完成")
        print(syncer.get_sync_status())

    elif action == "stk-factor":
        syncer = DataSyncer()
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

    elif action == "status":
        syncer = DataSyncer()
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"  数据库: {status.get('db_path', 'N/A')}")
        print(f"  股票: {status.get('stock_count', 0)}")
        print(f"  K线: {status.get('kline_count', 0)}")
        print("=" * 50)
        if status.get('sync_status'):
            print("同步状态:")
            for s in status['sync_status']:
                print(f"  {s['data_type']}: {s.get('last_date', 'N/A')} ({s.get('status', 'N/A')})")


def main():
    parser = argparse.ArgumentParser(
        prog="zt",
        description="Z哥量化工具 CLI（v2.10.0 统一入口）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  zt analyze 600487.SH
  zt screen --strategy B1 --limit 20
  zt score 600487.SH
  zt workflow
  zt watchlist add 600487.SH --tags 通信设备,5G
  zt watchlist scan
  zt watchlist report
  zt diagnose 600487.SH
  zt sync init
  zt sync sync 600487.SH
  zt sync status
  zt sync stk-factor 600487.SH
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='子命令', required=True)

    # ── analyze ──
    p_analyze = subparsers.add_parser('analyze', help='分析单只股票（指标 + 主力阶段 + 战法信号 + 诊断）')
    p_analyze.add_argument('ts_code', help='股票代码，如 600487.SH')
    p_analyze.add_argument('--days', type=int, default=120, help='分析天数')

    # ── screen ──
    p_screen = subparsers.add_parser('screen', help='批量选股（11 种策略）')
    p_screen.add_argument('--strategy', choices=STRATEGY_CHOICES,
                          default='B1', help='筛选策略（11 种别名）')
    p_screen.add_argument('--limit', type=int, default=20,
                          help='输出数量（0=全市场 500 上限）')
    p_screen.add_argument('--no-parallel', action='store_true', help='禁用多进程并行')

    # ── score（来自 screener.py score）──
    p_score = subparsers.add_parser('score', help='单只股票综合评分')
    p_score.add_argument('ts_code', nargs='?', help='股票代码，如 600487.SH')

    # ── workflow（来自 screener.py workflow）──
    subparsers.add_parser('workflow', help='每日五步工作流')

    # ── diagnose ──
    p_diag = subparsers.add_parser('diagnose', help='持仓诊断')
    p_diag.add_argument('ts_code', help='股票代码')
    p_diag.add_argument('--days', type=int, default=120, help='分析天数')

    # ── watchlist（add/remove/list/scan/report）──
    p_wl = subparsers.add_parser('watchlist', help='自选股管理')
    p_wl.add_argument('action', choices=['add', 'remove', 'list', 'scan', 'report'],
                      help='操作')
    p_wl.add_argument('ts_code', nargs='?', help='股票代码（add/remove 必填）')
    p_wl.add_argument('--tags', help='标签，逗号分隔')

    # ── sync（init/sync/status/stk-factor）──
    p_sync = subparsers.add_parser('sync', help='数据同步（init/sync/status/stk-factor）')
    p_sync_sub = p_sync.add_subparsers(dest='sync_action', required=True)

    p_sync_init = p_sync_sub.add_parser('init', help='初始化数据库')
    p_sync_run = p_sync_sub.add_parser('sync', help='同步日线 K 线（+ 可选指标缓存）')
    p_sync_run.add_argument('ts_code', nargs='?', help='股票代码（不传 = 全市场批量）')
    p_sync_run.add_argument('--days', type=int, default=730, help='同步天数')
    p_sync_run.add_argument('--indicators', action='store_true',
                            help='批量同步完成后计算并缓存技术指标')
    p_sync_run.add_argument('--skip-indicators', action='store_true',
                            help='跳过指标缓存（单只默认同步，批量需 --indicators）')
    p_sync_status = p_sync_sub.add_parser('status', help='查看同步状态')
    p_sync_factor = p_sync_sub.add_parser('stk-factor', help='同步 Tushare 官方指标（diff 验证用）')
    p_sync_factor.add_argument('ts_code', nargs='?', help='股票代码（不传 = 全市场）')
    p_sync_factor.add_argument('--days', type=int, default=365, help='同步天数')

    args = parser.parse_args()

    # 取消代理，避免 Tushare 连接问题
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    # 调度表
    handlers = {
        'analyze': cmd_analyze,
        'screen': cmd_screen,
        'score': cmd_score,
        'workflow': cmd_workflow,
        'diagnose': cmd_diagnose,
        'watchlist': cmd_watchlist,
        'sync': cmd_sync,
    }
    handlers[args.command](args)


if __name__ == '__main__':
    main()
