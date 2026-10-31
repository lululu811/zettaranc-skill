"""选股筛选服务"""

import logging

logger = logging.getLogger(__name__)

# 策略别名映射（与 cli.py 保持一致）
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

STRATEGY_DESCRIPTIONS = {
    "B1": "B1 买点 — J 值超卖 + 缩量回调至 BBI 附近",
    "B2": "B2 确认 — B1 后放量长阳突破",
    "B3": "B3 共识 — B2 后小阳线确认",
    "完美图形": "完美图形 — BBI 之上 + 缩量整理 + 均线多头",
    "超级B1": "超级 B1 — 多条件叠加的极强 B1",
    "长安战法": "长安战法 — B1 + 放量长阳 + 缩量分歧转一致",
    "建仓波": "建仓波 — 三波理论中的建仓阶段",
    "吸筹": "吸筹 — 麒麟会吸筹阶段特征",
    "安全": "安全 — 低风险综合筛选",
    "超跌": "超跌 — RSI/WR 超卖 + 偏离均线",
    "突破": "突破 — 放量突破关键阻力位",
}


def get_strategies() -> list[dict]:
    """列出所有可用策略"""
    return [
        {"alias": alias, "criteria": criteria, "description": STRATEGY_DESCRIPTIONS.get(alias, "")}
        for alias, criteria in STRATEGY_ALIAS.items()
    ]


def run_screen(strategy: str, limit: int = 20, use_parallel: bool = True) -> dict:
    """执行选股筛选"""
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(strategy, strategy.lower())
    scores = screen_stocks(
        criteria=criteria,
        max_stocks=limit,
        use_parallel=use_parallel,
    )

    stocks = []
    for s in scores[:limit]:
        stocks.append(
            {
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
            }
        )

    return {
        "strategy": strategy,
        "criteria": criteria,
        "count": len(stocks),
        "stocks": stocks,
    }
