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


# 关注 sys.modules 中这些"会被测试替换成 stub/mock"的 key。
# 跨测试隔离时需要快照 + 还原（特别是 modules.backtest.shaofu：
# 一旦被替换为 SimpleNamespace，如果包属性里已有原始模块，
# `from modules.backtest import shaofu` 与 `from modules.backtest.shaofu import X`
# 会指向不同对象 → 测试间污染）。
_TRACKED_MODULES: tuple[str, ...] = (
    "_core_compute",
    "modules.backtest_six_step",
    # v4.8.0 起 shaofu 实现迁到 modules.backtest.shaofu，Rust 桥的 Python
    # 兜底也从这里导入——mock 目标随之改变
    "modules.backtest.shaofu",
)

# 用于在快照中区分"键不存在"和"键存在但值为 None"的哨兵。
_SENTINEL: object = object()


@pytest.fixture(autouse=True)
def _isolate_rust_test_state():
    """每个测试前后保存/还原 sys.modules 的关键 key + 清空 _rust_compat 缓存。

    为什么需要（v4.0.2 fixture 隔离教训）：
    - `fake_rust_module` 会把 `_core_compute` 塞进 sys.modules；
      即使单个 fixture 清理了，跨文件测试顺序加载顺序也可能在 _rust_compat 缓存里残留。
    - `test_bridge_shaofu_single_calls_rust` 直接
      `sys.modules["modules.backtest.shaofu"] = SimpleNamespace(...)` 来 mock Python
      兜底路径；这会污染所有后续测试对该模块的 import 结果（特别是当
      包属性里已有真实模块绑定时，`from modules.backtest import shaofu` 与
      `from modules.backtest.shaofu import X` 会指向不同对象）。autouse 还原机制
      让"污染被限制在产生它的那个测试内"。

    只管 sys.modules 和 _rust_compat 缓存；ZETTARANC_BACKTEST_IMPL 由每个测试
    自己的 monkeypatch 负责（pytest 的 monkeypatch teardown 在 fixture teardown
    之后执行，避免与 autouse 直接改 os.environ 冲突）。

    注意：这是 test_cli_uses_rust.py 内的本地 fixture，不影响 conftest.py。
    """
    # ── before：快照 + 清缓存 ──
    # 先把被跟踪的 module 真正 import 进来：否则它们可能在快照之后才进入
    # sys.modules（测试体内的首次 import），teardown 时的 pop 会把它们删掉，
    # 于是 sys.modules 与包属性指向不同对象——后续测试从包属性拿到真模块，
    # 而 `from modules.backtest.shaofu import ...` 重新 import 出一个未被
    # patch 的新模块，mock 全部失效。
    import modules.backtest.shaofu  # noqa: F401
    import modules.backtest_six_step  # noqa: F401

    saved_modules = {key: sys.modules.get(key, _SENTINEL) for key in _TRACKED_MODULES}
    # 同时保存 modules.__dict__['backtest_six_step']（防止 SimpleNamespace 绑定污染
    # `from modules import backtest_six_step` 在后续测试中的解析）
    saved_pkg_attr = _SENTINEL
    # v4.8.0 起 shaofu 实现迁至 modules.backtest.shaofu，Rust 桥的 Python 兜底
    # 从那里导入——包属性 modules.backtest.shaofu 同样要快照还原
    saved_shaofu_attr = _SENTINEL
    try:
        import modules as _pkg

        if "backtest_six_step" in _pkg.__dict__:
            saved_pkg_attr = _pkg.__dict__["backtest_six_step"]
        import modules.backtest as _bt_pkg

        if "shaofu" in _bt_pkg.__dict__:
            saved_shaofu_attr = _bt_pkg.__dict__["shaofu"]
    except Exception:
        pass

    from modules.core import _rust_compat

    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    try:
        yield
    finally:
        # ── after：还原 sys.modules + 还原包属性绑定 + 清缓存 ──
        for key, value in saved_modules.items():
            if value is _SENTINEL:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
        if saved_pkg_attr is not _SENTINEL:
            try:
                import modules as _pkg

                _pkg.backtest_six_step = saved_pkg_attr
            except Exception:
                pass
        else:
            try:
                import modules as _pkg

                _pkg.__dict__.pop("backtest_six_step", None)
            except Exception:
                pass
        if saved_shaofu_attr is not _SENTINEL:
            try:
                import modules.backtest as _bt_pkg

                _bt_pkg.shaofu = saved_shaofu_attr
            except Exception:
                pass
        else:
            try:
                import modules.backtest as _bt_pkg

                _bt_pkg.__dict__.pop("shaofu", None)
            except Exception:
                pass
        _rust_compat.reset_cache()
        _rust_compat.reset_func_cache()


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

    # 不在这里手动 pop：_isolate_rust_test_state 会基于 setup 前的快照还原。
    # 但 _rust_compat 缓存手动再清一次防止 yield 中途被某些 reload 干扰。
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()


