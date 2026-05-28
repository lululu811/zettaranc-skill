#!/usr/bin/env python3
"""
Z哥量化工具 CLI

用法：
    python -m modules.cli analyze 600487.SH
    python -m modules.cli screen --strategy B1
    python -m modules.cli watchlist add 600487.SH --tag 通信设备
    python -m modules.cli diagnose 600487.SH
"""

import argparse
import sys
import os
from typing import List, Optional

# 加载环境变量
from pathlib import Path
from dotenv import load_dotenv
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def cmd_analyze(args):
    """分析单只股票"""
    from modules.indicators import analyze_stock
    from modules.strategies import detect_all_strategies, StrategyType
    from modules.portfolio_diagnosis import diagnose_stock

    ts_code = args.ts_code

    print(f"\n{'='*60}")
    print(f"股票分析: {ts_code}")
    print(f"{'='*60}")

    # 1. 指标分析
    print("\n【技术指标】")
    result = analyze_stock(ts_code, days=args.days)
    print(f"  日期: {result.trade_date}")
    print(f"  KDJ:  K={result.k:.2f}  D={result.d:.2f}  J={result.j:.2f}")
    print(f"  MACD: DIF={result.dif:.4f}  DEA={result.dea:.4f}  柱={result.macd_hist:.4f}")
    print(f"  BBI:  {result.bbi:.2f}")
    print(f"  均线: MA5={result.ma5:.2f}  MA10={result.ma10:.2f}  MA20={result.ma20:.2f}")
    print(f"  RSI:  {result.rsi6:.2f}/{result.rsi12:.2f}/{result.rsi24:.2f}")
    print(f"  砖型图: {result.brick_trend}({result.brick_count}块)  值={result.brick_value:.2f}")

    # 2. 策略信号
    print("\n【战法信号】")
    signals = detect_all_strategies(ts_code, days=args.days)
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

    # 3. 诊断
    print("\n【持仓诊断】")
    diagnosis = diagnose_stock(ts_code, days=args.days)
    print(diagnosis)


def cmd_screen(args):
    """筛选股票"""
    from modules.screener import StockScore
    from modules.database import get_connection

    print(f"\n{'='*60}")
    print(f"股票筛选")
    print(f"{'='*60}")

    strategy = args.strategy
    limit = args.limit

    # 从数据库中获取有K线数据的股票列表
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ts_code FROM daily_kline LIMIT ?", (limit * 5,))
        ts_codes = [row['ts_code'] for row in cursor.fetchall()]

    results = []
    for ts_code in ts_codes:
        try:
            score = StockScore(ts_code)
            if strategy == 'B1' and score.b1_score >= 3:
                results.append((ts_code, score.b1_score, 'B1'))
            elif strategy == 'B2' and score.is_b2:
                results.append((ts_code, score.b2_score, 'B2'))
            elif strategy == '完美图形' and score.is_perfect_pattern:
                results.append((ts_code, score.total_score, '完美图形'))
            elif strategy == '超级B1' and score.sb1_score >= 3:
                results.append((ts_code, score.sb1_score, '超级B1'))
        except Exception:
            continue

    print(f"\n筛选条件: {strategy}")
    print(f"扫描股票: {len(ts_codes)} 只")
    print(f"命中: {len(results)} 只\n")

    for ts_code, score, reason in sorted(results, key=lambda x: x[1], reverse=True)[:limit]:
        print(f"  {ts_code}  {reason}={score}")


def cmd_watchlist(args):
    """自选股管理"""
    from modules.watchlist import add_watch, remove_watch, list_watch, scan_watchlist

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
        stocks = result.get('stocks', [])
        print(f"\n扫描自选股 ({len(stocks)}只)...")
        for s in stocks:
            ts_code = s['ts_code']
            signals = s.get('signals', [])
            if signals:
                latest = signals[0]
                print(f"  {ts_code}: {latest['strategy']} ({latest['date']})")
            else:
                print(f"  {ts_code}: 无信号")


def cmd_diagnose(args):
    """持仓诊断"""
    from modules.portfolio_diagnosis import diagnose_stock

    ts_code = args.ts_code
    diagnosis = diagnose_stock(ts_code, days=args.days)
    print(diagnosis)


def main():
    parser = argparse.ArgumentParser(
        description="Z哥量化工具 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m modules.cli analyze 600487.SH
  python -m modules.cli screen --strategy B1 --limit 20
  python -m modules.cli watchlist add 600487.SH --tag 通信设备,5G
  python -m modules.cli watchlist scan
  python -m modules.cli diagnose 600487.SH
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # analyze
    p_analyze = subparsers.add_parser('analyze', help='分析单只股票')
    p_analyze.add_argument('ts_code', help='股票代码，如 600487.SH')
    p_analyze.add_argument('--days', type=int, default=120, help='分析天数')

    # screen
    p_screen = subparsers.add_parser('screen', help='筛选股票')
    p_screen.add_argument('--strategy', choices=['B1', 'B2', '完美图形', '超级B1'],
                          default='B1', help='筛选策略')
    p_screen.add_argument('--limit', type=int, default=20, help='输出数量')

    # watchlist
    p_wl = subparsers.add_parser('watchlist', help='自选股管理')
    p_wl.add_argument('action', choices=['add', 'remove', 'list', 'scan'],
                      help='操作')
    p_wl.add_argument('ts_code', nargs='?', help='股票代码')
    p_wl.add_argument('--tags', help='标签，逗号分隔')

    # diagnose
    p_diag = subparsers.add_parser('diagnose', help='持仓诊断')
    p_diag.add_argument('ts_code', help='股票代码')
    p_diag.add_argument('--days', type=int, default=120, help='分析天数')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 取消代理，避免 Tushare 连接问题
    os.environ['HTTP_PROXY'] = ''
    os.environ['HTTPS_PROXY'] = ''

    if args.command == 'analyze':
        cmd_analyze(args)
    elif args.command == 'screen':
        cmd_screen(args)
    elif args.command == 'watchlist':
        cmd_watchlist(args)
    elif args.command == 'diagnose':
        cmd_diagnose(args)


if __name__ == '__main__':
    main()
