"""CLI ↔ Rust PyO3 桥接测试（v4.0.2）。

覆盖矩阵：
  1. Rust 可用（fake _core_compute）→ CLI 走 Rust
  2. Rust 不可用（ImportError）→ CLI 走 Python
  3. ZETTARANC_BACKTEST_IMPL=python → 强制 Python
  4. Rust 抛错 → silent fallback 到 Python（log warning）
  5. compute_func 缓存行为

不依赖真实 _core_compute（maturin build），用 fake 模块替代。
不依赖数据库：用 mock 替代 backtest_shaofu_single / get_kline_data。
"""
from __future__ import annotations

import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────
# 辅助：fake `_core_compute` 模块 + 让 _rust_compat 用它
# ─────────────────────────────────────────────────────────────────────


class _FakeComputeModule(ModuleType):
    """fake _core_compute 模块。

    暴露若干函数属性，被 _rust_compat.getattr 拉走即可。
    """


@pytest.fixture
def fake_rust_module():
    """注入一个 fake _core_compute 到 sys.modules 并清缓存。

    yield：(fake_module, rust_smoke_called_list)
    """
    fake = _FakeComputeModule("_core_compute")

    # 默认 fake 实现：返回一个"看起来对"的 dict
    def fake_run_single(config, klines):
        fake.calls.append(("run_single_strategy_backtest_py", config, klines))
        return {
            "trades": [
                {
                    "entry_date": "20240102",
                    "exit_date": "20240115",
                    "entry_price": 10.0,
                    "exit_price": 11.0,
                    "pnl": 100.0,
                    "return": 0.10,
                    "exit_reason": "signal",
                }
            ],
            "metrics": {
                "total_return": 0.15,
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.05,
                "win_rate": 1.0,
                "final_value": 115_000.0,
                "initial_cash": 100_000.0,
                "total_trades": 1,
            },
            "equity_curve": [100_000.0, 115_000.0],
            "cash_history": [50_000.0, 45_000.0],
        }

    def fake_run_grid(base_config, param_grid, splits, klines):
        fake.calls.append(("run_grid_search_py", base_config, param_grid, splits))
        return {
            "all_results": [{"params": {}, "score": 0.0}],
            "best_params": {},
            "best_score": 0.0,
            "n_results": 1,
        }

    fake.run_single_strategy_backtest_py = fake_run_single
    fake.run_portfolio_backtest_py = MagicMock(return_value={"portfolio_metrics": {}})
    fake.run_grid_search_py = fake_run_grid
    fake.compute_atr_py = MagicMock(return_value=[1.0, 2.0])
    fake.rust_smoke = MagicMock(return_value="OK: ok from fake rust")
    fake.calls = []

    sys.modules["_core_compute"] = fake

    from modules.core import _rust_compat

    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    yield fake

    sys.modules.pop("_core_compute", None)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()


@pytest.fixture
def no_rust_module(monkeypatch):
    """把 _core_compute 从 sys.modules 摘掉 + 屏蔽 ImportError 路径。"""
    monkeypatch.delitem(sys.modules, "_core_compute", raising=False)

    # 拦截 import 让 _core_compute 永远 ImportError
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "_core_compute":
            raise ImportError("simulated: _core_compute not built")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from modules.core import _rust_compat

    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    yield
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()


# ─────────────────────────────────────────────────────────────────────
# _rust_compat.compute_func 单测
# ─────────────────────────────────────────────────────────────────────


def test_compute_func_returns_rust_callable(fake_rust_module):
    from modules.core import _rust_compat

    fn = _rust_compat.compute_func("run_single_strategy_backtest_py")
    assert fn is fake_rust_module.run_single_strategy_backtest_py


def test_compute_func_returns_none_when_module_missing(no_rust_module):
    # 默认 impl=rust 时会抛 RuntimeError；用 auto 测降级
    from modules.core import _rust_compat

    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    # 在 fixture 之后模块已 _cached_resolved=False；这里换 auto
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    try:
        assert _rust_compat.compute_func("run_single_strategy_backtest_py") is None
    finally:
        monkeypatch.undo()
        importlib.reload(_rust_compat)
        _rust_compat.reset_cache()
        _rust_compat.reset_func_cache()


