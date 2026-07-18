#!/usr/bin/env python3
"""少妇战法 v1.0 验收参数寻优（v3.7.1）

用 5 轮 hill-climb 在 100 股 × 240 天 + Walk-forward 上跑
V10VerifyScorer，按 passed_count + 0.1*sharpe 适应度爬山，
最佳参数集写回 param_registry:shaofu_v1。

用法：
  python -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100
  python -m scripts.optimize_for_v10_verify --smoke   # 1 round × 5 stocks
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# 让 `python -m scripts.optimize_for_v10_verify` 能跑（项目根目录加 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.loop_engine import LoopConfig  # noqa: E402
from modules.verify.portfolio_engine import PortfolioConfig, MarketAdaptiveConfig  # noqa: E402
from modules.verify.registry_writer import (  # noqa: E402
    write_optimization_to_registry,
)
from modules.verify.scorer import V10VerifyScorer, V10ScoreResult, LOOP_CONFIG_FIELDS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LoopConfig 字段的 (min, max, step) 元组（用于爬山边界）
PARAM_SPACE = {
    "j_threshold": (3, 20, 1),
    "stop_loss_pct": (-0.10, -0.01, 0.01),
    "vol_shrink_threshold": (0.5, 1.0, 0.1),
    "bbi_break_days": (1, 5, 1),
    "min_holding_days": (2, 7, 1),
    "lu_half": (0, 1, 1),  # bool 当 int 用
    "position_pct": (0.10, 0.50, 0.05),
}


def _clip(name: str, value: float) -> int | float | bool:
    lo, hi, step = PARAM_SPACE[name]
    v = max(lo, min(hi, value))
    v = round((v - lo) / step) * step + lo
    v = max(lo, min(hi, v))
    if name in ("lu_half",):
        return bool(int(v))
    return v


def _mutate(base: dict, rng: random.Random, n_mutations: int = 2) -> dict:
    """随机挑选 n_mutations 个字段微扰"""
    new = dict(base)
    keys = list(PARAM_SPACE.keys())
    picked = rng.sample(keys, k=min(n_mutations, len(keys)))
    for k in picked:
        lo, hi, step = PARAM_SPACE[k]
        delta = rng.choice([-2, -1, 1, 2]) * step
        new[k] = _clip(k, new.get(k, lo) + delta)
    return new


def _load_pool(args: argparse.Namespace, stocks_arg: int | None) -> list[str]:
    """加载股票池：默认使用多指标分组选股池，可回退到旧版流动性/趋势池"""
    from modules.verify.pool import (
        load_v10_stock_pool,
        load_v10_stock_pool_multi_criteria,
    )

    limit = stocks_arg or 100

    if getattr(args, "no_screener_pool", False):
        return load_v10_stock_pool(limit=limit)

    pool_criteria = getattr(args, "pool_criteria", None)
    if pool_criteria:
        criteria_list = [c.strip() for c in pool_criteria.split(",") if c.strip()]
        return load_v10_stock_pool_multi_criteria(
            groups={"custom": criteria_list},
            limit=limit,
            mode=args.pool_mode,
        )

    groups = [g.strip() for g in args.pool_groups.split(",") if g.strip()]
    return load_v10_stock_pool_multi_criteria(
        groups=groups,
        limit=limit,
        mode=args.pool_mode,
    )


def run_hillclimb(
    scorer: V10VerifyScorer,
    initial: dict,
    rounds: int,
    rng: random.Random,
) -> tuple[dict, V10ScoreResult, list[dict]]:
    """返回 (best_params, best_score, history)"""
    current = dict(initial)
    current_result = scorer.score(current)
    history: list[dict] = [
        {
            "round": 0,
            "kind": "baseline",
            "params": current,
            "fit": current_result.fit,
            "passed_count": current_result.passed_count,
        }
    ]
    logger.info(
        "基线 fit=%.3f passed=%d/%d sharpe=%.3f calmar=%.3f annret=%.3f",
        current_result.fit,
        current_result.passed_count,
        current_result.total_count,
        getattr(current_result, "sharpe", 0.0),
        getattr(current_result, "calmar", 0.0),
        getattr(current_result, "annualized_return", 0.0),
    )

    best = current
    best_result = current_result
    no_improve = 0

    for r in range(1, rounds + 1):
        candidate = _mutate(current, rng)
        candidate_result = scorer.score(candidate)
        history.append(
            {
                "round": r,
                "kind": "candidate",
                "params": candidate,
                "fit": candidate_result.fit,
                "passed_count": candidate_result.passed_count,
                "error": candidate_result.error,
            }
        )

        if candidate_result.fit > current_result.fit:
            current = candidate
            current_result = candidate_result
            no_improve = 0
            status = "keep"
        else:
            no_improve += 1
            status = "revert"

        if candidate_result.fit > best_result.fit:
            best = candidate
            best_result = candidate_result

        logger.info(
            "round %d: %s fit=%.3f passed=%d/%d sharpe=%.3f calmar=%.3f annret=%.3f (best fit=%.3f p=%d/%d)",
            r,
            status,
            candidate_result.fit,
            candidate_result.passed_count,
            candidate_result.total_count,
            getattr(candidate_result, "sharpe", 0.0),
            getattr(candidate_result, "calmar", 0.0),
            getattr(candidate_result, "annualized_return", 0.0),
            best_result.fit,
            best_result.passed_count,
            best_result.total_count,
        )

        if no_improve >= 3:
            logger.info("收敛于 round %d", r)
            break

    return best, best_result, history


def main() -> int:
    parser = argparse.ArgumentParser(description="v1.0 验收参数寻优")
    parser.add_argument("--rounds", type=int, default=5, help="爬山轮数（默认 5）")
    parser.add_argument("--stocks", type=int, default=200, help="股票池大小（默认 200）")
    parser.add_argument("--days", type=int, default=240, help="回测天数（默认 240）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--smoke", action="store_true", help="冒烟模式：1 轮 × 5 股")
    parser.add_argument("--extras", type=int, default=0, help="额外补充轮数")
    parser.add_argument(
        "--single-stock-mode",
        action="store_true",
        help="使用单股独立回测模式（对照用，默认关闭）",
    )
    parser.add_argument(
        "--pool-groups",
        type=str,
        default="left_pullback,stage_accumulation",
        help="选股分组，逗号分隔（默认：left_pullback,stage_accumulation）",
    )
    parser.add_argument(
        "--pool-mode",
        type=str,
        default="union",
        choices=["union", "intersection"],
        help="分组合并模式：union=并集（默认），intersection=交集",
    )
    parser.add_argument(
        "--no-screener-pool",
        action="store_true",
        help="禁用 screener 多指标选股池，回退到旧版流动性/趋势池",
    )
    parser.add_argument(
        "--pool-criteria",
        type=str,
        default=None,
        help="直接指定 criteria 列表，逗号分隔（绕过分组，例如 b1,super_b1）",
    )
    parser.add_argument(
        "--adaptive-regime",
        action="store_true",
        help="开启市场环境自适应仓位控制（v3.8.0）",
    )
    parser.add_argument(
        "--adaptive-weak-off",
        action="store_true",
        help="弱势日允许轻仓开新仓（默认禁止新买入）",
    )
    args = parser.parse_args()

    if args.smoke:
        args.rounds = 1
        args.stocks = 5
        # smoke 以快速验证为主，默认关闭 screener 多指标选股池，避免无数据时分析 500 只股票超时
        args.no_screener_pool = True

    rng = random.Random(args.seed)

    pool = _load_pool(args, args.stocks)
    if not pool:
        logger.error("无法加载股票池（数据库可能未初始化）")
        return 1
    logger.info("股票池: %d 只", len(pool))

    portfolio_config = None
    if args.adaptive_regime:
        portfolio_config = PortfolioConfig(
            initial_capital=1_000_000.0,
            max_positions=5,
            position_pct=LoopConfig().position_pct,
            adaptive=MarketAdaptiveConfig(
                enabled=True,
                weak_no_new_entries=not args.adaptive_weak_off,
            ),
        )

    scorer = V10VerifyScorer(
        stock_pool=pool,
        days=args.days,
        walk_forward=True,
        wf_train_days=120,
        wf_test_days=60,
        use_portfolio_engine=not getattr(args, "single_stock_mode", False),
        portfolio_config=portfolio_config,
    )

    baseline_params = {f: getattr(LoopConfig(), f) for f in LOOP_CONFIG_FIELDS}
    baseline_params["lu_half"] = bool(baseline_params["lu_half"])

    total_rounds = args.rounds + args.extras
    t0 = time.time()
    best_params, best_result, history = run_hillclimb(
        scorer=scorer,
        initial=baseline_params,
        rounds=total_rounds,
        rng=rng,
    )
    elapsed = time.time() - t0

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_dir = Path("optimization_drafts")
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"v10_verify_{run_id}.json"
    draft_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "elapsed_sec": elapsed,
                "rounds": total_rounds,
                "stocks": len(pool),
                "baseline_params": baseline_params,
                "best_params": best_params,
                "best_fit": best_result.fit,
                "best_passed_count": best_result.passed_count,
                "best_total_count": best_result.total_count,
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("中间产物：%s (%.1f s)", draft_path, elapsed)

    write_optimization_to_registry(
        optimization_results={"best_params": best_params},
        strategy_name="shaofu_v1",
    )
    logger.info(
        "已写回 param_registry:shaofu_v1 → fit=%.3f passed=%d/%d (calmar=%.3f, annret=%.3f)",
        best_result.fit,
        best_result.passed_count,
        best_result.total_count,
        getattr(best_result, "calmar", 0.0),
        getattr(best_result, "annualized_return", 0.0),
    )

    print(f"PASSED: {best_result.passed_count}/{best_result.total_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