@pytest.fixture
def no_rust_module(monkeypatch):
    """把 _core_compute 从 sys.modules 摘掉 + 屏蔽 ImportError 路径。

    v4.0.2 改动（fixture 隔离）：
    1. 显式设置 sys.modules['_core_compute'] = None（让 `import _core_compute`
       拿到 None；getattr(None, ...) 触发 AttributeError，触发 import system 重试，
       最终走 fake_import 抛 ImportError）。
    2. monkeypatch builtins.__import__ 拦截 _core_compute。
    3. 重置 _rust_compat 缓存。
    4. 不修改 ZETTARANC_BACKTEST_IMPL —— 各测试自己用 monkeypatch.setenv 处理
       auto/python 模式（避免 autouse fixture 与 monkeypatch teardown 顺序冲突）。

    注：跨测试 sys.modules 还原由 _isolate_rust_test_state autouse fixture 兜底，
    这里不再单独 pop。
    """
    # 1. 标记 _core_compute 为"不可用"（设为 None：import 系统会跳过缓存、走到 fake_import）
    sys.modules["_core_compute"] = None

    # 2. 拦截 import：让 _core_compute 永远 ImportError
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


def test_bridge_shaofu_single_calls_rust(fake_rust_module, monkeypatch):
    """Rust 可用：bridge_shaofu_single 应调 Rust，返回 schema 映射后的 dict。"""
    from modules.backtest._rust_bridge import bridge_shaofu_single

    # Mock Python fallback 路径，确认它没被调用。
    # 用 monkeypatch 同时打 sys.modules 和 modules.__dict__，让 pytest 在
    # teardown 时自动还原两者（避免 SimpleNamespace 绑定污染 from modules import）。
    import modules.backtest as _backtest_pkg

    fallback_mock = MagicMock()
    _ns = SimpleNamespace(
        backtest_shaofu_single=fallback_mock,
        summary_text=lambda r: "summary",
    )
    monkeypatch.setitem(sys.modules, "modules.backtest.shaofu", _ns)
    # 包属性也要一起替换，否则 `from modules.backtest import shaofu` 拿到的
    # 仍是真模块，与 sys.modules 里的替身不是同一个对象。
    # 用 monkeypatch.setattr 让它自动回滚。
    monkeypatch.setattr(_backtest_pkg, "shaofu", _ns, raising=False)

    try:
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
    finally:
        # sys.modules 与包属性都由 monkeypatch 自动回滚
        pass


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
            avg_win=0.10,
            loss_count=1,
            avg_loss=-0.02,
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

        from modules.backtest import shaofu

        original = getattr(shaofu, "backtest_shaofu_single", None)
        shaofu.backtest_shaofu_single = fake_py_single
        try:
            result = bridge_shaofu_single("600487.SH", days=250)
        finally:
            if original is not None:
                shaofu.backtest_shaofu_single = original
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
        avg_win=0.10,
        loss_count=1,
        avg_loss=-0.02,
        max_win=0.05,
        max_loss=0.0,
        profit_factor=1.0,
        avg_holding_days=5.0,
        trades=[],
    )

    from modules.backtest import shaofu

    original = getattr(shaofu, "backtest_shaofu_single", None)
    shaofu.backtest_shaofu_single = lambda *a, **kw: fake_python_result
    try:
        with caplog.at_level(logging.WARNING):
            klines = [SimpleNamespace(trade_date="20240102", open=10.0, high=10.5, low=9.5, close=10.2, vol=1000.0)]
            result = bridge_shaofu_single("600487.SH", days=250, klines=klines)
    finally:
        if original is not None:
            shaofu.backtest_shaofu_single = original

    assert result["ts_code"] == "600487.SH"
    assert result["total_trades"] == 1
    # 日志应包含 warning（message 含 "falling back" 或 "fallback"）
    assert any("Rust" in r.message and ("fall" in r.message) for r in caplog.records), (
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
            avg_win=0.10,
            loss_count=1,
            avg_loss=-0.02,
            max_win=0.15,
            max_loss=-0.03,
            profit_factor=3.0,
            avg_holding_days=7.0,
            trades=[],
        )
        from modules.backtest import shaofu

        original = getattr(shaofu, "backtest_shaofu_single", None)
        shaofu.backtest_shaofu_single = lambda *a, **kw: fake_python_result
        try:
            result = bridge_shaofu_single("600487.SH", days=250)
        finally:
            if original is not None:
                shaofu.backtest_shaofu_single = original
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
        avg_win=0.10,
        loss_count=1,
        avg_loss=-0.02,
        max_win=0.0,
        max_loss=0.0,
        profit_factor=0.0,
        avg_holding_days=0.0,
        trades=[],
    )
    from modules.backtest import shaofu
    from modules import indicators

    original_bs = getattr(shaofu, "backtest_shaofu_single", None)
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

    shaofu.backtest_shaofu_single = tracker
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
            shaofu.backtest_shaofu_single = original_bs
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
            avg_win=0.10,
            loss_count=1,
            avg_loss=-0.02,
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

        from modules.backtest import shaofu

        original = getattr(shaofu, "backtest_shaofu_single", None)
        shaofu.backtest_shaofu_single = lambda *a, **kw: fake_python_result
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
                shaofu.backtest_shaofu_single = original

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
            avg_win=0.10,
            loss_count=1,
            avg_loss=-0.02,
            max_win=0.05,
            max_loss=0.0,
            profit_factor=1.0,
            avg_holding_days=5.0,
            trades=[],
        )
        from modules.backtest import shaofu

        original = getattr(shaofu, "backtest_shaofu_single", None)
        shaofu.backtest_shaofu_single = lambda *a, **kw: fake_python_result
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
                shaofu.backtest_shaofu_single = original
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
            result = verify_pipeline._run_single_stock_backtest("600487.SH", days=250, config=None)
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

        # 注意：verify_pipeline 已 `from modules.backtest import backtest_shaofu_single`，
        # 所以必须 patch verify_pipeline 的本地绑定，而不是 backtest.shaofu 模块属性。
        original = verify_pipeline.backtest_shaofu_single
        verify_pipeline.backtest_shaofu_single = tracker
        try:
            result = verify_pipeline._run_single_stock_backtest("600487.SH", days=250)
        finally:
            verify_pipeline.backtest_shaofu_single = original

        assert called["v"] == 1, "Python backtest_shaofu_single should be called"
        assert result.ts_code == "600487.SH"
        assert result.trades == 2
        assert result.skipped is False
    finally:
        monkeypatch.undo()