def test_compute_func_unknown_name_returns_none(fake_rust_module):
    from modules.core import _rust_compat

    assert _rust_compat.compute_func("not_existing_function_xyz") is None


def test_compute_func_caches_lookup(fake_rust_module):
    from modules.core import _rust_compat

    fn1 = _rust_compat.compute_func("run_single_strategy_backtest_py")
    fn2 = _rust_compat.compute_func("run_single_strategy_backtest_py")
    assert fn1 is fn2
    # 缓存被 reset 后再查：还是同一个（模块缓存复位，函数缓存保留）
    _rust_compat.reset_cache()
    fn3 = _rust_compat.compute_func("run_single_strategy_backtest_py")
    assert fn3 is fn1


def test_compute_func_respects_python_choice(monkeypatch, fake_rust_module):
    """ZETTARANC_BACKTEST_IMPL=python 即便 fake 已注入也应返回 None。"""
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "python")
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    try:
        assert _rust_compat.compute_func("run_single_strategy_backtest_py") is None
    finally:
        monkeypatch.delenv("ZETTARANC_BACKTEST_IMPL", raising=False)
        importlib.reload(_rust_compat)
        _rust_compat.reset_cache()
        _rust_compat.reset_func_cache()


# ─────────────────────────────────────────────────────────────────────
# bridge_*: Rust / Python fallback 行为
# ─────────────────────────────────────────────────────────────────────


def test_bridge_is_rust_available_true_with_fake(fake_rust_module):
    from modules.backtest._rust_bridge import is_rust_available

    assert is_rust_available() is True


def test_bridge_is_rust_available_false_when_missing(no_rust_module):
    from modules.backtest._rust_bridge import is_rust_available

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    try:
        assert is_rust_available() is False
    finally:
        monkeypatch.undo()


def test_bridge_shaofu_single_calls_rust(fake_rust_module):
    """Rust 可用：bridge_shaofu_single 应调 Rust，返回 schema 映射后的 dict。"""
    from modules.backtest._rust_bridge import bridge_shaofu_single

    # Mock Python fallback 路径，确认它没被调用
    fallback_mock = MagicMock()
    sys.modules["modules.backtest_six_step"] = SimpleNamespace(
        backtest_shaofu_single=fallback_mock,
        summary_text=lambda r: "summary",
    )

    # 用最简单的 K 线 list 让 fake 接受
    klines = [
        SimpleNamespace(
            trade_date="20240102",
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
            vol=1000.0,
        )
    ]
    result = bridge_shaofu_single("600487.SH", days=250, klines=klines)

    # Rust fake 被调用
    assert len(fake_rust_module.calls) == 1
    fn_name, cfg, kline_dicts = fake_rust_module.calls[0]
    assert fn_name == "run_single_strategy_backtest_py"
    assert isinstance(cfg, dict)
    assert isinstance(kline_dicts, list)
    assert kline_dicts[0]["close"] == 10.2

    # Python fallback 没被调用
    assert fallback_mock.call_count == 0

    # 返回 schema 正确
    assert result["ts_code"] == "600487.SH"
    assert result["total_trades"] == 1
    assert result["win_count"] == 1
    assert result["win_rate"] == 1.0
    assert result["total_return"] == 15.0  # 0.15 * 100
    assert result["max_drawdown"] == 5.0  # 0.05 * 100
    assert result["sharpe_ratio"] == 1.5
    assert len(result["trades"]) == 1
    assert result["trades"][0]["entry_price"] == 10.0


