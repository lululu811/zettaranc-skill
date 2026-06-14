#!/usr/bin/env python3
"""
自我改进系统 - 跟踪池管理模块

管理跟踪股票的添加、移除、查询、状态更新
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.database import get_connection  # noqa: E402


class TrackingManager:
    """跟踪池管理器"""

    def __init__(self):
        """初始化跟踪池管理器"""
        pass

    def add_stock(
        self,
        ts_code: str,
        name: str | None = None,
        reason: str | None = None,
        strategy_tags: list[str] | None = None,
        notes: str | None = None,
    ) -> bool:
        """
        添加股票到跟踪池

        Args:
            ts_code: 股票代码（如 600519.SH）
            name: 股票名称
            reason: 跟踪原因
            strategy_tags: 策略标签列表（如 ['B1', '长安战法']）
            notes: 备注

        Returns:
            是否添加成功
        """
        try:
            add_date = datetime.now().strftime("%Y-%m-%d")
            strategy_tags_str = ",".join(strategy_tags) if strategy_tags else None

            with get_connection() as conn:
                cursor = conn.cursor()

                # 检查是否已存在
                cursor.execute(
                    """
                    SELECT id FROM tracking_pool_self
                    WHERE ts_code = ? AND status = 'active'
                """,
                    (ts_code,),
                )

                if cursor.fetchone():
                    print(f"股票 {ts_code} 已在跟踪池中")
                    return False

                # 插入新记录
                cursor.execute(
                    """
                    INSERT INTO tracking_pool_self (
                        ts_code, name, add_date, status, track_reason, strategy_tags, notes
                    ) VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                    (ts_code, name, add_date, reason, strategy_tags_str, notes),
                )

                conn.commit()
                print(f"已添加 {ts_code} 到跟踪池")
                return True

        except Exception as e:
            print(f"添加股票失败: {e}")
            return False

    def remove_stock(self, ts_code: str, reason: str | None = None) -> bool:
        """
        从跟踪池移除股票

        Args:
            ts_code: 股票代码
            reason: 移除原因

        Returns:
            是否移除成功
        """
        try:
            remove_date = datetime.now().strftime("%Y-%m-%d")

            with get_connection() as conn:
                cursor = conn.cursor()

                # 更新状态为 removed
                cursor.execute(
                    """
                    UPDATE tracking_pool_self
                    SET status = 'removed',
                        remove_date = ?,
                        updated_at = datetime('now')
                    WHERE ts_code = ? AND status = 'active'
                """,
                    (remove_date, ts_code),
                )

                if cursor.rowcount == 0:
                    print(f"股票 {ts_code} 不在跟踪池中")
                    return False

                conn.commit()
                print(f"已从跟踪池移除 {ts_code}")
                return True

        except Exception as e:
            print(f"移除股票失败: {e}")
            return False

    def list_stocks(self, status: str = "active", strategy_tag: str | None = None) -> list[dict[str, Any]]:
        """
        列出跟踪池中的股票

        Args:
            status: 状态筛选（active/paused/removed）
            strategy_tag: 策略标签筛选

        Returns:
            股票列表
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                sql = "SELECT * FROM tracking_pool_self WHERE 1=1"
                params = []

                if status:
                    sql += " AND status = ?"
                    params.append(status)

                if strategy_tag:
                    sql += " AND strategy_tags LIKE ?"
                    params.append(f"%{strategy_tag}%")

                sql += " ORDER BY add_date DESC"

                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            print(f"查询跟踪池失败: {e}")
            return []

    def get_stock_info(self, ts_code: str) -> dict[str, Any] | None:
        """
        获取股票的跟踪信息

        Args:
            ts_code: 股票代码

        Returns:
            股票信息字典
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM tracking_pool_self
                    WHERE ts_code = ?
                    ORDER BY add_date DESC
                    LIMIT 1
                """,
                    (ts_code,),
                )

                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            print(f"查询股票信息失败: {e}")
            return None

    def update_stock_status(self, ts_code: str, status: str, notes: str | None = None) -> bool:
        """
        更新股票状态

        Args:
            ts_code: 股票代码
            status: 新状态（active/paused/removed）
            notes: 备注

        Returns:
            是否更新成功
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                update_sql = """
                    UPDATE tracking_pool_self
                    SET status = ?, updated_at = datetime('now')
                """
                params = [status]

                if notes:
                    update_sql += ", notes = ?"
                    params.append(notes)

                update_sql += " WHERE ts_code = ? AND status != 'removed'"
                params.append(ts_code)

                cursor.execute(update_sql, params)

                if cursor.rowcount == 0:
                    print(f"股票 {ts_code} 不存在或已移除")
                    return False

                conn.commit()
                print(f"已更新 {ts_code} 状态为 {status}")
                return True

        except Exception as e:
            print(f"更新股票状态失败: {e}")
            return False

    def get_tracking_stats(self) -> dict[str, Any]:
        """
        获取跟踪池统计信息

        Returns:
            统计信息字典
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # 统计各状态数量
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM tracking_pool_self
                    GROUP BY status
                """)

                stats = {row["status"]: row["count"] for row in cursor.fetchall()}

                # 统计总数量
                cursor.execute("SELECT COUNT(*) as total FROM tracking_pool_self")
                stats["total"] = cursor.fetchone()["total"]

                # 统计今日新增
                today = datetime.now().strftime("%Y-%m-%d")
                cursor.execute(
                    """
                    SELECT COUNT(*) as today_added
                    FROM tracking_pool_self
                    WHERE add_date = ?
                """,
                    (today,),
                )
                stats["today_added"] = cursor.fetchone()["today_added"]

                return stats

        except Exception as e:
            print(f"获取统计信息失败: {e}")
            return {}

    def get_strategy_distribution(self) -> dict[str, int]:
        """
        获取策略分布统计

        Returns:
            策略分布字典
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT strategy_tags
                    FROM tracking_pool_self
                    WHERE status = 'active' AND strategy_tags IS NOT NULL
                """)

                distribution: dict[str, int] = {}
                for row in cursor.fetchall():
                    tags = row["strategy_tags"].split(",")
                    for tag in tags:
                        tag = tag.strip()
                        if tag:
                            distribution[tag] = distribution.get(tag, 0) + 1

                return distribution

        except Exception as e:
            print(f"获取策略分布失败: {e}")
            return {}


def main():
    """测试函数"""
    manager = TrackingManager()

    # 测试添加股票
    print("\n=== 测试添加股票 ===")
    manager.add_stock("600519.SH", "贵州茅台", "B1买点出现", ["B1"], "测试股票")
    manager.add_stock("000858.SZ", "五粮液", "观察池", ["B2", "长安战法"], "测试股票2")

    # 测试列出股票
    print("\n=== 测试列出股票 ===")
    stocks = manager.list_stocks()
    for stock in stocks:
        print(f"{stock['ts_code']} - {stock['name']} - {stock['status']}")

    # 测试获取统计信息
    print("\n=== 测试获取统计信息 ===")
    stats = manager.get_tracking_stats()
    print(f"总数量: {stats.get('total', 0)}")
    print(f"活跃数量: {stats.get('active', 0)}")

    # 测试获取策略分布
    print("\n=== 测试获取策略分布 ===")
    distribution = manager.get_strategy_distribution()
    for strategy, count in distribution.items():
        print(f"{strategy}: {count}只")


if __name__ == "__main__":
    main()