# ─────────────────────────────────────────────────────────────────────
# Fixture 隔离回归测试（v4.0.2）
# 目的：保证 no_rust_module + fake_rust_module 在测试间不留残留，
# 特别是 sys.modules["_core_compute"] 与 sys.modules["modules.backtest.shaofu"]
# 不污染下一个测试。
# ─────────────────────────────────────────────────────────────────────


def test_no_rust_module_leaves_no_residue_in_sys_modules(no_rust_module, monkeypatch):
    """no_rust_module 之后：_core_compute 不可 import，且 sys.modules 状态干净。

    验证 autouse fixture 把 _core_compute 的 sys.modules 还原了。
    """
    # 1. import _core_compute 必须失败（被 fake_import 拦截）
    with pytest.raises(ImportError):
        import _core_compute  # noqa: F401

    # 2. 在 auto 模式下，get_compute_module 返回 None 而不是抛 RuntimeError
    from modules.core import _rust_compat

    monkeypatch.setenv("ZETTARANC_BACKTEST_IMPL", "auto")
    importlib.reload(_rust_compat)
    _rust_compat.reset_cache()
    _rust_compat.reset_func_cache()
    assert _rust_compat.get_compute_module() is None


def test_isolation_no_rust_then_real_import_via_fake(no_rust_module):
    """场景：先用 no_rust_module 屏蔽 _core_compute。

    验证 autouse fixture 在测试间还原 sys.modules['_core_compute']：
    测试结束时 _core_compute 应已被清掉（None 被 pop 掉），
    这样下一个测试能正常 import。
    """
    # no_rust_module 期间 _core_compute 一定是 None（被 fake_import 拦截）
    assert sys.modules.get("_core_compute") is None
    # 测试结束后 autouse 会把它清掉，下一个测试拿到的是正常 Python 行为
    # （我们在这里只断言当前状态；下个测试能用 fake_rust_module 验证）


def test_isolation_modules_backtest_shaofu_leak_prevention(fake_rust_module):
    """场景：fake_rust_module 注入 _core_compute 后，bridge_shaofu_single_calls_rust
    把 sys.modules['modules.backtest.shaofu'] 替换成 SimpleNamespace。

    autouse fixture 在测试结束时应还原 modules.backtest.shaofu，
    下一个测试应能拿到原始模块（带完整属性、__file__）。
    """
    from modules.backtest import shaofu as shaofu_module  # noqa: F401 触发 import

    # 真模块必须有 __file__；SimpleNamespace 没有
    assert hasattr(shaofu_module, "__file__")
    assert hasattr(shaofu_module, "backtest_shaofu_single")