def test_bridge_shaofu_single_falls_back_to_python(no_rust_module):
    """Rust 不可用：bridge 应 silent fallback 到 Python backtest_shaofu_single。"""
    from modules.backtest._rust_bridge import bridge_shaofu_single

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    try:
        # 注入一个 fake Python backtest 返回值
        fake_python_result = SimpleNamespace(
            ts_code="600487.SH",
            total_trades=2,
            win_count=1,
            win_rate=0.5,
            total_return=0.10,
            max_drawdown=0.03,
            sharpe_ratio=1.2,
            avg_pnl=0.05,
            max_win=0.10,
            max_loss=-0.02,
            profit_factor=2.0,
            avg_holding_days=8.0,
            trades=[
                SimpleNamespace(
                    entry_date="20240102",
                    entry_price=10.0,
                    exit_date="20240115",
                    exit_price=11.0,
                    exit_reason="signal",
                    pnl_pct=0.10,
                    holding_days=13,
                )
            ],
        )
        called = {"count": 0}

        def fake_py_single(ts_code, days=250, klines=None, config=None):
            called["count"] += 1
            return fake_python_result

        from modules import backtest_six_step

        original = getattr(backtest_six_step, "backtest_shaofu_single", None)
        backtest_six_step.backtest_shaofu_single = fake_py_single
        try:
            result = bridge_shaofu_single("600487.SH", days=250)
        finally:
            if original is not None:
                backtest_six_step.backtest_shaofu_single = original
    finally:
        monkeypatch.undo()

    assert called["count"] == 1, "Python fallback should have been invoked"
    # 返回的是 Python _shaofu_result_to_dict 的 schema
    assert result["ts_code"] == "600487.SH"
    assert result["total_trades"] == 2
    assert result["win_rate"] == 0.5


def test_bridge_shaofu_single_silent_fallback_when_rust_raises(fake_rust_module, caplog):
    """Rust fake 抛错 → bridge silent fallback 到 Python。"""

    def boom(config, klines):
        raise RuntimeError("simulated Rust panic")

    fake_rust_module.run_single_strategy_backtest_py = boom
    # 清缓存让新函数被拿到
    from modules.core import _rust_compat

    _rust_compat.reset_func_cache()

    from modules.backtest._rust_bridge import bridge_shaofu_single

    fake_python_result = SimpleNamespace(
        ts_code="600487.SH",
        total_trades=1,
        win_count=1,
        win_rate=1.0,
        total_return=0.05,
        max_drawdown=0.02,
        sharpe_ratio=1.0,
        avg_pnl=0.05,
        max_win=0.05,
        max_loss=0.0,
        profit_factor=1.0,
        avg_holding_days=5.0,
        trades=[],
    )

    from modules import backtest_six_step

    original = getattr(backtest_six_step, "backtest_shaofu_single", None)
    backtest_six_step.backtest_shaofu_single = lambda *a, **kw: fake_python_result
    try:
        with caplog.at_level(logging.WARNING):
            klines = [SimpleNamespace(trade_date="20240102", open=10.0, high=10.5, low=9.5, close=10.2, vol=1000.0)]
            result = bridge_shaofu_single("600487.SH", days=250, klines=klines)
    finally:
        if original is not None:
            backtest_six_step.backtest_shaofu_single = original

    assert result["ts_code"] == "600487.SH"
    assert result["total_trades"] == 1
    # 日志应包含 warning（message 含 "falling back" 或 "fallback"）
    assert any(
        "Rust" in r.message and ("fall" in r.message)
        for r in caplog.records
    ), (
        f"expected a Rust fallback warning, got: {[r.message for r in caplog.records]}"
    )


def test_bridge_force_python_via_env(monkeypatch, fake_rust_module):
    """ZETTARANC_BACKTEST_IMPL=python → 永远走 Python，不调 Rust（即便 fake 已注入）。"""
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "python")

    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    try:
        from modules.backtest._rust_bridge import bridge_shaofu_single

        fake_python_result = SimpleNamespace(
            ts_code="600487.SH",
            total_trades=3,
            win_count=2,
            win_rate=2 / 3,
            total_return=0.20,
            max_drawdown=0.05,
            sharpe_ratio=1.8,
            avg_pnl=0.07,
            max_win=0.15,
            max_loss=-0.03,
            profit_factor=3.0,
            avg_holding_days=7.0,
            trades=[],
        )
        from modules import backtest_six_step

        original = getattr(backtest_six_step, "backtest_shaofu_single", None)
        backtest_six_step.backtest_shaofu_single = lambda *a, **kw: fake_python_result
        try:
            result = bridge_shaofu_single("600487.SH", days=250)
        finally:
            if original is not None:
                backtest_six_step.backtest_shaofu_single = original
    finally:
        monkeypatch.delenv("ZETTARANC_BACKTEST_IMPL", raising=False)
        importlib.reload(_rust_compat)
        _rust_compat.reset_cache()
        _rust_compat.reset_func_cache()

    # Rust fake 没被调
    assert len(fake_rust_module.calls) == 0, "Rust fake should not be called when impl=python"
    # 走的是 Python 结果
    assert result["total_trades"] == 3


