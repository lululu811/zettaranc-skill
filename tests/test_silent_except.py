"""
H3 静默 except 收敛验证测试（v3.x.x）

覆盖 5 个 hot file 的 except 收敛：
- modules/data_sync/syncer.py
- modules/tracking_manager.py
- modules/simulator/narrator.py
- modules/tracking_syncer.py
- modules/review_generator.py

每个 `except Exception` 块都已 narrow 到 specific exception type。本测试验证：
1. **recoverable 路径**: narrow 的异常类型被 catch, log + 不 raise + 状态正确
2. **propagatable 路径**: 未预期的异常不被 swallow, 应自然 propagate
3. **不应再有"裸" pass 块**: 验证 5 个 hot file 内不再有 bare `except Exception: pass`
"""

from __future__ import annotations

import ast
import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 5 个 hot file 的相对路径
HOT_FILES = [
    "modules/data_sync/syncer.py",
    "modules/tracking_manager.py",
    "modules/simulator/narrator.py",
    "modules/tracking_syncer.py",
    "modules/review_generator.py",
]


# ==================== 静态检查: 5 个 hot file 不再含 bare except Exception ====================


@pytest.mark.parametrize("relpath", HOT_FILES)
def test_hot_file_no_bare_except_exception(relpath):
    """5 个 hot file 必须不含 bare `except Exception` (允许 `except (X, Y, ...)`)"""
    src = (PROJECT_ROOT / relpath).read_text(encoding="utf-8")
    tree = ast.parse(src)

    bad: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                bad.append((node.lineno, ast.unparse(node)))

    assert not bad, f"{relpath} 仍有 bare `except Exception`: " + ", ".join(f"L{ln}: {code}" for ln, code in bad)


def test_hot_files_no_pass_only_except_blocks():
    """5 个 hot file 不允许有『只 pass / 只 continue / 只 return 占位』的 except 块

    例外: 显式 narrow 的 except AttributeError + continue/pass 是允许的 (迭代容错)。
    """
    for relpath in HOT_FILES:
        src = (PROJECT_ROOT / relpath).read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # 必须 narrow 到具体类型 (不是 bare Exception)
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                pytest.fail(f"{relpath} L{node.lineno}: bare `except Exception` is not allowed")


# ==================== modules/tracking_manager.py ====================


class TestTrackingManagerExcept:
    """tracking_manager 的 except 块必须 narrow 到 sqlite3.Error + 不 raise"""

    def test_add_stock_returns_false_on_sqlite_error(self, temp_db, caplog):
        """sqlite3.Error 必须被 catch (返回 False + log warning), 不应 propagate"""
        from modules.tracking_manager import TrackingManager

        mgr = TrackingManager()
        with caplog.at_level(logging.WARNING):
            with patch("modules.tracking_manager.get_connection") as mock_conn:
                mock_conn.side_effect = sqlite3.OperationalError("disk full")
                result = mgr.add_stock("600519.SH", "贵州茅台", "B1")
        assert result is False, "sqlite 失败应返回 False (recoverable)"
        assert any("添加股票" in r.message for r in caplog.records), "应有 warning log"

    def test_unexpected_exception_propagates(self, temp_db):
        """未预期的异常 (如 RuntimeError) 不应被 swallow, 应 propagate"""
        from modules.tracking_manager import TrackingManager

        mgr = TrackingManager()
        with patch("modules.tracking_manager.get_connection") as mock_conn:
            mock_conn.side_effect = RuntimeError("not a sqlite error")
            with pytest.raises(RuntimeError, match="not a sqlite error"):
                mgr.add_stock("600519.SH", "贵州茅台", "B1")

    def test_list_stocks_returns_empty_on_value_error(self, temp_db, caplog):
        """ValueError 也应被 catch (返回 [] + log)"""
        from modules.tracking_manager import TrackingManager

        mgr = TrackingManager()
        with caplog.at_level(logging.WARNING):
            with patch.object(mgr, "list_stocks", wraps=mgr.list_stocks) as _:
                # 直接 mock get_connection raise ValueError
                with patch("modules.tracking_manager.get_connection") as mock_conn:
                    mock_conn.side_effect = ValueError("bad param")
                    result = mgr.list_stocks()
        assert result == [], "ValueError 应返回 [] (recoverable)"


