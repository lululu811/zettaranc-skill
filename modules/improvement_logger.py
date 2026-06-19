#!/usr/bin/env python3
"""
自我改进系统 - 日志记录模块

记录所有自我改进的操作和结果
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

# 项目根目录（用于解析默认 logs/ 路径）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ImprovementLogger:
    """自我改进日志记录器"""

    def __init__(self, log_dir: str | None = None):
        """
        初始化日志记录器

        Args:
            log_dir: 日志目录（默认为 logs/）
        """
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = PROJECT_ROOT / "logs"

        # 创建日志目录
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 日志文件路径
        self.log_file = self.log_dir / "improvement_log.jsonl"

    def log(
        self, action: str, category: str, details: dict[str, Any], status: str = "success", message: str = ""
    ) -> bool:
        """
        记录日志

        Args:
            action: 操作名称
            category: 分类（signal/review/harness/optimization）
            details: 详细信息
            status: 状态（success/failure/warning）
            message: 附加消息

        Returns:
            是否记录成功
        """
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "category": category,
                "status": status,
                "message": message,
                "details": details,
            }

            # 追加到日志文件
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            return True

        except Exception as e:
            print(f"记录日志失败: {e}")
            return False

    def log_signal_detection(
        self,
        ts_code: str,
        trade_date: str,
        signal_type: str,
        signal_score: float,
        signal_reason: str,
        indicator_data: dict[str, Any],
    ) -> bool:
        """
        记录信号检测日志

        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            signal_type: 信号类型
            signal_score: 信号评分
            signal_reason: 信号原因
            indicator_data: 指标数据

        Returns:
            是否记录成功
        """
        details = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "signal_type": signal_type,
            "signal_score": signal_score,
            "signal_reason": signal_reason,
            "indicator_data": indicator_data,
        }

        return self.log(
            action="signal_detection",
            category="signal",
            details=details,
            status="success",
            message=f"{ts_code} 检测到 {signal_type} 信号",
        )

    def log_review_generation(
        self,
        review_month: str,
        total_stocks: int,
        avg_return: float,
        max_drawdown: float,
        buy_signals: int,
        correct_buy_signals: int,
    ) -> bool:
        """
        记录复盘报告生成日志

        Args:
            review_month: 复盘月份
            total_stocks: 股票数量
            avg_return: 平均收益
            max_drawdown: 最大回撤
            buy_signals: 买入信号数
            correct_buy_signals: 正确买入信号数

        Returns:
            是否记录成功
        """
        accuracy_rate = 0.0
        if buy_signals > 0:
            accuracy_rate = correct_buy_signals / buy_signals * 100

        details = {
            "review_month": review_month,
            "total_stocks": total_stocks,
            "avg_return": avg_return,
            "max_drawdown": max_drawdown,
            "buy_signals": buy_signals,
            "correct_buy_signals": correct_buy_signals,
            "accuracy_rate": accuracy_rate,
        }

        return self.log(
            action="review_generation",
            category="review",
            details=details,
            status="success",
            message=f"生成 {review_month} 复盘报告，共 {total_stocks} 只股票",
        )

    def log_harness_update(self, review_month: str, updates_count: int, warnings: list) -> bool:
        """
        记录 Harness 层更新日志

        Args:
            review_month: 复盘月份
            updates_count: 更新数量
            warnings: 警告列表

        Returns:
            是否记录成功
        """
        details = {"review_month": review_month, "updates_count": updates_count, "warnings": warnings}

        return self.log(
            action="harness_update",
            category="harness",
            details=details,
            status="success",
            message=f"Harness 层更新，生成 {updates_count} 条建议",
        )

    def log_optimization(
        self,
        optimization_type: str,
        before_value: float,
        after_value: float,
        improvement: float,
        details: dict[str, Any],
    ) -> bool:
        """
        记录优化日志

        Args:
            optimization_type: 优化类型
            before_value: 优化前值
            after_value: 优化后值
            improvement: 改进幅度
            details: 详细信息

        Returns:
            是否记录成功
        """
        log_details = {
            "optimization_type": optimization_type,
            "before_value": before_value,
            "after_value": after_value,
            "improvement": improvement,
            **details,
        }

        return self.log(
            action="optimization",
            category="optimization",
            details=log_details,
            status="success",
            message=f"{optimization_type} 优化：{before_value:.2f} → {after_value:.2f}（+{improvement:.2f}%）",
        )

    def get_recent_logs(self, limit: int = 100) -> list:
        """
        获取最近的日志

        Args:
            limit: 返回数量

        Returns:
            日志列表
        """
        try:
            if not self.log_file.exists():
                return []

            logs = []
            with open(self.log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            log_entry = json.loads(line)
                            logs.append(log_entry)
                        except json.JSONDecodeError:
                            continue

            # 返回最新的日志
            return logs[-limit:]

        except Exception as e:
            print(f"获取日志失败: {e}")
            return []

    def get_logs_by_category(self, category: str, limit: int = 100) -> list:
        """
        按分类获取日志

        Args:
            category: 分类
            limit: 返回数量

        Returns:
            日志列表
        """
        logs = self.get_recent_logs(limit=1000)
        filtered_logs = [log for log in logs if log.get("category") == category]
        return filtered_logs[-limit:]

    def get_improvement_summary(self) -> dict[str, Any]:
        """
        获取改进摘要

        Returns:
            改进摘要
        """
        try:
            logs = self.get_recent_logs(limit=1000)

            # 统计各分类数量
            category_counts: dict[str, int] = {}
            for log in logs:
                category = log.get("category", "unknown")
                category_counts[category] = category_counts.get(category, 0) + 1

            # 统计各状态数量
            status_counts: dict[str, int] = {}
            for log in logs:
                status = log.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            # 获取最新的优化记录
            optimization_logs = [log for log in logs if log.get("category") == "optimization"]
            latest_optimization = optimization_logs[-1] if optimization_logs else None

            return {
                "total_logs": len(logs),
                "category_counts": category_counts,
                "status_counts": status_counts,
                "latest_optimization": latest_optimization,
            }

        except Exception as e:
            print(f"获取改进摘要失败: {e}")
            return {}


def main():
    """测试函数"""
    logger = ImprovementLogger()

    # 测试记录信号检测
    logger.log_signal_detection(
        ts_code="600519.SH",
        trade_date="20260529",
        signal_type="B1",
        signal_score=80,
        signal_reason="B1买点：J值=-10.3<=-10",
        indicator_data={"j_value": -10.3, "bbi": 1312.68},
    )

    # 测试记录复盘报告生成
    logger.log_review_generation(
        review_month="202605",
        total_stocks=194,
        avg_return=-5.38,
        max_drawdown=45.17,
        buy_signals=7,
        correct_buy_signals=2,
    )

    # 测试记录 Harness 层更新
    logger.log_harness_update(
        review_month="202605",
        updates_count=7,
        warnings=[
            "策略 持仓,能源,新能源 近期表现不佳（平均收益 -30.4%），谨慎使用",
            "策略 自选,军工 近期表现不佳（平均收益 -27.8%），谨慎使用",
        ],
    )

    # 获取改进摘要
    summary = logger.get_improvement_summary()
    print("改进摘要:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 获取最近的日志
    recent_logs = logger.get_recent_logs(limit=5)
    print("\n最近的日志:")
    for log in recent_logs:
        print(f"[{log['timestamp']}] {log['action']}: {log['message']}")


if __name__ == "__main__":
    main()
