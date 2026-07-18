#!/usr/bin/env python3
"""
策略回测评估脚本

在真实数据上运行少妇战法回测、多策略融合回测和选股筛选，
收集性能指标用于策略优化决策。

用法: .venv/bin/python scripts/eval_strategies.py
"""

import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中（必须在 import modules 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402  在 sys.path 设置后导入
from modules.database import get_connection  # noqa: E402
from modules.backtest_six_step import backtest_shaofu_single  # noqa: E402
from modules.backtest import backtest_multi_strategy  # noqa: E402
from modules.screener import screen_stocks  # noqa: E402

# 加载 .env（modules/__init__.py 也会做，但脚本直接运行时需要手动）
try:
    load_dotenv(project_root / ".env")
except Exception:
    pass


def get_test_stocks(limit: int = 20):
    """获取数据充足的测试股票"""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.ts_code, s.name, COUNT(*) as cnt
            FROM daily_kline d
            JOIN stock_basic s ON d.ts_code = s.ts_code
            GROUP BY d.ts_code
            HAVING cnt >= 250
            ORDER BY cnt DESC
            LIMIT ?
        """,
            (limit,),
        )
        return cur.fetchall()


def run_shaofu_backtests(stocks):
    """Step 2: 少妇战法单股回测"""
    print("=" * 80)
    print("STEP 2: 少妇战法六步闭环回测 (250天)")
    print("=" * 80)

    results = []
    for ts_code, name, cnt in stocks:
        try:
            result = backtest_shaofu_single(ts_code, days=250)
            print(
                f"  {ts_code} {name:<8}: trades={result.total_trades:3d} "
                f"win_rate={result.win_rate:.1%} "
                f"total_return={result.total_return:+.1%} "
                f"sharpe={result.sharpe_ratio:.2f} "
                f"max_dd={result.max_drawdown:.1%} "
                f"profit_factor={result.profit_factor:.2f} "
                f"avg_hold={result.avg_holding_days:.1f}d"
            )
            results.append(
                {
                    "ts_code": ts_code,
                    "name": name,
                    "total_trades": result.total_trades,
                    "win_rate": result.win_rate,
                    "total_return": result.total_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "profit_factor": result.profit_factor,
                    "avg_holding_days": result.avg_holding_days,
                }
            )
        except Exception as e:
            print(f"  {ts_code} {name:<8}: ERROR {e}")
            results.append({"ts_code": ts_code, "name": name, "error": str(e)})

    return results


def run_multi_strategy_backtests(stocks):
    """Step 3: 多策略融合回测（单股）"""
    print("\n" + "=" * 80)
    print("STEP 3: 多策略融合回测 (250天, 全策略信号)")
    print("=" * 80)

    results = []
    for ts_code, name, cnt in stocks:
        try:
            result = backtest_multi_strategy(ts_code, days=250)
            print(
                f"  {ts_code} {name:<8}: trades={result.total_trades:3d} "
                f"win_rate={result.win_rate:.1%} "
                f"total_return={result.total_return:+.1%} "
                f"sharpe={result.sharpe_ratio:.2f} "
                f"max_dd={result.max_drawdown:.1%} "
                f"profit_factor={result.profit_factor:.2f}"
            )
            results.append(
                {
                    "ts_code": ts_code,
                    "name": name,
                    "total_trades": result.total_trades,
                    "win_rate": result.win_rate,
                    "total_return": result.total_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "profit_factor": result.profit_factor,
                }
            )
        except Exception as e:
            print(f"  {ts_code} {name:<8}: ERROR {e}")
            results.append({"ts_code": ts_code, "name": name, "error": str(e)})

    return results


def run_screener():
    """Step 4: B1选股信号质量"""
    print("\n" + "=" * 80)
    print("STEP 4: B1选股信号质量检查")
    print("=" * 80)

    results = screen_stocks(criteria="b1", max_stocks=20, use_parallel=False)
    print(f"\n  B1选股命中: {len(results)}只")
    for r in results[:10]:
        print(
            f"    {r.ts_code} {r.name:<8}: score={r.score:.1f} "
            f"b1={r.b1_score:.1f} trend={r.trend_score:.1f} "
            f"risk={r.risk_score:.1f} vol={r.volume_score:.1f}"
        )
    return results


def summarize(shaofu_results, multi_results, screener_results):
    """Step 5: 汇总分析"""
    print("\n" + "=" * 80)
    print("STEP 5: 汇总分析")
    print("=" * 80)

    # --- 少妇战法汇总 ---
    valid_shaofu = [r for r in shaofu_results if "error" not in r]
    zero_trade_shaofu = [r for r in valid_shaofu if r["total_trades"] == 0]

    print("\n--- 少妇战法六步闭环 ---")
    print(f"  测试股票数: {len(shaofu_results)}")
    print(f"  有交易的股票: {len(valid_shaofu) - len(zero_trade_shaofu)}")
    print(f"  无交易的股票(策略未触发): {len(zero_trade_shaofu)}")
    if zero_trade_shaofu:
        print(f"    无交易: {', '.join(r['ts_code'] + ' ' + r['name'] for r in zero_trade_shaofu)}")

    traded_shaofu = [r for r in valid_shaofu if r["total_trades"] > 0]
    if traded_shaofu:
        avg_win_rate = sum(r["win_rate"] for r in traded_shaofu) / len(traded_shaofu)
        avg_return = sum(r["total_return"] for r in traded_shaofu) / len(traded_shaofu)
        avg_sharpe = sum(r["sharpe_ratio"] for r in traded_shaofu) / len(traded_shaofu)
        avg_max_dd = sum(r["max_drawdown"] for r in traded_shaofu) / len(traded_shaofu)
        avg_pf = sum(r["profit_factor"] for r in traded_shaofu) / len(traded_shaofu)
        avg_hold = sum(r["avg_holding_days"] for r in traded_shaofu) / len(traded_shaofu)

        best_wr = max(traded_shaofu, key=lambda r: r["win_rate"])
        best_sharpe = max(traded_shaofu, key=lambda r: r["sharpe_ratio"])
        best_return = max(traded_shaofu, key=lambda r: r["total_return"])
        worst_dd = max(traded_shaofu, key=lambda r: r["max_drawdown"])

        print(f"\n  平均胜率:     {avg_win_rate:.1%}")
        print(f"  平均累计收益: {avg_return:+.1%}")
        print(f"  平均夏普比率: {avg_sharpe:.2f}")
        print(f"  平均最大回撤: {avg_max_dd:.1%}")
        print(f"  平均盈亏比:   {avg_pf:.2f}")
        print(f"  平均持仓天数: {avg_hold:.1f}")
        print(f"\n  最高胜率:   {best_wr['ts_code']} {best_wr['name']} {best_wr['win_rate']:.1%}")
        print(f"  最高夏普:   {best_sharpe['ts_code']} {best_sharpe['name']} {best_sharpe['sharpe_ratio']:.2f}")
        print(f"  最高收益:   {best_return['ts_code']} {best_return['name']} {best_return['total_return']:+.1%}")
        print(f"  最大回撤:   {worst_dd['ts_code']} {worst_dd['name']} {worst_dd['max_drawdown']:.1%}")

    # --- 多策略融合汇总 ---
    valid_multi = [r for r in multi_results if "error" not in r]
    zero_trade_multi = [r for r in valid_multi if r["total_trades"] == 0]

    print("\n--- 多策略融合回测 ---")
    print(f"  测试股票数: {len(multi_results)}")
    print(f"  有交易的股票: {len(valid_multi) - len(zero_trade_multi)}")
    print(f"  无交易的股票(策略未触发): {len(zero_trade_multi)}")
    if zero_trade_multi:
        print(f"    无交易: {', '.join(r['ts_code'] + ' ' + r['name'] for r in zero_trade_multi)}")

    traded_multi = [r for r in valid_multi if r["total_trades"] > 0]
    if traded_multi:
        avg_wr = sum(r["win_rate"] for r in traded_multi) / len(traded_multi)
        avg_ret = sum(r["total_return"] for r in traded_multi) / len(traded_multi)
        avg_sh = sum(r["sharpe_ratio"] for r in traded_multi) / len(traded_multi)
        avg_dd = sum(r["max_drawdown"] for r in traded_multi) / len(traded_multi)
        avg_pf = sum(r["profit_factor"] for r in traded_multi) / len(traded_multi)

        best_wr_m = max(traded_multi, key=lambda r: r["win_rate"])
        best_sh_m = max(traded_multi, key=lambda r: r["sharpe_ratio"])
        best_ret_m = max(traded_multi, key=lambda r: r["total_return"])

        print(f"\n  平均胜率:     {avg_wr:.1%}")
        print(f"  平均累计收益: {avg_ret:+.1%}")
        print(f"  平均夏普比率: {avg_sh:.2f}")
        print(f"  平均最大回撤: {avg_dd:.1%}")
        print(f"  平均盈亏比:   {avg_pf:.2f}")
        print(f"\n  最高胜率:   {best_wr_m['ts_code']} {best_wr_m['name']} {best_wr_m['win_rate']:.1%}")
        print(f"  最高夏普:   {best_sh_m['ts_code']} {best_sh_m['name']} {best_sh_m['sharpe_ratio']:.2f}")
        print(f"  最高收益:   {best_ret_m['ts_code']} {best_ret_m['name']} {best_ret_m['total_return']:+.1%}")

    # --- 跨策略对比 ---
    print("\n--- 策略对比 (少妇 vs 多策略) ---")
    common_codes = set()
    if traded_shaofu and traded_multi:
        shaofu_map = {r["ts_code"]: r for r in traded_shaofu}
        multi_map = {r["ts_code"]: r for r in traded_multi}
        common_codes = set(shaofu_map.keys()) & set(multi_map.keys())

        if common_codes:
            print(f"  可比股票: {len(common_codes)}只")
            sf_better_wr = 0
            sf_better_sh = 0
            for code in common_codes:
                sf = shaofu_map[code]
                mt = multi_map[code]
                if sf["win_rate"] >= mt["win_rate"]:
                    sf_better_wr += 1
                if sf["sharpe_ratio"] >= mt["sharpe_ratio"]:
                    sf_better_sh += 1
            print(f"  少妇胜率更高的股票: {sf_better_wr}/{len(common_codes)}")
            print(f"  少妇夏普更高的股票: {sf_better_sh}/{len(common_codes)}")

    # --- 选股汇总 ---
    print("\n--- B1选股信号 ---")
    print(f"  命中股票数: {len(screener_results)}")
    if screener_results:
        avg_score = sum(r.score for r in screener_results) / len(screener_results)
        avg_b1 = sum(r.b1_score for r in screener_results) / len(screener_results)
        print(f"  平均综合评分: {avg_score:.1f}")
        print(f"  平均B1评分:   {avg_b1:.1f}")

    # --- 关键问题回答 ---
    print("\n--- 关键问题 ---")

    # Q1: 哪个策略组合胜率最高?
    print("\n  Q1: 哪个策略胜率最高?")
    all_traded = []
    for r in traded_shaofu or []:
        all_traded.append(("少妇战法", r))
    for r in traded_multi or []:
        all_traded.append(("多策略融合", r))
    if all_traded:
        best = max(all_traded, key=lambda x: x[1]["win_rate"])
        print(f"    => {best[0]}: {best[1]['ts_code']} {best[1]['name']} 胜率 {best[1]['win_rate']:.1%}")

    # Q2: 哪个夏普最高?
    print("\n  Q2: 哪个策略夏普比率最高?")
    if all_traded:
        best = max(all_traded, key=lambda x: x[1]["sharpe_ratio"])
        print(f"    => {best[0]}: {best[1]['ts_code']} {best[1]['name']} 夏普 {best[1]['sharpe_ratio']:.2f}")

    # Q3: 平均最大回撤
    print("\n  Q3: 平均最大回撤?")
    if traded_shaofu:
        print(f"    少妇战法: {sum(r['max_drawdown'] for r in traded_shaofu) / len(traded_shaofu):.1%}")
    if traded_multi:
        print(f"    多策略融合: {sum(r['max_drawdown'] for r in traded_multi) / len(traded_multi):.1%}")

    # Q4: 0交易股票数
    print("\n  Q4: 策略未触发(0交易)的股票数?")
    print(f"    少妇战法: {len(zero_trade_shaofu)}/{len(shaofu_results)}")
    print(f"    多策略融合: {len(zero_trade_multi)}/{len(multi_results)}")

    print("\n" + "=" * 80)
    print("评估完成")
    print("=" * 80)


def main():
    print("策略回测评估 (真实数据)")
    print("=" * 80)

    # Step 1: 获取测试股票
    print("\nSTEP 1: 获取测试股票 (>=250天数据)")
    stocks = get_test_stocks(20)
    print(f"  找到 {len(stocks)} 只股票:")
    for ts_code, name, cnt in stocks:
        print(f"    {ts_code} {name} ({cnt}天)")

    if not stocks:
        print("  没有找到数据充足的股票，请先运行数据同步。")
        return

    # Step 2: 少妇战法回测
    shaofu_results = run_shaofu_backtests(stocks)

    # Step 3: 多策略融合回测 (取前10只)
    top_stocks = stocks[:10]
    multi_results = run_multi_strategy_backtests(top_stocks)

    # Step 4: B1选股
    screener_results = run_screener()

    # Step 5: 汇总
    summarize(shaofu_results, multi_results, screener_results)


if __name__ == "__main__":
    main()