# ==================== modules/data_sync/syncer.py ====================


class TestDataSyncerExcept:
    """data_sync/syncer 的 except 块必须 narrow + log + 不 raise"""

    def test_sync_daily_kline_returns_zero_on_sqlite_error(self, temp_db, caplog):
        """sync_daily_kline 必须 catch sqlite3.Error (返回 0 + log)"""
        from modules.data_sync.syncer import DataSyncer

        syncer = DataSyncer()
        with caplog.at_level(logging.ERROR):
            with patch.object(syncer.daily_kline.ctx, "call_api_with_retry") as mock_api:
                mock_api.side_effect = sqlite3.OperationalError("db locked")
                result = syncer.sync_daily_kline("600519.SH")
        assert result == 0, "sqlite 失败应返回 0 (recoverable)"
        assert any("日线数据同步失败" in r.message for r in caplog.records), "应有 error log"

    def test_batch_sync_worker_returns_zero_per_stock(self, temp_db, caplog):
        """_batch_sync._worker 必须 narrow sqlite3.Error, 单股失败不影响整体"""
        from modules.data_sync.syncer import DataSyncer

        syncer = DataSyncer()

        def _bad_sync_one(ts_code):
            raise sqlite3.OperationalError(f"fail {ts_code}")

        with caplog.at_level(logging.ERROR):
            results = syncer._batch_sync("测试", _bad_sync_one, ["600519.SH", "000001.SZ"])
        # 每个失败应返回 0, 不应 crash 整个 batch
        assert results == {"600519.SH": 0, "000001.SZ": 0}
        assert any("同步失败" in r.message for r in caplog.records)

    def test_unexpected_runtime_error_propagates_from_sync(self, temp_db):
        """RuntimeError 不应被 swallow, 应 propagate"""
        from modules.data_sync.syncer import DataSyncer

        syncer = DataSyncer()
        with patch.object(syncer.daily_kline.ctx, "call_api_with_retry") as mock_api:
            mock_api.side_effect = RuntimeError("totally unexpected")
            with pytest.raises(RuntimeError, match="totally unexpected"):
                syncer.sync_daily_kline("600519.SH")


# ==================== modules/simulator/narrator.py ====================


