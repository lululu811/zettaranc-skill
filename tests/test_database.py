"""
database.py 单元测试
"""

import os
import sqlite3
import pytest
from pathlib import Path


class TestGetDbPath:
    """数据库路径解析测试"""

    def test_path_is_absolute(self, mock_env_for_tests):
        from modules.database import get_db_path
        path = get_db_path()
        assert path.is_absolute()

    def test_parent_dir_created(self, mock_env_for_tests):
        from modules.database import get_db_path
        path = get_db_path()
        assert path.parent.exists()


class TestGetConnection:
    """数据库连接测试"""

    def test_connection_returns_context(self, temp_db):
        from modules.database import get_connection
        with get_connection() as conn:
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

    def test_connection_has_row_factory(self, temp_db):
        from modules.database import get_connection
        with get_connection() as conn:
            assert conn.row_factory is not None

    def test_commit_on_success(self, temp_db):
        from modules.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT
                )
            """)
            cursor.execute("INSERT INTO test_table (id, name) VALUES (1, 'test')")
        # 退出 context 后应该已提交
        from modules.database import get_connection as gc2
        with gc2() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM test_table WHERE id = 1")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "test"

    def test_rollback_on_error(self, temp_db):
        from modules.database import get_connection
        # 先创建表
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_rollback (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
        # 插入失败应该回滚
        with pytest.raises(Exception):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO test_rollback (id, name) VALUES (1, NULL)")


class TestInitDatabase:
    """数据库初始化测试"""

    def test_creates_tables(self, temp_db):
        from modules.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = {row[0] for row in cursor.fetchall()}
            expected = {
                "daily_kline", "indicator_cache", "moneyflow",
                "financial_data", "stock_basic", "trade_signals", "sync_log"
            }
            assert expected.issubset(tables)

    def test_creates_indexes(self, temp_db):
        from modules.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='index'
            """)
            indexes = {row[0] for row in cursor.fetchall()}
            assert "idx_kline_code_date" in indexes
            assert "idx_ind_date" in indexes
            assert "idx_mf_code_date" in indexes

    def test_idempotent(self, temp_db):
        """多次调用不应报错"""
        from modules.database import init_database
        init_database()
        init_database()  # 第二次不应失败


class TestDropAllTables:
    """删除表测试"""

    def test_drops_all_tables(self, temp_db):
        from modules.database import drop_all_tables, init_database
        # 先初始化
        init_database()
        # 再删除
        drop_all_tables()
        # 验证
        from modules.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = cursor.fetchall()
            assert len(tables) == 0

    def test_reinit_after_drop(self, temp_db):
        from modules.database import drop_all_tables, init_database
        init_database()
        drop_all_tables()
        init_database()  # 删除后重新初始化应成功