# ─────────────────────────────────────────────────────────────────────
# CLI 集成：zt backtest shaofu 调度路径
# ─────────────────────────────────────────────────────────────────────


def test_cmd_backtest_shaofu_uses_rust_when_available(fake_rust_module, capsys):
    """zt backtest shaofu 在 Rust 可用时调 Rust 函数。"""
    from modules.cli_commands import cmd_backtest

    fake_python_result = SimpleNamespace(
        ts_code="600487.SH",
        total_trades=0,
        win_count=0,
        win_rate=0.0,
        total_return=0.0,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        avg_pnl=0.0,
        max_win=0.0,
        max_loss=0.0,
        profit_factor=0.0,
        avg_holding_days=0.0,
        trades=[],
    )
    from modules import backtest_six_step, indicators

    original_bs = getattr(backtest_six_step, "backtest_shaofu_single", None)
    original_gk = getattr(indicators, "get_kline_data", None)

    fallback_called = {"v": 0}

    def tracker(*a, **kw):
        fallback_called["v"] += 1
        return fake_python_result

    fake_klines = [
        SimpleNamespace(
            trade_date="20240102",
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
            vol=1000.0,
        )
    ]

    backtest_six_step.backtest_shaofu_single = tracker
    indicators.get_kline_data = lambda ts_code, days: fake_klines
    try:
        args = SimpleNamespace(
            backtest_sub="shaofu",
            ts_code="600487.SH",
            days=250,
            json=True,
        )
        cmd_backtest(args)
    finally:
        if original_bs is not None:
            backtest_six_step.backtest_shaofu_single = original_bs
        if original_gk is not None:
            indicators.get_kline_data = original_gk

    # Rust fake 被调
    assert len(fake_rust_module.calls) >= 1
    fn_name = fake_rust_module.calls[0][0]
    assert fn_name == "run_single_strategy_backtest_py"
    # Python fallback 没被调（因为 Rust 成功）
    assert fallback_called["v"] == 0

    # 输出包含 JSON
    captured = capsys.readouterr()
    assert "600487.SH" in captured.out
    assert "total_trades" in captured.out


def test_cmd_backtest_shaofu_falls_back_when_no_rust(no_rust_module, capsys):
    """Rust 不可用：CLI 走 Python 路径。"""
    from modules.cli_commands import cmd_backtest

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    try:
        fake_python_result = SimpleNamespace(
            ts_code="600487.SH",
            total_trades=2,
            win_count=1,
            win_rate=0.5,
            total_return=0.10,
            max_drawdown=0.03,
            sharpe_ratio=1.2,
            avg_pnl=0.05,
            max_win=0.10,
            max_loss=-0.02,
            profit_factor=2.0,
            avg_holding_days=8.0,
            trades=[
                SimpleNamespace(
                    entry_date="20240102",
                    entry_price=10.0,
                    exit_date="20240115",
                    exit_price=11.0,
                    exit_reason="signal",
                    pnl_pct=0.10,
                    holding_days=13,
                )
            ],
        )

        from modules import backtest_six_step

        original = getattr(backtest_six_step, "backtest_shaofu_single", None)
        backtest_six_step.backtest_shaofu_single = lambda *a, **kw: fake_python_result
        try:
            args = SimpleNamespace(
                backtest_sub="shaofu",
                ts_code="600487.SH",
                days=250,
                json=True,
            )
            cmd_backtest(args)
        finally:
            if original is not None:
                backtest_six_step.backtest_shaofu_single = original

        captured = capsys.readouterr()
        # Python 结果被输出
        assert "600487.SH" in captured.out
        assert "total_trades" in captured.out
    finally:
        monkeypatch.undo()