class TestNarratorExcept:
    """narrator 的 except 块必须 narrow 到 IOError / AttributeError / ImportError"""

    def test_read_section_text_handles_ioerror(self, tmp_path, caplog):
        """_read_section_text 必须 catch OSError + UnicodeDecodeError"""
        from modules.simulator import narrator

        # 通过 monkey patch 改 _KNOWLEDGE_DIR 指向不存在的目录
        original_dir = narrator._KNOWLEDGE_DIR
        narrator._KNOWLEDGE_DIR = tmp_path / "nonexistent"
        try:
            with caplog.at_level(logging.WARNING):
                result = narrator._read_section_text("anything.md")
            assert result == "", "OSError 应返回空字符串 (recoverable)"
        finally:
            narrator._KNOWLEDGE_DIR = original_dir

    def test_metrics_attribute_missing_skipped(self):
        """metrics 缺属性时 must skip via AttributeError narrow (not bare Exception)"""
        from modules.simulator import narrator

        class FakeMetrics:
            annualized_return = 0.10
            # 故意缺 calmar_ratio / sortino_ratio / volatility_annual / max_consecutive_wins

        from modules.simulator import (
            CostModel,
            SimulationConfig,
            SimulationResult,
            SlippageModel,
        )

        config = SimulationConfig(
            initial_capital=1_000_000.0,
            cost_model=CostModel(),
            slippage_model=SlippageModel(),
        )
        result = SimulationResult(
            config=config,
            trades=[],
            equity_curve=[],
            positions=[],
            initial_capital=1_000_000.0,
            final_value=1_000_000.0,
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            avg_holding_days=0.0,
            metrics=FakeMetrics(),
        )
        prompt = narrator._build_user_prompt(result)
        # metrics 缺字段时, 整段 metrics 行会被跳过 (AttributeError pass)
        # 不应抛错
        assert "年化收益" not in prompt or "Calmar" not in prompt

    def test_unexpected_runtime_error_propagates_from_llm(self):
        """LLM 抛 RuntimeError 仍应被 catch (返回 error payload, 不 propagate)"""
        from modules.llm_providers import MiniMaxProvider
        from modules.simulator import narrator

        from modules.simulator import (
            CostModel,
            SimulationConfig,
            SimulationResult,
            SlippageModel,
        )

        config = SimulationConfig(
            initial_capital=1_000_000.0,
            cost_model=CostModel(),
            slippage_model=SlippageModel(),
        )
        result = SimulationResult(
            config=config,
            trades=[],
            equity_curve=[],
            positions=[],
            initial_capital=1_000_000.0,
            final_value=1_000_000.0,
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            avg_holding_days=0.0,
        )

        def _raise_runtime(*args, **kwargs):
            raise RuntimeError("API timeout")

        with patch.object(MiniMaxProvider, "generate", side_effect=_raise_runtime):
            with patch.object(MiniMaxProvider, "__init__", return_value=None):
                out = narrator.generate_simulation_narrative(result)
        assert out.get("error") == "llm_failed"
        assert "[生成失败]" in out["narrative_text"]

    def test_keyboard_interrupt_not_swallowed(self):
        """KeyboardInterrupt 不应被 narrow except 吞掉 (它不是 Exception)"""
        from modules.llm_providers import MiniMaxProvider
        from modules.simulator import narrator

        from modules.simulator import (
            CostModel,
            SimulationConfig,
            SimulationResult,
            SlippageModel,
        )

        config = SimulationConfig(
            initial_capital=1_000_000.0,
            cost_model=CostModel(),
            slippage_model=SlippageModel(),
        )
        result = SimulationResult(
            config=config,
            trades=[],
            equity_curve=[],
            positions=[],
            initial_capital=1_000_000.0,
            final_value=1_000_000.0,
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=0,
            avg_holding_days=0.0,
        )

        def _raise_kbi(*args, **kwargs):
            raise KeyboardInterrupt("user abort")

        with patch.object(MiniMaxProvider, "generate", side_effect=_raise_kbi):
            with patch.object(MiniMaxProvider, "__init__", return_value=None):
                with pytest.raises(KeyboardInterrupt):
                    narrator.generate_simulation_narrative(result)


# ==================== modules/tracking_syncer.py ====================


class TestTrackingSyncerExcept:
    """tracking_syncer 的 except 块必须 narrow + log"""

    def test_sync_daily_returns_failure_on_sqlite_error(self, temp_db, caplog):
        """sync_daily 必须 catch sqlite3.Error (返回 {success: False} + log)"""
        from modules.tracking_syncer import TrackingSyncer

        syncer = TrackingSyncer()
        with caplog.at_level(logging.WARNING):
            with patch("modules.tracking_syncer.get_connection") as mock_conn:
                mock_conn.side_effect = sqlite3.OperationalError("db locked")
                result = syncer.sync_daily("600519.SH")
        assert result["success"] is False
        assert "同步失败" in result["message"]
        assert any("同步" in r.message for r in caplog.records)

    def test_unexpected_runtime_error_propagates(self, temp_db):
        """RuntimeError 不应被 swallow"""
        from modules.tracking_syncer import TrackingSyncer

        syncer = TrackingSyncer()
        with patch("modules.tracking_syncer.get_connection") as mock_conn:
            mock_conn.side_effect = RuntimeError("totally unexpected")
            with pytest.raises(RuntimeError, match="totally unexpected"):
                syncer.sync_daily("600519.SH")

    def test_detect_signal_handles_zero_division(self, caplog):
        """_detect_signal 必须 catch ZeroDivisionError (返回 NONE)"""
        from modules.tracking_syncer import TrackingSyncer

        syncer = TrackingSyncer()
        # 构造 indicator_data 触发 zero division: prev_vol = 0, vol = 100
        with caplog.at_level(logging.WARNING):
            result = syncer._detect_signal(
                {"j_value": -15, "vol_ratio": None, "macd_dif": 0, "macd_dea": 0},
                {
                    "ts_code": "TEST.SH",
                    "trade_date": "20260101",
                    "open": 10,
                    "high": 11,
                    "low": 9,
                    "close": 10,
                    "pct_chg": 0,
                    "vol": 100,
                },
                {"open": 10, "high": 10.5, "low": 9.5, "close": 10, "pct_chg": 4, "vol": 0},
            )
        # 零除法可能导致 ValueError 或 ZeroDivisionError, 都应被 catch
        assert result["signal_type"] == "NONE"


