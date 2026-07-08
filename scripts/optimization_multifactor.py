#!/usr/bin/env python3
"""
多因子组合优化脚本 — 4 Phase 渐进式参数搜索

Phase 1: 基础参数网格搜索（J 阈值 × 止损 × 缩量阈值 = 160 组合）
Phase 2: 市场状态感知优化（按 BULL/BEAR/SIDEWAYS 分组，独立搜索各状态最优参数）
Phase 3: 仓位参数优化（risk_per_trade × max_positions × regime_multiplier）
Phase 4: 行业分散化优化（max_per_industry × 行业采样策略）

用法:
    python3 scripts/optimization_multifactor.py                 # 完整 4 Phase 优化
    python3 scripts/optimization_multifactor.py --quick          # 快速模式（减少参数组合）
    python3 scripts/optimization_multifactor.py --phases 1,2     # 只运行 Phase 1 和 2
    python3 scripts/optimization_multifactor.py --stocks 30 --days 300  # 自定义股票数和天数
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.backtest_six_step import (
    ShaofuBacktestResult,
    _calc_metrics,
    backtest_shaofu_portfolio_integrated,
)
from modules.indicators import DailyData
from modules.industry_filter import IndustryFilter
from modules.loop_engine import LoopConfig, ShaofuLoopEngine
from modules.market_regime import MarketRegimeClassifier
from modules.position_manager import PositionManager

logger = logging.getLogger(__name__)


# ============================================================================
# 数据加载（复用 optimization_v2 的数据加载逻辑）
# ============================================================================


def load_klines_batch(ts_codes: list[str], days: int = 500) -> dict[str, list[DailyData]]:
    """批量加载 K 线数据

    Args:
        ts_codes: 股票代码列表
        days: 加载天数

    Returns:
        {ts_code: [DailyData, ...]} 按日期升序排列
    """
    db_path = Path("data/stock_data.db")
    if not db_path.exists():
        logger.error("数据库文件不存在: %s", db_path)
        return {}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    result: dict[str, list[DailyData]] = {}
    for ts_code in ts_codes:
        cursor.execute(
            """
            SELECT trade_date, open, high, low, close, vol, amount, pct_chg
            FROM daily_kline
            WHERE ts_code = ?
            ORDER BY trade_date DESC
            LIMIT ?
        """,
            (ts_code, days),
        )

        rows = cursor.fetchall()
        if not rows or len(rows) < 50:
            continue

        klines: list[DailyData] = []
        for row in reversed(rows):
            klines.append(
                DailyData(
                    ts_code=ts_code,
                    trade_date=row[0],
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    vol=float(row[5]),
                    amount=float(row[6]) if row[6] else 0,
                    pct_chg=float(row[7]) if row[7] else 0.0,
                )
            )
        result[ts_code] = klines

    conn.close()
    return result


def get_stocks(count: int = 50) -> list[str]:
    """获取优化用股票列表

    优先从 data/optimization_stocks.txt 读取，不存在则返回空列表。

    Args:
        count: 最大股票数

    Returns:
        股票代码列表
    """
    stocks_file = Path("data/optimization_stocks.txt")
    if stocks_file.exists():
        with open(stocks_file) as f:
            return [line.strip() for line in f if line.strip()][:count]
    return []


# ============================================================================
# 评估函数
# ============================================================================


@dataclass
class ParamScore:
    """参数组合的评估结果"""

    params: dict
    win_rate: float
    total_return: float
    sharpe: float
    max_dd: float
    trades: int
    score: float
    extra_metrics: dict = field(default_factory=dict)  # 额外指标（行业集中度等）


def eval_results(results: list[ShaofuBacktestResult]) -> dict:
    """评估单股回测结果集（用于 Phase 1 快速评估）

    Args:
        results: 各股回测结果列表

    Returns:
        聚合指标字典 {wr, ret, sharpe, dd, trades, stocks}
    """
    valid = [r for r in results if r.total_trades > 0]
    if not valid:
        return {"wr": 0, "ret": 0, "sharpe": 0, "dd": 0, "trades": 0, "stocks": 0}

    # 聚合所有交易
    all_pnls: list[float] = []
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    for r in valid:
        for t in r.trades:
            all_pnls.append(t.pnl_pct)
            equity *= 1 + t.pnl_pct / 100.0
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

    wins = [p for p in all_pnls if p > 0]
    total_return = (equity / 100.0) - 1.0
    wr = len(wins) / len(all_pnls) if all_pnls else 0

    # 夏普比率（交易级别，年化因子按平均持仓 10 日估算）
    if len(all_pnls) >= 3:
        avg_ret = sum(all_pnls) / len(all_pnls)
        var = sum((r - avg_ret) ** 2 for r in all_pnls) / (len(all_pnls) - 1)
        std = var**0.5 if var > 0 else 0
        sharpe = (avg_ret / std) * (252 / 10) ** 0.5 if std > 0 else 0
    else:
        sharpe = 0

    return {
        "wr": wr,
        "ret": total_return,
        "sharpe": sharpe,
        "dd": max_dd,
        "trades": len(all_pnls),
        "stocks": len(valid),
    }


def evaluate_portfolio_result(result_dict: dict) -> dict:
    """评估组合回测结果（用于 Phase 2-4 的集成回测）

    从 backtest_shaofu_portfolio_integrated 返回值中提取综合指标。

    Args:
        result_dict: backtest_shaofu_portfolio_integrated 的返回值

    Returns:
        {
            "wr": float,          # 胜率
            "ret": float,         # 累计收益率
            "sharpe": float,      # 夏普比率
            "dd": float,          # 最大回撤
            "trades": int,        # 总交易次数
            "industry_hhi": float,  # 行业集中度 (HHI)
            "position_util": float, # 仓位利用率
            "sub_period_stability": float,  # 子周期稳健性
        }
    """
    portfolio_result: ShaofuBacktestResult = result_dict.get("result")
    trade_details: list[dict] = result_dict.get("trade_details", [])
    daily_equity: list[tuple[str, float]] = result_dict.get("daily_equity", [])

    if not portfolio_result or not portfolio_result.trades:
        return {
            "wr": 0,
            "ret": 0,
            "sharpe": 0,
            "dd": 0,
            "trades": 0,
            "industry_hhi": 0,
            "position_util": 0,
            "sub_period_stability": 0,
        }

    # 基础指标
    wr = portfolio_result.win_rate
    total_return = portfolio_result.total_return
    sharpe = portfolio_result.sharpe_ratio
    max_dd = portfolio_result.max_drawdown
    total_trades = portfolio_result.total_trades

    # 行业集中度（HHI — Herfindahl-Hirschman Index）
    industry_hhi = _calc_industry_hhi(trade_details)

    # 仓位利用率（有持仓的天数 / 总交易天数）
    position_util = _calc_position_utilization(daily_equity)

    # 子周期稳健性（各市场状态下的胜率标准差，越小越稳健）
    sub_period_stability = _calc_sub_period_stability(trade_details)

    return {
        "wr": wr,
        "ret": total_return,
        "sharpe": sharpe,
        "dd": max_dd,
        "trades": total_trades,
        "industry_hhi": industry_hhi,
        "position_util": position_util,
        "sub_period_stability": sub_period_stability,
    }


def _calc_industry_hhi(trade_details: list[dict]) -> float:
    """计算交易记录中的行业集中度 (HHI)

    HHI = sum(行业占比^2)，范围 [1/N, 1]，越接近 1 越集中。
    无行业信息时返回 0。
    """
    if not trade_details:
        return 0.0

    # 按行业分组统计交易次数
    industry_counts: Counter[str] = Counter()
    for td in trade_details:
        industry = td.get("industry", "")
        if industry:
            industry_counts[industry] += 1

    if not industry_counts:
        return 0.0

    total = sum(industry_counts.values())
    hhi = sum((cnt / total) ** 2 for cnt in industry_counts.values())
    return round(hhi, 4)


def _calc_position_utilization(daily_equity: list[tuple[str, float]]) -> float:
    """计算仓位利用率

    以初始资金为基准，计算平均仓位占用比例。
    """
    if not daily_equity or len(daily_equity) < 2:
        return 0.0

    # 使用净值变化估算仓位利用（简化版）
    equities = [e for _, e in daily_equity]
    initial = equities[0]
    if initial <= 0:
        return 0.0

    # 估算：每日净值与初始资金的偏差作为仓位活动度
    deviations = [abs(eq - initial) / initial for eq in equities]
    avg_deviation = sum(deviations) / len(deviations)
    return round(min(avg_deviation * 5, 1.0), 4)  # 归一化到 [0, 1]


def _calc_sub_period_stability(trade_details: list[dict]) -> float:
    """计算子周期稳健性

    按市场状态分组，计算各组胜率的标准差。
    标准差越小 → 各状态下表现越一致 → 稳健性越高。
    返回 1 - normalized_std（越高越好）。
    """
    if not trade_details:
        return 0.0

    regime_trades: dict[str, list[float]] = {}
    for td in trade_details:
        regime = td.get("market_regime", "UNKNOWN")
        pnl = td.get("pnl_pct", 0)
        if regime not in regime_trades:
            regime_trades[regime] = []
        regime_trades[regime].append(pnl)

    if len(regime_trades) < 2:
        return 1.0  # 只有一种状态，视为完全稳健

    # 各状态胜率
    regime_win_rates: list[float] = []
    for regime, pnls in regime_trades.items():
        if len(pnls) >= 2:
            wr = len([p for p in pnls if p > 0]) / len(pnls)
            regime_win_rates.append(wr)

    if len(regime_win_rates) < 2:
        return 0.5

    # 胜率标准差
    mean_wr = sum(regime_win_rates) / len(regime_win_rates)
    var = sum((w - mean_wr) ** 2 for w in regime_win_rates) / len(regime_win_rates)
    std = var**0.5

    # 归一化到 [0, 1]：std=0 → 1.0（完全稳健），std=0.5 → 0.0
    stability = max(0.0, 1.0 - std * 2)
    return round(stability, 4)


def score_metrics(m: dict) -> float:
    """综合评分（用于 Phase 1 单股评估）

    Args:
        m: eval_results 返回的指标字典

    Returns:
        综合得分 [0, 100]
    """
    # 胜率权重 35%
    wr_s = min(m["wr"] / 0.5, 1.0) * 35
    # 收益权重 35%
    ret_s = min(max(m["ret"], 0) / 0.5, 1.0) * 35
    # 回撤惩罚 15%
    dd_s = max(0, 1 - m["dd"] / 0.25) * 15
    # 交易频率奖励 10%
    tr_s = min(m["trades"] / 500, 1.0) * 10
    # 夏普比率奖励 5%
    sh_s = min(max(m["sharpe"], 0) / 2.0, 1.0) * 5
    return wr_s + ret_s + dd_s + tr_s + sh_s


def score_portfolio_metrics(m: dict) -> float:
    """组合级综合评分（用于 Phase 2-4 集成回测评估）

    在基础评分上，额外考虑行业集中度、仓位利用率、子周期稳健性。

    Args:
        m: evaluate_portfolio_result 返回的指标字典

    Returns:
        综合得分 [0, 100]
    """
    # 基础评分（权重 70%）
    base = score_metrics(m) * 0.70

    # 行业分散度奖励（HHI 越低越好，理想值 < 0.25）
    hhi = m.get("industry_hhi", 0)
    if hhi > 0:
        hhi_s = max(0, 1 - hhi / 0.5) * 15  # 15% 权重
    else:
        hhi_s = 5  # 无行业信息时给默认分

    # 仓位利用率奖励（利用率越高越好）
    pos_util = m.get("position_util", 0)
    pos_s = min(pos_util / 0.5, 1.0) * 10  # 10% 权重

    # 子周期稳健性奖励
    stability = m.get("sub_period_stability", 0.5)
    stab_s = stability * 5  # 5% 权重

    return base + hhi_s + pos_s + stab_s


# ============================================================================
# Phase 1: 基础参数网格搜索
# ============================================================================


def phase1_basic_grid_search(
    all_klines: dict[str, list[DailyData]],
    quick: bool = False,
) -> list[ParamScore]:
    """Phase 1: 基础参数网格搜索

    J 阈值 × 止损 × 缩量阈值 = 8×5×4 = 160 组合（quick 模式 4×3×2 = 24）
    使用单股独立回测，快速评估各参数组合。

    Args:
        all_klines: {ts_code: klines} 数据字典
        quick: 是否使用精简参数空间

    Returns:
        按得分降序排列的 ParamScore 列表
    """
    print("\n" + "=" * 70)
    print("Phase 1: 基础参数网格搜索")
    print("=" * 70)

    # 参数空间
    if quick:
        j_values = [8, 12, 18, 25]
        sl_values = [-0.03, -0.07, -0.15]
        vol_values = [0.6, 0.8]
    else:
        j_values = [5, 8, 10, 12, 15, 18, 20, 25]
        sl_values = [-0.03, -0.05, -0.07, -0.10, -0.15]
        vol_values = [0.5, 0.6, 0.7, 0.8]

    combos = [(j, sl, v) for j in j_values for sl in sl_values for v in vol_values]
    print(f"参数组合数: {len(combos)} ({len(j_values)}×{len(sl_values)}×{len(vol_values)})")

    all_results: list[ParamScore] = []

    for idx, (j_th, sl_pct, vol_th) in enumerate(combos, 1):
        config = LoopConfig(
            j_threshold=j_th,
            stop_loss_pct=sl_pct,
            vol_shrink_threshold=vol_th,
        )
        engine = ShaofuLoopEngine(config)

        results: list[ShaofuBacktestResult] = []
        for ts_code, klines in all_klines.items():
            trades = engine.run_stock(klines, ts_code=ts_code)
            if trades:
                r = ShaofuBacktestResult(ts_code=ts_code, trades=trades)
                _calc_metrics(r)
                results.append(r)

        m = eval_results(results)
        s = score_metrics(m)

        all_results.append(
            ParamScore(
                params={"j_threshold": j_th, "stop_loss_pct": sl_pct, "vol_shrink": vol_th},
                win_rate=m["wr"],
                total_return=m["ret"],
                sharpe=m["sharpe"],
                max_dd=m["dd"],
                trades=m["trades"],
                score=s,
            )
        )

        if idx % 20 == 0 or idx == len(combos):
            best_score = max(r.score for r in all_results)
            print(f"  [{idx}/{len(combos)}] 当前最佳得分: {best_score:.2f}")

    all_results.sort(key=lambda x: x.score, reverse=True)
    return all_results


# ============================================================================
# Phase 2: 市场状态感知优化
# ============================================================================


def _load_index_klines(days: int) -> list[DailyData] | None:
    """加载大盘指数 K 线数据（用于市场状态分类）

    Args:
        days: 加载天数

    Returns:
        DailyData 列表（按日期升序），失败返回 None
    """
    db_path = Path("data/stock_data.db")
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT trade_date, open, high, low, close, vol, amount, pct_chg
            FROM daily_kline WHERE ts_code = '000001.SH'
            ORDER BY trade_date DESC LIMIT ?
            """,
            (days + 120,),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows or len(rows) < 120:
            return None
        klines: list[DailyData] = []
        for row in reversed(rows):
            klines.append(
                DailyData(
                    ts_code="000001.SH",
                    trade_date=row[0],
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    vol=float(row[5]),
                    amount=float(row[6]) if row[6] else 0,
                    pct_chg=float(row[7]) if row[7] else 0.0,
                )
            )
        return klines
    except Exception:
        return None


