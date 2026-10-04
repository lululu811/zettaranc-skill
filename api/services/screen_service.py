"""选股筛选服务"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 策略别名映射：单一事实来源 modules/screener/aliases.py（CLI 侧同源）
from modules.screener.aliases import STRATEGY_ALIAS, STRATEGY_DESCRIPTIONS  # noqa: E402

def _param_group(criteria: str) -> str:
    """param_registry 中的参数组名与 criteria 同名（simple_perfect_1/2/3 各自成组）"""
    return criteria


def _param_specs(criteria: str) -> list[dict[str, Any]]:
    """取该策略在 param_registry 中注册的可调参数（含默认值与取值范围）"""
    try:
        from modules.self_optimizer.param_registry import get_registry

        group = get_registry().get(_param_group(criteria))
        if not group:
            return []
        return [
            {
                "name": p.name,
                "default": p.default,
                "min": p.min,
                "max": p.max,
                "step": p.step,
                "description": p.description,
            }
            for p in group.params.values()
        ]
    except ImportError as e:
        logger.warning("[screen] 参数注册表不可用: %s", e)
        return []


def get_strategies() -> list[dict]:
    """列出所有可用策略（含可调参数定义）"""
    return [
        {
            "alias": alias,
            "criteria": criteria,
            "description": STRATEGY_DESCRIPTIONS.get(alias, ""),
            "params": _param_specs(criteria),
        }
        for alias, criteria in STRATEGY_ALIAS.items()
    ]


def _scanned_count(limit: int) -> int:
    """本次实际扫描的股票数（limit=0 时为全市场）"""
    try:
        from modules.screener.data import get_all_stocks

        pool = len(get_all_stocks())
    except Exception as e:  # 取不到就退回 limit 本身，不让统计失败影响主流程
        logger.warning("[screen] 无法获取股票池规模: %s", e)
        return max(limit, 0)
    return pool if limit <= 0 else min(limit, pool)


def run_screen(
    strategy: str,
    limit: int = 100,
    use_parallel: bool = True,
    params: dict[str, Any] | None = None,
    top: int = 0,
) -> dict:
    """执行选股筛选（支持运行时覆盖策略参数）

    Args:
        limit: 扫描多少只股票（0 = 全市场，股票池按 ts_code 排序取前 N 只）
        top: 返回条数上限，0 = 返回全部命中
    """
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(strategy, strategy.lower())
    overrides = {k: v for k, v in (params or {}).items() if v is not None}

    def _run() -> list:
        return screen_stocks(
            criteria=criteria,
            max_stocks=limit,
            use_parallel=use_parallel,
        )

    if overrides:
        try:
            from modules.self_optimizer.param_registry import get_registry, using_params

            group = _param_group(criteria)
            if group in get_registry():
                # 只接受已注册的参数，避免前端传入任意键
                allowed = get_registry()[group].params
                clean = {k: v for k, v in overrides.items() if k in allowed}
                with using_params({group: clean}):
                    scores = _run()
                overrides = clean
            else:
                scores = _run()
        except (ImportError, TypeError, ValueError) as e:
            logger.warning("[screen] 参数覆盖失败，按默认值运行: %s", e)
            scores = _run()
    else:
        scores = _run()

    matched = len(scores)
    shown = scores[:top] if top > 0 else scores

    stocks = []
    for s in shown:
        stocks.append({
            "ts_code": s.ts_code,
            "name": s.name,
            "score": round(s.score, 1),
            "b1_score": round(s.b1_score, 1),
            "trend_score": round(s.trend_score, 1),
            "volume_score": round(s.volume_score, 1),
            "risk_score": round(s.risk_score, 1),
            "rating": s.rating,
            "reasons": s.reasons,
            "warnings": s.warnings,
        })

    return {
        "strategy": strategy,
        "criteria": criteria,
        "count": len(stocks),
        "scanned": _scanned_count(limit),
        "matched": matched,
        "params": overrides,
        "stocks": stocks,
    }