def test_cmd_backtest_shaofu_respects_python_env(fake_rust_module, capsys, monkeypatch):
    """ZETTARANC_BACKTEST_IMPL=python → 即便 fake 已注入，CLI 仍走 Python。"""
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "python")
    from modules.core import _rust_compat

    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()

    try:
        from modules.cli_commands import cmd_backtest

        fake_python_result = SimpleNamespace(
            ts_code="600487.SH",
            total_trades=1,
            win_count=1,
            win_rate=1.0,
            total_return=0.05,
            max_drawdown=0.02,
            sharpe_ratio=1.0,
            avg_pnl=0.05,
            max_win=0.05,
            max_loss=0.0,
            profit_factor=1.0,
            avg_holding_days=5.0,
            trades=[],
        )
        from modules import backtest_six_step

        original = getattr(backtest_six_step, "backtest_shaofu_single", None)
        backtest_six_step.backtest_shaofu_single = lambda *a, **kw: fake_python_result
        try:
            args = SimpleNamespace(
                backtest_sub="shaofu",
                ts_code="600487.SH",
                days=250,
                json=True,
            )
            cmd_backtest(args)
        finally:
            if original is not None:
                backtest_six_step.backtest_shaofu_single = original
    finally:
        monkeypatch.delenv("ZETTARANC_BACKTEST_IMPL", raising=False)
        importlib.reload(_rust_compat)
        _rust_compat.reset_cache()
        _rust_compat.reset_func_cache()

    # Rust fake 完全没被调
    assert len(fake_rust_module.calls) == 0
    captured = capsys.readouterr()
    assert "600487.SH" in captured.out


# ─────────────────────────────────────────────────────────────────────
# verify pipeline 集成
# ─────────────────────────────────────────────────────────────────────


def test_verify_pipeline_uses_rust_when_available(fake_rust_module):
    """verify pipeline 的 _run_single_stock_backtest 在 Rust 可用时优先调 Rust。"""
    from modules.verify import pipeline as verify_pipeline
    from modules import indicators

    fake_klines = [
        SimpleNamespace(
            trade_date="20240102",
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
            vol=1000.0,
        )
    ]
    original_gk = getattr(indicators, "get_kline_data", None)
    indicators.get_kline_data = lambda ts_code, days: fake_klines
    try:
        # 也需要 mock backtest_shaofu_single（作为 fallback 兜底）
        original_bs = verify_pipeline.backtest_shaofu_single
        verify_pipeline.backtest_shaofu_single = MagicMock()
        try:
            result = verify_pipeline._run_single_stock_backtest(
                "600487.SH", days=250, config=None
            )
        finally:
            verify_pipeline.backtest_shaofu_single = original_bs
    finally:
        if original_gk is not None:
            indicators.get_kline_data = original_gk

    assert result.skipped is False
    assert result.ts_code == "600487.SH"
    # Rust fake 被调
    assert len(fake_rust_module.calls) >= 1
    assert fake_rust_module.calls[0][0] == "run_single_strategy_backtest_py"


def test_verify_pipeline_falls_back_to_python(no_rust_module):
    """verify pipeline 在 Rust 不可用时走 Python backtest_shaofu_single。"""
    from modules.verify import pipeline as verify_pipeline

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    try:
        fake_python_result = SimpleNamespace(
            ts_code="600487.SH",
            total_trades=2,
            win_count=1,
            win_rate=0.5,
            total_return=0.10,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
            equity_curve=[100.0, 110.0],
        )
        called = {"v": 0}

        def tracker(*a, **kw):
            called["v"] += 1
            return fake_python_result

        # 注意：verify_pipeline 已 `from modules.backtest_six_step import backtest_shaofu_single`，
        # 所以必须 patch verify_pipeline 的本地绑定，而不是 backtest_six_step 模块属性。
        original = verify_pipeline.backtest_shaofu_single
        verify_pipeline.backtest_shaofu_single = tracker
        try:
            result = verify_pipeline._run_single_stock_backtest(
                "600487.SH", days=250
            )
        finally:
            verify_pipeline.backtest_shaofu_single = original

        assert called["v"] == 1, "Python backtest_shaofu_single should be called"
        assert result.ts_code == "600487.SH"
        assert result.trades == 2
        assert result.skipped is False
    finally:
        monkeypatch.undo()