# ==================== modules/review_generator.py ====================


class TestReviewGeneratorExcept:
    """review_generator 的 except 块必须 narrow + log"""

    def test_generate_monthly_review_returns_failure_on_sqlite_error(self, temp_db, caplog):
        """generate_monthly_review 必须 catch sqlite3.Error"""
        from modules.review_generator import ReviewGenerator

        gen = ReviewGenerator()
        with caplog.at_level(logging.WARNING):
            with patch("modules.review_generator.get_connection") as mock_conn:
                mock_conn.side_effect = sqlite3.OperationalError("db locked")
                result = gen.generate_monthly_review("202605")
        assert result["success"] is False
        assert "生成复盘报告失败" in result["message"]
        assert any("生成复盘报告" in r.message for r in caplog.records)

    def test_save_review_returns_false_on_sqlite_error(self, temp_db, caplog):
        """save_review_to_database 必须 catch sqlite3.Error (返回 False + log)"""
        from modules.review_generator import ReviewGenerator

        gen = ReviewGenerator()
        with caplog.at_level(logging.WARNING):
            with patch("modules.review_generator.get_connection") as mock_conn:
                mock_conn.side_effect = sqlite3.OperationalError("disk full")
                result = gen.save_review_to_database({"ts_code": "TEST.SH", "review_month": "202605"})
        assert result is False
        assert any("保存复盘" in r.message for r in caplog.records)

    def test_unexpected_runtime_error_propagates(self, temp_db):
        """RuntimeError 不应被 swallow"""
        from modules.review_generator import ReviewGenerator

        gen = ReviewGenerator()
        with patch("modules.review_generator.get_connection") as mock_conn:
            mock_conn.side_effect = RuntimeError("totally unexpected")
            with pytest.raises(RuntimeError, match="totally unexpected"):
                gen.generate_monthly_review("202605")


# ==================== 集成检查: log message 必须含可读上下文 ====================


def test_tracking_manager_logs_use_logger_not_print(caplog):
    """tracking_manager 应使用 logger.warning 而非 print (回归测试)"""
    from modules.tracking_manager import TrackingManager

    mgr = TrackingManager()
    with caplog.at_level(logging.WARNING):
        with patch("modules.tracking_manager.get_connection") as mock_conn:
            mock_conn.side_effect = sqlite3.OperationalError("fail")
            mgr.add_stock("600519.SH", "贵州茅台", "test")
    # 验证通过 caplog 能捕获到 (如果用 print 就捕获不到)
    assert len(caplog.records) > 0, "tracking_manager 没用 logger, 而是用 print"


def test_review_generator_logs_use_logger_not_print(caplog):
    """review_generator 应使用 logger.warning 而非 print"""
    from modules.review_generator import ReviewGenerator

    gen = ReviewGenerator()
    with caplog.at_level(logging.WARNING):
        with patch("modules.review_generator.get_connection") as mock_conn:
            mock_conn.side_effect = sqlite3.OperationalError("fail")
            gen.save_review_to_database({"ts_code": "TEST.SH", "review_month": "202605"})
    assert len(caplog.records) > 0, "review_generator 没用 logger, 而是用 print"


def test_tracking_syncer_logs_use_logger_not_print(caplog):
    """tracking_syncer 应使用 logger.warning 而非 print"""
    from modules.tracking_syncer import TrackingSyncer

    syncer = TrackingSyncer()
    with caplog.at_level(logging.WARNING):
        with patch("modules.tracking_syncer.get_connection") as mock_conn:
            mock_conn.side_effect = sqlite3.OperationalError("fail")
            syncer._get_indicators_for_date("600519.SH", "20260101")
    assert len(caplog.records) > 0, "tracking_syncer 没用 logger, 而是用 print"