def phase2_regime_aware_optimization(
    all_klines: dict[str, list[DailyData]],
    base_params: dict,
    quick: bool = False,
) -> list[ParamScore]:
    """Phase 2: 市场状态感知优化

    使用 MarketRegimeClassifier 对每日市场状态分类，
    按状态分组交易，各状态独立搜索最优参数。

    策略（分步搜索，避免组合爆炸）：
    1. 加载大盘指数 K 线，预计算每日市场状态
    2. 对各状态独立搜索 J 阈值 × 止损 的最优组合
    3. 按各状态交易频率加权汇总得分

    Args:
        all_klines: {ts_code: klines} 数据字典
        base_params: Phase 1 最优基础参数
        quick: 是否使用精简参数空间

    Returns:
        按得分降序排列的 ParamScore 列表
    """
    print("\n" + "=" * 70)
    print("Phase 2: 市场状态感知优化")
    print("=" * 70)

    # 参数空间
    if quick:
        j_ranges = {"BULL": [15, 20, 25], "SIDEWAYS": [10, 12, 15], "BEAR": [3, 5, 8]}
        sl_ranges = {
            "BULL": [-0.05, -0.07, -0.10],
            "SIDEWAYS": [-0.03, -0.05, -0.07],
            "BEAR": [-0.02, -0.03, -0.05],
        }
    else:
        j_ranges = {"BULL": [12, 15, 18, 20, 25], "SIDEWAYS": [8, 10, 12, 15, 18], "BEAR": [3, 5, 8, 10]}
        sl_ranges = {
            "BULL": [-0.05, -0.07, -0.10, -0.15],
            "SIDEWAYS": [-0.03, -0.05, -0.07, -0.10],
            "BEAR": [-0.02, -0.03, -0.05, -0.07],
        }

    # 加载指数数据并预计算市场状态
    index_klines = _load_index_klines(max(500, max(len(kl) for kl in all_klines.values())) if all_klines else 500)

    regime_day_counts: dict[str, int] = {"BULL": 0, "BEAR": 0, "SIDEWAYS": 0}
    has_index = False

    if index_klines and len(index_klines) >= 120:
        classifier = MarketRegimeClassifier()
        regime_map = classifier.precompute_all(index_klines, start_idx=120)
        has_index = True
        for regime in regime_map.values():
            regime_day_counts[regime.value] = regime_day_counts.get(regime.value, 0) + 1
        total_days = sum(regime_day_counts.values())
        print(f"  指数数据: {len(index_klines)} 日, 市场状态分布:")
        for r, cnt in regime_day_counts.items():
            pct = cnt / total_days * 100 if total_days > 0 else 0
            print(f"    {r}: {cnt} 日 ({pct:.0f}%)")
    else:
        print("  警告: 无指数数据，Phase 2 将使用默认市场状态参数")

    # ── 分步搜索各状态最优参数 ────────────────────────────
    # 对每个状态，搜索 (J 阈值, 止损) 组合
    # 评估方式：使用该状态的 config 对所有股票做单股回测，按该状态交易日比例加权

    best_regime_params: dict[str, dict] = {}
    regime_scores: dict[str, float] = {}

    for regime_name in ["SIDEWAYS", "BULL", "BEAR"]:
        regime_weight = regime_day_counts.get(regime_name, 0)
        if not has_index:
            regime_weight = 1  # 无指数时各状态等权

        print(f"\n  搜索 {regime_name} 最优参数 (权重={regime_weight})...")

        j_vals = j_ranges[regime_name]
        sl_vals = sl_ranges[regime_name]
        combos = [(j, sl) for j in j_vals for sl in sl_vals]
        print(f"    参数组合: {len(combos)}")

        best_score = -1.0
        best_j = j_vals[len(j_vals) // 2]
        best_sl = sl_vals[len(sl_vals) // 2]

        for j_th, sl_pct in combos:
            config = LoopConfig(
                j_threshold=j_th,
                stop_loss_pct=sl_pct,
                vol_shrink_threshold=base_params.get("vol_shrink", 0.8),
            )
            engine = ShaofuLoopEngine(config)

            results: list[ShaofuBacktestResult] = []
            for ts_code, klines in all_klines.items():
                trades = engine.run_stock(klines, ts_code=ts_code)
                if trades:
                    r = ShaofuBacktestResult(ts_code=ts_code, trades=trades)
                    _calc_metrics(r)
                    results.append(r)

            m = eval_results(results)
            s = score_metrics(m)

            if s > best_score:
                best_score = s
                best_j = j_th
                best_sl = sl_pct

        best_regime_params[regime_name] = {"j_threshold": best_j, "stop_loss_pct": best_sl}
        regime_scores[regime_name] = best_score
        print(f"    {regime_name} 最优: J={best_j}, SL={best_sl}, 得分={best_score:.2f}")

    # ── 汇总最终结果 ────────────────────────────────────────
    # 加权综合得分
    total_weight = sum(regime_day_counts.values()) or 1
    weighted_score = sum(
        regime_scores.get(r, 0) * regime_day_counts.get(r, 0) / total_weight for r in ["BULL", "SIDEWAYS", "BEAR"]
    )

    all_results: list[ParamScore] = [
        ParamScore(
            params={"regime_params": best_regime_params},
            win_rate=0,
            total_return=0,
            sharpe=0,
            max_dd=0,
            trades=0,
            score=weighted_score,
            extra_metrics={
                "regime_scores": regime_scores,
                "regime_day_counts": regime_day_counts,
            },
        )
    ]

    print("\n  Phase 2 最优市场状态参数:")
    for regime, params in best_regime_params.items():
        print(f"    {regime}: J={params['j_threshold']}, SL={params['stop_loss_pct']}")
    print(f"  加权综合得分: {weighted_score:.2f}")

    return all_results


# ============================================================================
# Phase 3: 仓位参数优化
# ============================================================================


def phase3_position_optimization(
    all_klines: dict[str, list[DailyData]],
    base_params: dict,
    regime_params: dict[str, dict],
    quick: bool = False,
) -> list[ParamScore]:
    """Phase 3: 仓位参数优化

    搜索 risk_per_trade × max_positions × regime_multiplier 的最优组合。
    使用 PositionManager 进行仓位计算。

    Args:
        all_klines: {ts_code: klines} 数据字典
        base_params: Phase 1 最优基础参数
        regime_params: Phase 2 最优市场状态参数
        quick: 是否使用精简参数空间

    Returns:
        按得分降序排列的 ParamScore 列表
    """
    print("\n" + "=" * 70)
    print("Phase 3: 仓位参数优化")
    print("=" * 70)

    if quick:
        risk_values = [0.01, 0.02, 0.03]
        max_pos_values = [3, 5, 8]
        regime_mult_values = [{"BULL": 1.0, "SIDEWAYS": 0.8, "BEAR": 0.5}]
    else:
        risk_values = [0.01, 0.015, 0.02, 0.025, 0.03]
        max_pos_values = [3, 5, 8, 10]
        regime_mult_values = [
            {"BULL": 1.0, "SIDEWAYS": 0.8, "BEAR": 0.5},
            {"BULL": 1.2, "SIDEWAYS": 1.0, "BEAR": 0.6},
            {"BULL": 1.5, "SIDEWAYS": 1.0, "BEAR": 0.4},
            {"BULL": 1.0, "SIDEWAYS": 1.0, "BEAR": 0.8},
        ]

    stock_list = list(all_klines.keys())
    ts_codes = stock_list
    days = min(500, max(250, len(list(all_klines.values())[0]) - 120 if all_klines else 250))

    # 构建基础配置
    base_config = LoopConfig(
        j_threshold=base_params.get("j_threshold", 12),
        stop_loss_pct=base_params.get("stop_loss_pct", -0.05),
        vol_shrink_threshold=base_params.get("vol_shrink", 0.8),
    )

    classifier = MarketRegimeClassifier()

    combos = [
        (risk, max_pos, rmult) for risk in risk_values for max_pos in max_pos_values for rmult in regime_mult_values
    ]
    print(f"参数组合数: {len(combos)} ({len(risk_values)}×{len(max_pos_values)}×{len(regime_mult_values)})")

    all_results: list[ParamScore] = []

    for idx, (risk, max_pos, rmult) in enumerate(combos, 1):
        pm = PositionManager(
            initial_capital=1_000_000,
            risk_per_trade=risk,
            max_positions=max_pos,
            regime_multipliers=rmult,
        )

        result_dict = backtest_shaofu_portfolio_integrated(
            ts_codes=ts_codes,
            days=days,
            base_config=base_config,
            regime_classifier=classifier,
            position_manager=pm,
            initial_capital=1_000_000,
            regime_params=regime_params,
        )

        m = evaluate_portfolio_result(result_dict)
        s = score_portfolio_metrics(m)

        all_results.append(
            ParamScore(
                params={
                    "risk_per_trade": risk,
                    "max_positions": max_pos,
                    "regime_multipliers": rmult,
                },
                win_rate=m["wr"],
                total_return=m["ret"],
                sharpe=m["sharpe"],
                max_dd=m["dd"],
                trades=m["trades"],
                score=s,
                extra_metrics={
                    "industry_hhi": m.get("industry_hhi", 0),
                    "position_util": m.get("position_util", 0),
                    "sub_period_stability": m.get("sub_period_stability", 0),
                },
            )
        )

        if idx % 5 == 0 or idx == len(combos):
            best_score = max(r.score for r in all_results)
            print(f"  [{idx}/{len(combos)}] 当前最佳得分: {best_score:.2f}")

    all_results.sort(key=lambda x: x.score, reverse=True)

    if all_results:
        best = all_results[0]
        print("\n  Phase 3 最优仓位参数:")
        print(f"    risk_per_trade:    {best.params['risk_per_trade']}")
        print(f"    max_positions:     {best.params['max_positions']}")
        print(f"    regime_multipliers: {best.params['regime_multipliers']}")
        print(f"    得分:              {best.score:.2f}")

    return all_results


# ============================================================================
# Phase 4: 行业分散化优化
# ============================================================================


def phase4_industry_optimization(
    all_klines: dict[str, list[DailyData]],
    base_params: dict,
    regime_params: dict[str, dict],
    position_params: dict,
    quick: bool = False,
) -> list[ParamScore]:
    """Phase 4: 行业分散化优化

    搜索 max_per_industry × 行业采样策略的最优组合。
    使用 IndustryFilter 进行行业约束。

    Args:
        all_klines: {ts_code: klines} 数据字典
        base_params: Phase 1 最优基础参数
        regime_params: Phase 2 最优市场状态参数
        position_params: Phase 3 最优仓位参数
        quick: 是否使用精简参数空间

    Returns:
        按得分降序排列的 ParamScore 列表
    """
    print("\n" + "=" * 70)
    print("Phase 4: 行业分散化优化")
    print("=" * 70)

    if quick:
        max_per_industry_values = [1, 2, 3]
        industry_pct_values = [0.2, 0.4]
    else:
        max_per_industry_values = [1, 2, 3, 4]
        industry_pct_values = [0.2, 0.3, 0.4, 0.5]

    stock_list = list(all_klines.keys())
    ts_codes = stock_list
    days = min(500, max(250, len(list(all_klines.values())[0]) - 120 if all_klines else 250))

    # 构建基础配置
    base_config = LoopConfig(
        j_threshold=base_params.get("j_threshold", 12),
        stop_loss_pct=base_params.get("stop_loss_pct", -0.05),
        vol_shrink_threshold=base_params.get("vol_shrink", 0.8),
    )

    classifier = MarketRegimeClassifier()

    # 仓位管理器（使用 Phase 3 最优参数）
    pm_base = PositionManager(
        initial_capital=1_000_000,
        risk_per_trade=position_params.get("risk_per_trade", 0.02),
        max_positions=position_params.get("max_positions", 5),
        regime_multipliers=position_params.get("regime_multipliers", {"BULL": 1.2, "SIDEWAYS": 1.0, "BEAR": 0.6}),
    )

    combos = [(mpi, ipct) for mpi in max_per_industry_values for ipct in industry_pct_values]
    print(f"参数组合数: {len(combos)} ({len(max_per_industry_values)}×{len(industry_pct_values)})")

    all_results: list[ParamScore] = []

    for idx, (mpi, ipct) in enumerate(combos, 1):
        # 每次迭代需要重置 PositionManager 状态
        pm = PositionManager(
            initial_capital=1_000_000,
            risk_per_trade=pm_base.risk_per_trade,
            max_positions=pm_base.max_positions,
            regime_multipliers=dict(pm_base.regime_multipliers),
        )

        ind_filter = IndustryFilter(
            max_per_industry=mpi,
            max_industry_pct=ipct,
        )

        result_dict = backtest_shaofu_portfolio_integrated(
            ts_codes=ts_codes,
            days=days,
            base_config=base_config,
            regime_classifier=classifier,
            position_manager=pm,
            industry_filter=ind_filter,
            initial_capital=1_000_000,
            regime_params=regime_params,
        )

        m = evaluate_portfolio_result(result_dict)
        s = score_portfolio_metrics(m)

        all_results.append(
            ParamScore(
                params={
                    "max_per_industry": mpi,
                    "max_industry_pct": ipct,
                },
                win_rate=m["wr"],
                total_return=m["ret"],
                sharpe=m["sharpe"],
                max_dd=m["dd"],
                trades=m["trades"],
                score=s,
                extra_metrics={
                    "industry_hhi": m.get("industry_hhi", 0),
                    "position_util": m.get("position_util", 0),
                    "sub_period_stability": m.get("sub_period_stability", 0),
                },
            )
        )

        if idx % 5 == 0 or idx == len(combos):
            best_score = max(r.score for r in all_results)
            print(f"  [{idx}/{len(combos)}] 当前最佳得分: {best_score:.2f}")

    all_results.sort(key=lambda x: x.score, reverse=True)

    if all_results:
        best = all_results[0]
        print("\n  Phase 4 最优行业参数:")
        print(f"    max_per_industry:  {best.params['max_per_industry']}")
        print(f"    max_industry_pct:  {best.params['max_industry_pct']}")
        print(f"    得分:              {best.score:.2f}")

    return all_results


# ============================================================================
# 输出格式化
# ============================================================================


def print_top_results(title: str, results: list[ParamScore], n: int = 10) -> None:
    """打印 Top N 结果

    Args:
        title: 标题
        results: ParamScore 列表
        n: 显示数量
    """
    print(f"\n{'=' * 70}")
    print(f"Top {n} {title}")
    print(f"{'=' * 70}\n")
    print(f"{'排名':<4} {'得分':<8} {'胜率':<8} {'收益':<10} {'夏普':<8} {'回撤':<8} {'交易':<8} 参数")
    print("-" * 90)
    for i, r in enumerate(results[:n], 1):
        params_str = ", ".join(f"{k}={v}" for k, v in r.params.items() if k != "regime_params")
        if "regime_params" in r.params:
            rp = r.params["regime_params"]
            regime_summary = "; ".join(
                f"{k}:J{v.get('j_threshold', '?')}/SL{v.get('stop_loss_pct', '?')}" for k, v in rp.items()
            )
            params_str = f"[{regime_summary}]"
        print(
            f"{i:<4} {r.score:<8.2f} {r.win_rate:<7.1%} {r.total_return:<+9.1%} "
            f"{r.sharpe:<8.2f} {r.max_dd:<7.1%} {r.trades:<8} {params_str}"
        )


# ============================================================================
# 主函数
# ============================================================================


def main() -> None:
    """多因子组合优化主入口

    命令行参数:
        --quick: 快速模式（减少参数组合数）
        --stocks N: 优化用股票数（默认 50）
        --days N: 回测天数（默认 500）
        --phases "1,2,3,4": 要运行的 Phase 编号（逗号分隔）
    """
    parser = argparse.ArgumentParser(description="多因子组合优化")
    parser.add_argument("--quick", action="store_true", help="快速模式（减少参数组合）")
    parser.add_argument("--stocks", type=int, default=50, help="优化用股票数（默认 50）")
    parser.add_argument("--days", type=int, default=500, help="回测天数（默认 500）")
    parser.add_argument("--phases", type=str, default="1,2,3,4", help="要运行的 Phase 编号（逗号分隔，默认 1,2,3,4）")
    args = parser.parse_args()

    # 解析 phases
    phases_to_run = [int(p.strip()) for p in args.phases.split(",")]

    stock_count = 20 if args.quick else args.stocks

    print("\n" + "=" * 70)
    print("多因子组合优化")
    print("=" * 70)
    print(f"  股票数: {stock_count}")
    print(f"  回测天数: {args.days}")
    print(f"  快速模式: {'是' if args.quick else '否'}")
    print(f"  运行 Phases: {phases_to_run}")

    start_time = time.time()

    # ── 加载数据 ──────────────────────────────────────────
    print("\n加载 K 线数据...")
    stocks = get_stocks(stock_count)
    if not stocks:
        print("错误: 无法获取股票列表。请确认 data/optimization_stocks.txt 存在。")
        sys.exit(1)

    all_klines = load_klines_batch(stocks, args.days)
    print(f"成功加载 {len(all_klines)} 只股票")

    if not all_klines:
        print("错误: 无法加载 K 线数据。请确认数据库已同步。")
        sys.exit(1)

    # ── Phase 结果容器 ────────────────────────────────────
    p1_results: list[ParamScore] = []
    p2_results: list[ParamScore] = []
    p3_results: list[ParamScore] = []
    p4_results: list[ParamScore] = []

    # 累计最优参数
    best_base_params: dict = {"j_threshold": 12, "stop_loss_pct": -0.05, "vol_shrink": 0.8}
    best_regime_params: dict[str, dict] = {
        "BULL": {"j_threshold": 18, "stop_loss_pct": -0.07},
        "SIDEWAYS": {"j_threshold": 12, "stop_loss_pct": -0.05},
        "BEAR": {"j_threshold": 5, "stop_loss_pct": -0.03},
    }
    best_position_params: dict = {
        "risk_per_trade": 0.02,
        "max_positions": 5,
        "regime_multipliers": {"BULL": 1.2, "SIDEWAYS": 1.0, "BEAR": 0.6},
    }
    best_industry_params: dict = {"max_per_industry": 2, "max_industry_pct": 0.4}

    # ── Phase 1: 基础参数网格搜索 ─────────────────────────
    if 1 in phases_to_run:
        p1_results = phase1_basic_grid_search(all_klines, quick=args.quick)
        print_top_results("Phase 1 — 基础参数网格搜索", p1_results)

        if p1_results:
            best = p1_results[0]
            best_base_params = {
                "j_threshold": best.params["j_threshold"],
                "stop_loss_pct": best.params["stop_loss_pct"],
                "vol_shrink": best.params["vol_shrink"],
            }
            print(f"\n  ★ Phase 1 最优基础参数: {best_base_params}")

    # ── Phase 2: 市场状态感知优化 ─────────────────────────
    if 2 in phases_to_run:
        p2_results = phase2_regime_aware_optimization(all_klines, best_base_params, quick=args.quick)
        print_top_results("Phase 2 — 市场状态感知优化", p2_results)

        if p2_results and "regime_params" in p2_results[0].params:
            best_regime_params = p2_results[0].params["regime_params"]
            print(f"\n  ★ Phase 2 最优市场状态参数: {best_regime_params}")

    # ── Phase 3: 仓位参数优化 ─────────────────────────────
    if 3 in phases_to_run:
        p3_results = phase3_position_optimization(all_klines, best_base_params, best_regime_params, quick=args.quick)
        print_top_results("Phase 3 — 仓位参数优化", p3_results)

        if p3_results:
            best_p = p3_results[0].params
            best_position_params = {
                "risk_per_trade": best_p["risk_per_trade"],
                "max_positions": best_p["max_positions"],
                "regime_multipliers": best_p["regime_multipliers"],
            }
            print(f"\n  ★ Phase 3 最优仓位参数: {best_position_params}")

    # ── Phase 4: 行业分散化优化 ───────────────────────────
    if 4 in phases_to_run:
        p4_results = phase4_industry_optimization(
            all_klines, best_base_params, best_regime_params, best_position_params, quick=args.quick
        )
        print_top_results("Phase 4 — 行业分散化优化", p4_results)

        if p4_results:
            best_i = p4_results[0].params
            best_industry_params = {
                "max_per_industry": best_i["max_per_industry"],
                "max_industry_pct": best_i["max_industry_pct"],
            }
            print(f"\n  ★ Phase 4 最优行业参数: {best_industry_params}")

    # ── 汇总 & 保存 ───────────────────────────────────────
    elapsed = time.time() - start_time

    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "stocks": stock_count,
            "days": args.days,
            "quick": args.quick,
            "phases": phases_to_run,
            "elapsed_seconds": round(elapsed, 1),
        },
        "best_params": {
            "base": best_base_params,
            "regime": best_regime_params,
            "position": best_position_params,
            "industry": best_industry_params,
        },
        "phase1_top10": [
            {
                "rank": i + 1,
                "score": r.score,
                "params": r.params,
                "wr": r.win_rate,
                "ret": r.total_return,
                "sharpe": r.sharpe,
                "dd": r.max_dd,
                "trades": r.trades,
            }
            for i, r in enumerate(p1_results[:10])
        ]
        if p1_results
        else [],
        "phase2_top10": [
            {
                "rank": i + 1,
                "score": r.score,
                "params": {k: v for k, v in r.params.items()},
                "wr": r.win_rate,
                "ret": r.total_return,
                "sharpe": r.sharpe,
                "dd": r.max_dd,
                "trades": r.trades,
                "extra": r.extra_metrics,
            }
            for i, r in enumerate(p2_results[:10])
        ]
        if p2_results
        else [],
        "phase3_top10": [
            {
                "rank": i + 1,
                "score": r.score,
                "params": r.params,
                "wr": r.win_rate,
                "ret": r.total_return,
                "sharpe": r.sharpe,
                "dd": r.max_dd,
                "trades": r.trades,
                "extra": r.extra_metrics,
            }
            for i, r in enumerate(p3_results[:10])
        ]
        if p3_results
        else [],
        "phase4_top10": [
            {
                "rank": i + 1,
                "score": r.score,
                "params": r.params,
                "wr": r.win_rate,
                "ret": r.total_return,
                "sharpe": r.sharpe,
                "dd": r.max_dd,
                "trades": r.trades,
                "extra": r.extra_metrics,
            }
            for i, r in enumerate(p4_results[:10])
        ]
        if p4_results
        else [],
    }

    output_path = Path("reports/optimization_multifactor_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print("✅ 多因子优化完成!")
    print(f"{'=' * 70}")
    print(f"  耗时:       {elapsed:.1f} 秒")
    print(f"  最优基础参数: {best_base_params}")
    print(f"  最优市场参数: {best_regime_params}")
    print(f"  最优仓位参数: {best_position_params}")
    print(f"  最优行业参数: {best_industry_params}")
    print(f"  结果保存:  {output_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
