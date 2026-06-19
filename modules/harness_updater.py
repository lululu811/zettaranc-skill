#!/usr/bin/env python3
"""
Harness 层集成模块

根据复盘结果自动更新 Guardrails
"""

from datetime import datetime, timedelta
from typing import Optional, Any

from modules.database import get_connection
from modules.improvement_logger import ImprovementLogger


class HarnessUpdater:
    """Harness 层更新器"""

    def __init__(self):
        """初始化 Harness 更新器"""
        self.logger = ImprovementLogger()

    def analyze_strategy_performance(self, review_month: str | None = None) -> dict[str, Any]:
        """
        分析策略表现

        Args:
            review_month: 复盘月份（默认最新月份）

        Returns:
            策略表现分析结果
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # 获取最新的复盘月份
                if not review_month:
                    cursor.execute("""
                        SELECT DISTINCT review_month
                        FROM monthly_reviews_self
                        ORDER BY review_month DESC
                        LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        review_month = row[0]
                    else:
                        return {"success": False, "message": "没有复盘数据"}

                # 分析各策略的表现（从 tracking_pool_self 获取策略标签）
                cursor.execute(
                    """
                    SELECT
                        p.strategy_tags,
                        COUNT(*) as stock_count,
                        AVG(r.monthly_return) as avg_return,
                        AVG(r.max_drawdown) as avg_drawdown,
                        SUM(r.buy_signals_count) as total_buy_signals,
                        SUM(r.correct_buy_signals) as correct_buy_signals
                    FROM monthly_reviews_self r
                    JOIN tracking_pool_self p ON r.ts_code = p.ts_code
                    WHERE r.review_month = ?
                    GROUP BY p.strategy_tags
                """,
                    (review_month,),
                )

                strategy_stats = []
                for row in cursor.fetchall():
                    strategy_tags = row[0]
                    stock_count = row[1]
                    avg_return = row[2]
                    avg_drawdown = row[3]
                    total_buy_signals = row[4]
                    correct_buy_signals = row[5]

                    # 计算买入信号准确率
                    accuracy_rate = 0
                    if total_buy_signals > 0:
                        accuracy_rate = correct_buy_signals / total_buy_signals * 100

                    # 判断策略状态
                    status = "normal"
                    warning = ""

                    if avg_return < -10:
                        status = "poor"
                        warning = f"策略 {strategy_tags} 近期表现不佳（平均收益 {avg_return:.1f}%），谨慎使用"
                    elif avg_drawdown > 20:
                        status = "risky"
                        warning = f"策略 {strategy_tags} 风险较高（平均回撤 {avg_drawdown:.1f}%），建议降低仓位"
                    elif avg_return > 10 and accuracy_rate > 50:
                        status = "good"
                        warning = f"策略 {strategy_tags} 近期表现良好（平均收益 {avg_return:.1f}%），可适当关注"

                    strategy_stats.append(
                        {
                            "strategy_tags": strategy_tags,
                            "stock_count": stock_count,
                            "avg_return": avg_return,
                            "avg_drawdown": avg_drawdown,
                            "total_buy_signals": total_buy_signals,
                            "correct_buy_signals": correct_buy_signals,
                            "accuracy_rate": accuracy_rate,
                            "status": status,
                            "warning": warning,
                        }
                    )

                return {"success": True, "review_month": review_month, "strategy_stats": strategy_stats}

        except Exception as e:
            return {"success": False, "message": f"分析策略表现失败: {str(e)}"}

    def generate_guardrails_update(self, analysis_result: dict[str, Any]) -> dict[str, Any]:
        """
        生成 Guardrails 更新建议

        Args:
            analysis_result: 策略表现分析结果

        Returns:
            Guardrails 更新建议
        """
        try:
            if not analysis_result.get("success"):
                return analysis_result

            review_month = analysis_result.get("review_month")
            strategy_stats = analysis_result.get("strategy_stats", [])

            # 生成更新建议
            updates = []

            for stat in strategy_stats:
                strategy_tags = stat.get("strategy_tags")
                status = stat.get("status")
                warning = stat.get("warning")

                if status == "poor":
                    updates.append(
                        {
                            "type": "warning",
                            "strategy": strategy_tags,
                            "message": warning,
                            "action": "在回答中谨慎使用该策略",
                        }
                    )
                elif status == "risky":
                    updates.append(
                        {
                            "type": "limit",
                            "strategy": strategy_tags,
                            "message": warning,
                            "action": "在回答中提示风险，建议降低仓位",
                        }
                    )
                elif status == "good":
                    updates.append(
                        {
                            "type": "recommend",
                            "strategy": strategy_tags,
                            "message": warning,
                            "action": "在回答中适当推荐该策略",
                        }
                    )

            return {"success": True, "review_month": review_month, "updates": updates, "total_updates": len(updates)}

        except Exception as e:
            return {"success": False, "message": f"生成 Guardrails 更新建议失败: {str(e)}"}

    def apply_guardrails_updates(self, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """
        应用 Guardrails 更新

        Args:
            updates: 更新建议列表

        Returns:
            应用结果
        """
        try:
            # 这里可以实现自动更新 SKILL.md 的逻辑
            # 目前先返回更新建议，供人工审核

            applied_count = 0
            for update in updates:
                # 记录更新建议
                print(f"[{update['type'].upper()}] {update['message']}")
                applied_count += 1

            # 记录 Harness 层更新日志
            warnings = [update.get("message", "") for update in updates if update.get("type") == "warning"]
            self.logger.log_harness_update(
                review_month=updates[0].get("review_month", "") if updates else "",
                updates_count=applied_count,
                warnings=warnings,
            )

            return {
                "success": True,
                "applied_count": applied_count,
                "message": f"生成了 {applied_count} 条 Guardrails 更新建议，请人工审核后应用",
            }

        except Exception as e:
            return {"success": False, "message": f"应用 Guardrails 更新失败: {str(e)}"}

    def run_harness_update(self, review_month: str | None = None) -> dict[str, Any]:
        """
        运行 Harness 更新流程

        Args:
            review_month: 复盘月份

        Returns:
            更新结果
        """
        try:
            print("开始 Harness 层更新...")

            # 1. 分析策略表现
            print("1. 分析策略表现...")
            analysis_result = self.analyze_strategy_performance(review_month)
            if not analysis_result.get("success"):
                return analysis_result

            # 2. 生成 Guardrails 更新建议
            print("2. 生成 Guardrails 更新建议...")
            updates_result = self.generate_guardrails_update(analysis_result)
            if not updates_result.get("success"):
                return updates_result

            # 3. 应用 Guardrails 更新
            print("3. 应用 Guardrails 更新...")
            apply_result = self.apply_guardrails_updates(updates_result.get("updates", []))

            return {
                "success": True,
                "review_month": analysis_result.get("review_month"),
                "analysis": analysis_result,
                "updates": updates_result,
                "apply": apply_result,
            }

        except Exception as e:
            return {"success": False, "message": f"Harness 更新失败: {str(e)}"}


def main():
    """测试函数"""
    updater = HarnessUpdater()

    print("测试 Harness 层更新...")
    result = updater.run_harness_update()

    if result.get("success"):
        print("\n更新成功:")
        print(f"复盘月份: {result.get('review_month')}")
        print(f"更新建议数量: {result.get('updates', {}).get('total_updates', 0)}")

        # 显示更新建议
        updates = result.get("updates", {}).get("updates", [])
        if updates:
            print("\n更新建议:")
            for update in updates:
                print(f"  [{update['type'].upper()}] {update['message']}")
    else:
        print(f"更新失败: {result.get('message')}")


if __name__ == "__main__":
    main()
