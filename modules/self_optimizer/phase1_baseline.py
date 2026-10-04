"""Phase 1: baseline score from monthly_reviews_self + LLM judge stub."""

from __future__ import annotations

from typing import Any

from modules.database import get_connection
from modules.self_optimizer.scorer import compute_total_score


def _fetch_aggregate_stats(review_months: int) -> dict[str, Any]:
    """读最近 N 个月 monthly_reviews_self 聚合统计."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                AVG(monthly_return) as avg_return,
                AVG(max_drawdown) as avg_drawdown,
                SUM(buy_signals_count) as total_buy,
                SUM(correct_buy_signals) as total_correct,
                COUNT(DISTINCT ts_code) as stock_count
            FROM (
                SELECT * FROM monthly_reviews_self
                ORDER BY review_month DESC
                LIMIT ?
            )
            """,
            (review_months * 30,),  # 近似 30 天/月
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return {
                "avg_return": 0.0,
                "avg_drawdown": 0.0,
                "accuracy_rate": 0.0,
                "stock_count": 0,
            }
        avg_return, avg_drawdown, total_buy, total_correct, stock_count = row
        accuracy_rate = (total_correct / total_buy * 100) if total_buy and total_buy > 0 else 0.0
        return {
            "avg_return": float(avg_return or 0.0),
            "avg_drawdown": float(avg_drawdown or 0.0),
            "accuracy_rate": float(accuracy_rate),
            "stock_count": int(stock_count or 0),
        }


def phase1_baseline(review_months: int = 3) -> float:
    """计算基线分数 (0-100). V2 仅基于 trading 历史评估."""
    stats = _fetch_aggregate_stats(review_months)
    total, _ = compute_total_score("baseline", stats, proposed={})
    return total
