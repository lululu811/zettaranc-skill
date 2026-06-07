#!/usr/bin/env python3
"""
日志分析模块

分析自我改进系统的日志数据，发现优化机会
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any
from collections import defaultdict

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.improvement_logger import ImprovementLogger  # noqa: E402


class LogAnalyzer:
    """日志分析器"""

    def __init__(self, log_dir: str = None):
        """
        初始化日志分析器

        Args:
            log_dir: 日志目录（默认为 logs/）
        """
        self.logger = ImprovementLogger(log_dir)

    def analyze_signal_distribution(self, days: int = 30) -> dict[str, Any]:
        """
        分析信号分布

        Args:
            days: 分析最近 N 天的数据

        Returns:
            信号分布统计
        """
        try:
            logs = self.logger.get_recent_logs(limit=10000)

            # 过滤信号检测日志
            signal_logs = [log for log in logs if log.get("category") == "signal"]

            # 过滤最近 N 天的数据
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_signals = []
            for log in signal_logs:
                try:
                    log_date = datetime.fromisoformat(log.get("timestamp", ""))
                    if log_date >= cutoff_date:
                        recent_signals.append(log)
                except Exception:
                    continue

            # 统计信号类型分布
            signal_type_counts = defaultdict(int)
            signal_score_sum = defaultdict(float)
            signal_count_by_type = defaultdict(int)

            for log in recent_signals:
                details = log.get("details", {})
                signal_type = details.get("signal_type", "NONE")
                signal_score = details.get("signal_score", 0)

                signal_type_counts[signal_type] += 1
                signal_score_sum[signal_type] += signal_score
                signal_count_by_type[signal_type] += 1

            # 计算平均评分
            avg_scores = {}
            for signal_type, count in signal_count_by_type.items():
                if count > 0:
                    avg_scores[signal_type] = signal_score_sum[signal_type] / count

            return {
                "success": True,
                "days": days,
                "total_signals": len(recent_signals),
                "signal_type_counts": dict(signal_type_counts),
                "avg_scores": avg_scores,
            }

        except Exception as e:
            return {"success": False, "message": f"分析信号分布失败: {str(e)}"}

    def analyze_signal_accuracy(self, days: int = 30) -> dict[str, Any]:
        """
        分析信号准确率

        Args:
            days: 分析最近 N 天的数据

        Returns:
            信号准确率统计
        """
        try:
            logs = self.logger.get_recent_logs(limit=10000)

            # 过滤信号检测日志
            signal_logs = [log for log in logs if log.get("category") == "signal"]

            # 过滤最近 N 天的数据
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_signals = []
            for log in signal_logs:
                try:
                    log_date = datetime.fromisoformat(log.get("timestamp", ""))
                    if log_date >= cutoff_date:
                        recent_signals.append(log)
                except Exception:
                    continue

            # 按信号类型统计
            signal_stats = defaultdict(lambda: {"count": 0, "stocks": set()})

            for log in recent_signals:
                details = log.get("details", {})
                signal_type = details.get("signal_type", "NONE")
                ts_code = details.get("ts_code", "")

                signal_stats[signal_type]["count"] += 1
                if ts_code:
                    signal_stats[signal_type]["stocks"].add(ts_code)

            # 转换为可序列化格式
            result = {}
            for signal_type, stats in signal_stats.items():
                result[signal_type] = {"count": stats["count"], "unique_stocks": len(stats["stocks"])}

            return {"success": True, "days": days, "signal_accuracy": result}

        except Exception as e:
            return {"success": False, "message": f"分析信号准确率失败: {str(e)}"}

    def analyze_improvement_trends(self, months: int = 6) -> dict[str, Any]:
        """
        分析改进趋势

        Args:
            months: 分析最近 N 个月的数据

        Returns:
            改进趋势统计
        """
        try:
            logs = self.logger.get_recent_logs(limit=10000)

            # 按月统计
            monthly_stats = defaultdict(
                lambda: {"signal_count": 0, "review_count": 0, "harness_count": 0, "optimization_count": 0}
            )

            for log in logs:
                try:
                    log_date = datetime.fromisoformat(log.get("timestamp", ""))
                    month_key = log_date.strftime("%Y-%m")
                    category = log.get("category", "unknown")

                    if category == "signal":
                        monthly_stats[month_key]["signal_count"] += 1
                    elif category == "review":
                        monthly_stats[month_key]["review_count"] += 1
                    elif category == "harness":
                        monthly_stats[month_key]["harness_count"] += 1
                    elif category == "optimization":
                        monthly_stats[month_key]["optimization_count"] += 1
                except Exception:
                    continue

            # 转换为列表格式
            trends = []
            for month, stats in sorted(monthly_stats.items()):
                trends.append(
                    {
                        "month": month,
                        "signal_count": stats["signal_count"],
                        "review_count": stats["review_count"],
                        "harness_count": stats["harness_count"],
                        "optimization_count": stats["optimization_count"],
                    }
                )

            return {"success": True, "months": months, "trends": trends}

        except Exception as e:
            return {"success": False, "message": f"分析改进趋势失败: {str(e)}"}

    def generate_optimization_report(self) -> dict[str, Any]:
        """
        生成优化报告

        Returns:
            优化报告
        """
        try:
            # 分析信号分布
            signal_dist = self.analyze_signal_distribution(days=30)

            # 分析信号准确率
            signal_acc = self.analyze_signal_accuracy(days=30)

            # 分析改进趋势
            trends = self.analyze_improvement_trends(months=6)

            # 生成优化建议
            optimization_suggestions = []

            # 基于信号分布的建议
            if signal_dist.get("success"):
                signal_counts = signal_dist.get("signal_type_counts", {})
                total_signals = signal_dist.get("total_signals", 0)

                if total_signals > 0:
                    none_ratio = signal_counts.get("NONE", 0) / total_signals
                    if none_ratio > 0.8:
                        optimization_suggestions.append(
                            {
                                "type": "signal_detection",
                                "priority": "high",
                                "suggestion": "信号检测过于保守，80%以上的时间没有信号，建议放宽信号条件",
                            }
                        )

                    b1_ratio = signal_counts.get("B1", 0) / total_signals
                    if b1_ratio < 0.01:
                        optimization_suggestions.append(
                            {
                                "type": "signal_detection",
                                "priority": "medium",
                                "suggestion": "B1 信号出现频率过低（<1%），建议调整 J 值阈值",
                            }
                        )

            # 基于信号准确率的建议
            if signal_acc.get("success"):
                signal_accuracy = signal_acc.get("signal_accuracy", {})

                for signal_type, stats in signal_accuracy.items():
                    if signal_type != "NONE" and stats.get("count", 0) > 0:
                        # 这里可以添加准确率计算逻辑
                        # 目前只是统计信号数量
                        pass

            return {
                "success": True,
                "signal_distribution": signal_dist,
                "signal_accuracy": signal_acc,
                "improvement_trends": trends,
                "optimization_suggestions": optimization_suggestions,
            }

        except Exception as e:
            return {"success": False, "message": f"生成优化报告失败: {str(e)}"}

    def print_report(self, report: dict[str, Any]) -> None:
        """
        打印优化报告

        Args:
            report: 优化报告
        """
        if not report.get("success"):
            print(f"报告生成失败: {report.get('message')}")
            return

        print("=" * 60)
        print("自我改进系统优化报告")
        print("=" * 60)

        # 信号分布
        signal_dist = report.get("signal_distribution", {})
        if signal_dist.get("success"):
            print(f"\n信号分布（最近 {signal_dist.get('days', 30)} 天）:")
            print("-" * 40)
            print(f"总信号数: {signal_dist.get('total_signals', 0)}")

            signal_counts = signal_dist.get("signal_type_counts", {})
            for signal_type, count in sorted(signal_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {signal_type}: {count} 条")

        # 信号准确率
        signal_acc = report.get("signal_accuracy", {})
        if signal_acc.get("success"):
            print(f"\n信号准确率（最近 {signal_acc.get('days', 30)} 天）:")
            print("-" * 40)

            signal_accuracy = signal_acc.get("signal_accuracy", {})
            for signal_type, stats in sorted(signal_accuracy.items()):
                if signal_type != "NONE":
                    print(f"  {signal_type}: {stats.get('count', 0)} 条，涉及 {stats.get('unique_stocks', 0)} 只股票")

        # 改进趋势
        trends = report.get("improvement_trends", {})
        if trends.get("success"):
            print(f"\n改进趋势（最近 {trends.get('months', 6)} 个月）:")
            print("-" * 40)

            trend_data = trends.get("trends", [])
            for trend in trend_data[-6:]:  # 只显示最近 6 个月
                print(
                    f"  {trend['month']}: 信号={trend['signal_count']}, 复盘={trend['review_count']}, Harness={trend['harness_count']}"
                )

        # 优化建议
        suggestions = report.get("optimization_suggestions", [])
        if suggestions:
            print("\n优化建议:")
            print("-" * 40)
            for i, suggestion in enumerate(suggestions, 1):
                print(f"  {i}. [{suggestion['priority'].upper()}] {suggestion['suggestion']}")

        print("\n" + "=" * 60)


def main():
    """主函数"""
    analyzer = LogAnalyzer()

    print("生成优化报告...")
    report = analyzer.generate_optimization_report()

    analyzer.print_report(report)


if __name__ == "__main__":
    main()
