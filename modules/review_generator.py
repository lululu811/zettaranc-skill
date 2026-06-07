#!/usr/bin/env python3
"""
自我改进系统 - 复盘报告生成模块

生成月度复盘报告，分析信号准确率、收益统计、策略表现
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.database import get_connection
from modules.improvement_logger import ImprovementLogger


class ReviewGenerator:
    """复盘报告生成器"""

    def __init__(self):
        """初始化复盘报告生成器"""
        self.logger = ImprovementLogger()

    def generate_monthly_review(self, review_month: str) -> dict[str, Any]:
        """
        生成月度复盘报告

        Args:
            review_month: 复盘月份（YYYY-MM）

        Returns:
            复盘报告
        """
        try:
            # 获取该月的所有跟踪记录
            with get_connection() as conn:
                cursor = conn.cursor()

                # 获取该月有记录的股票
                cursor.execute(
                    """
                    SELECT DISTINCT ts_code
                    FROM tracking_records_self
                    WHERE trade_date LIKE ?
                """,
                    (f"{review_month}%",),
                )

                tracked_stocks = [row["ts_code"] for row in cursor.fetchall()]

            if not tracked_stocks:
                return {"success": True, "message": f"{review_month} 没有跟踪记录", "reviews": []}

            reviews = []
            for ts_code in tracked_stocks:
                review = self._analyze_stock_performance(ts_code, review_month)
                if review:
                    reviews.append(review)

            # 生成策略表现统计
            strategy_stats = self._analyze_strategy_performance(review_month)

            # 记录复盘报告生成日志
            avg_return = sum(r.get("monthly_return", 0) for r in reviews) / len(reviews) if reviews else 0
            max_drawdown = max(r.get("max_drawdown", 0) for r in reviews) if reviews else 0
            total_buy_signals = sum(r.get("buy_signals_count", 0) for r in reviews)
            total_correct_buy_signals = sum(r.get("correct_buy_signals", 0) for r in reviews)

            self.logger.log_review_generation(
                review_month=review_month,
                total_stocks=len(reviews),
                avg_return=avg_return,
                max_drawdown=max_drawdown,
                buy_signals=total_buy_signals,
                correct_buy_signals=total_correct_buy_signals,
            )

            return {
                "success": True,
                "message": f"已生成 {review_month} 的复盘报告",
                "review_month": review_month,
                "reviews": reviews,
                "strategy_stats": strategy_stats,
                "total_stocks": len(reviews),
            }

        except Exception as e:
            return {"success": False, "message": f"生成复盘报告失败: {str(e)}"}

    def _analyze_stock_performance(self, ts_code: str, review_month: str) -> dict[str, Any] | None:
        """
        分析单只股票的月度表现

        Args:
            ts_code: 股票代码
            review_month: 复盘月份

        Returns:
            分析结果
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # 获取该月的所有记录
                cursor.execute(
                    """
                    SELECT * FROM tracking_records_self
                    WHERE ts_code = ? AND trade_date LIKE ?
                    ORDER BY trade_date
                """,
                    (ts_code, f"{review_month}%"),
                )

                records = [dict(row) for row in cursor.fetchall()]

                if not records:
                    return None

                # 计算月初和月末状态
                first_record = records[0]
                last_record = records[-1]

                start_price = first_record.get("close")
                end_price = last_record.get("close")
                start_j_value = first_record.get("j_value")
                end_j_value = last_record.get("j_value")
                start_signal = first_record.get("signal_type")
                end_signal = last_record.get("signal_type")

                # 计算月度收益率
                monthly_return = None
                if start_price and end_price and start_price > 0:
                    monthly_return = (end_price - start_price) / start_price * 100

                # 计算最大回撤和最大涨幅
                max_drawdown = 0
                max_gain = 0
                prices = [r.get("close") for r in records if r.get("close")]

                if len(prices) >= 2:
                    peak = prices[0]
                    for price in prices:
                        if price > peak:
                            peak = price
                        drawdown = (peak - price) / peak * 100
                        if drawdown > max_drawdown:
                            max_drawdown = drawdown

                    trough = prices[0]
                    for price in prices:
                        if price < trough:
                            trough = price
                        gain = (price - trough) / trough * 100
                        if gain > max_gain:
                            max_gain = gain

                # 统计信号
                buy_signals = [r for r in records if r.get("signal_type") == "BUY"]
                sell_signals = [r for r in records if r.get("signal_type") == "SELL"]

                # 计算信号准确率（简化版本）
                correct_buy_signals = 0
                for i, record in enumerate(records):
                    if record.get("signal_type") == "BUY":
                        # 检查买入后3天内是否上涨
                        if i + 3 < len(records):
                            future_price = records[i + 3].get("close")
                            current_price = record.get("close")
                            if future_price and current_price and future_price > current_price:
                                correct_buy_signals += 1

                correct_sell_signals = 0
                for i, record in enumerate(records):
                    if record.get("signal_type") == "SELL":
                        # 检查卖出后3天内是否下跌
                        if i + 3 < len(records):
                            future_price = records[i + 3].get("close")
                            current_price = record.get("close")
                            if future_price and current_price and future_price < current_price:
                                correct_sell_signals += 1

                # 生成复盘总结
                review_summary = self._generate_review_summary(
                    ts_code,
                    monthly_return,
                    max_drawdown,
                    max_gain,
                    len(buy_signals),
                    len(sell_signals),
                    correct_buy_signals,
                    correct_sell_signals,
                )

                # 生成经验教训
                lessons_learned = self._generate_lessons_learned(
                    ts_code, monthly_return, max_drawdown, len(buy_signals), correct_buy_signals
                )

                # 生成策略调整建议
                strategy_adjustments = self._generate_adjustment_suggestions(
                    ts_code, monthly_return, max_drawdown, len(buy_signals), correct_buy_signals
                )

                return {
                    "ts_code": ts_code,
                    "review_month": review_month,
                    "start_price": start_price,
                    "start_j_value": start_j_value,
                    "start_signal": start_signal,
                    "end_price": end_price,
                    "end_j_value": end_j_value,
                    "end_signal": end_signal,
                    "monthly_return": monthly_return,
                    "max_drawdown": max_drawdown,
                    "max_gain": max_gain,
                    "buy_signals_count": len(buy_signals),
                    "sell_signals_count": len(sell_signals),
                    "correct_buy_signals": correct_buy_signals,
                    "correct_sell_signals": correct_sell_signals,
                    "review_summary": review_summary,
                    "lessons_learned": lessons_learned,
                    "strategy_adjustments": strategy_adjustments,
                }

        except Exception as e:
            print(f"分析 {ts_code} 失败: {e}")
            return None

    def _analyze_strategy_performance(self, review_month: str) -> list[dict[str, Any]]:
        """
        分析策略表现

        Args:
            review_month: 复盘月份

        Returns:
            策略表现列表
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # 获取该月的所有记录
                cursor.execute(
                    """
                    SELECT signal_type, signal_score, signal_reason, close
                    FROM tracking_records_self
                    WHERE trade_date LIKE ? AND signal_type IS NOT NULL
                """,
                    (f"{review_month}%",),
                )

                records = [dict(row) for row in cursor.fetchall()]

                # 按信号类型统计
                signal_stats = {}
                for record in records:
                    signal_type = record.get("signal_type")
                    if signal_type not in signal_stats:
                        signal_stats[signal_type] = {"total": 0, "correct": 0, "scores": []}

                    signal_stats[signal_type]["total"] += 1
                    if record.get("signal_score"):
                        signal_stats[signal_type]["scores"].append(record["signal_score"])

                # 计算准确率
                strategy_performance = []
                for signal_type, stats in signal_stats.items():
                    accuracy_rate = 0
                    if stats["total"] > 0:
                        accuracy_rate = stats["correct"] / stats["total"] * 100

                    avg_score = 0
                    if stats["scores"]:
                        avg_score = sum(stats["scores"]) / len(stats["scores"])

                    strategy_performance.append(
                        {
                            "strategy_name": signal_type,
                            "review_month": review_month,
                            "total_signals": stats["total"],
                            "correct_signals": stats["correct"],
                            "accuracy_rate": accuracy_rate,
                            "avg_score": avg_score,
                        }
                    )

                return strategy_performance

        except Exception as e:
            print(f"分析策略表现失败: {e}")
            return []

    def _generate_review_summary(
        self,
        ts_code: str,
        monthly_return: float | None,
        max_drawdown: float,
        max_gain: float,
        buy_signals_count: int,
        sell_signals_count: int,
        correct_buy_signals: int,
        correct_sell_signals: int,
    ) -> str:
        """生成复盘总结"""
        summary_parts = []

        # 收益总结
        if monthly_return is not None:
            if monthly_return > 0:
                summary_parts.append(f"月度收益：+{monthly_return:.2f}%")
            else:
                summary_parts.append(f"月度收益：{monthly_return:.2f}%")

        # 风险总结
        if max_drawdown > 10:
            summary_parts.append(f"最大回撤：{max_drawdown:.2f}%（较高）")
        elif max_drawdown > 5:
            summary_parts.append(f"最大回撤：{max_drawdown:.2f}%（中等）")
        else:
            summary_parts.append(f"最大回撤：{max_drawdown:.2f}%（较低）")

        # 信号总结
        if buy_signals_count > 0:
            buy_accuracy = correct_buy_signals / buy_signals_count * 100
            summary_parts.append(f"买入信号：{buy_signals_count}次，准确率{buy_accuracy:.1f}%")

        if sell_signals_count > 0:
            sell_accuracy = correct_sell_signals / sell_signals_count * 100
            summary_parts.append(f"卖出信号：{sell_signals_count}次，准确率{sell_accuracy:.1f}%")

        return "；".join(summary_parts)

    def _generate_lessons_learned(
        self,
        ts_code: str,
        monthly_return: float | None,
        max_drawdown: float,
        buy_signals_count: int,
        correct_buy_signals: int,
    ) -> str:
        """生成经验教训"""
        lessons = []

        # 收益教训
        if monthly_return is not None:
            if monthly_return < -5:
                lessons.append("月度亏损较大，需要加强止损纪律")
            elif monthly_return > 10:
                lessons.append("月度收益良好，但要注意止盈")

        # 风险教训
        if max_drawdown > 15:
            lessons.append("最大回撤过大，需要优化仓位管理")

        # 信号教训
        if buy_signals_count > 0:
            buy_accuracy = correct_buy_signals / buy_signals_count * 100
            if buy_accuracy < 50:
                lessons.append("买入信号准确率低，需要优化买入条件")
            elif buy_accuracy > 80:
                lessons.append("买入信号准确率高，策略有效")

        if not lessons:
            lessons.append("表现中规中矩，继续观察")

        return "；".join(lessons)

    def _generate_adjustment_suggestions(
        self,
        ts_code: str,
        monthly_return: float | None,
        max_drawdown: float,
        buy_signals_count: int,
        correct_buy_signals: int,
    ) -> str:
        """生成策略调整建议"""
        suggestions = []

        # 收益调整
        if monthly_return is not None:
            if monthly_return < -5:
                suggestions.append("收紧止损条件，降低单笔亏损")
            elif monthly_return > 10:
                suggestions.append("考虑增加仓位，扩大收益")

        # 风险调整
        if max_drawdown > 15:
            suggestions.append("降低单票仓位，分散风险")

        # 信号调整
        if buy_signals_count > 0:
            buy_accuracy = correct_buy_signals / buy_signals_count * 100
            if buy_accuracy < 50:
                suggestions.append("增加买入确认条件，提高信号质量")
            elif buy_accuracy > 80:
                suggestions.append("当前买入条件有效，可适当放宽")

        if not suggestions:
            suggestions.append("当前策略表现稳定，无需调整")

        return "；".join(suggestions)

    def save_review_to_database(self, review_data: dict[str, Any]) -> bool:
        """
        保存复盘结果到数据库

        Args:
            review_data: 复盘数据

        Returns:
            是否保存成功
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # 保存月度复盘
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO monthly_reviews_self (
                        review_month, ts_code, start_price, start_j_value, start_signal,
                        end_price, end_j_value, end_signal, monthly_return, max_drawdown, max_gain,
                        buy_signals_count, sell_signals_count, correct_buy_signals, correct_sell_signals,
                        review_summary, lessons_learned, strategy_adjustments
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        review_data.get("review_month"),
                        review_data.get("ts_code"),
                        review_data.get("start_price"),
                        review_data.get("start_j_value"),
                        review_data.get("start_signal"),
                        review_data.get("end_price"),
                        review_data.get("end_j_value"),
                        review_data.get("end_signal"),
                        review_data.get("monthly_return"),
                        review_data.get("max_drawdown"),
                        review_data.get("max_gain"),
                        review_data.get("buy_signals_count"),
                        review_data.get("sell_signals_count"),
                        review_data.get("correct_buy_signals"),
                        review_data.get("correct_sell_signals"),
                        review_data.get("review_summary"),
                        review_data.get("lessons_learned"),
                        review_data.get("strategy_adjustments"),
                    ),
                )

                conn.commit()
                return True

        except Exception as e:
            print(f"保存复盘数据失败: {e}")
            return False

    def save_strategy_performance(self, strategy_data: dict[str, Any]) -> bool:
        """
        保存策略表现到数据库

        Args:
            strategy_data: 策略数据

        Returns:
            是否保存成功
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO strategy_performance_self (
                        strategy_name, review_month, total_signals, correct_signals, accuracy_rate,
                        avg_return, max_return, min_return, win_rate,
                        avg_drawdown, max_drawdown, sharpe_ratio,
                        strengths, weaknesses, adjustments
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        strategy_data.get("strategy_name"),
                        strategy_data.get("review_month"),
                        strategy_data.get("total_signals"),
                        strategy_data.get("correct_signals"),
                        strategy_data.get("accuracy_rate"),
                        strategy_data.get("avg_return"),
                        strategy_data.get("max_return"),
                        strategy_data.get("min_return"),
                        strategy_data.get("win_rate"),
                        strategy_data.get("avg_drawdown"),
                        strategy_data.get("max_drawdown"),
                        strategy_data.get("sharpe_ratio"),
                        strategy_data.get("strengths"),
                        strategy_data.get("weaknesses"),
                        strategy_data.get("adjustments"),
                    ),
                )

                conn.commit()
                return True

        except Exception as e:
            print(f"保存策略表现失败: {e}")
            return False

    def get_historical_reviews(self, limit: int = 12) -> list[dict[str, Any]]:
        """
        获取历史复盘记录

        Args:
            limit: 返回记录数

        Returns:
            历史复盘列表
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT DISTINCT review_month
                    FROM monthly_reviews_self
                    ORDER BY review_month DESC
                    LIMIT ?
                """,
                    (limit,),
                )

                return [row["review_month"] for row in cursor.fetchall()]

        except Exception as e:
            print(f"获取历史复盘失败: {e}")
            return []


def main():
    """测试函数"""
    generator = ReviewGenerator()

    # 测试生成月度复盘
    print("\n=== 测试生成月度复盘 ===")
    result = generator.generate_monthly_review("2026-05")
    print(f"结果：{result}")

    # 测试获取历史复盘
    print("\n=== 测试获取历史复盘 ===")
    history = generator.get_historical_reviews()
    print(f"历史复盘：{history}")


if __name__ == "__main__":
    main()
