"""活跃市值闸门统一入口(apply_active_mv_gate)单元测试。

- enabled=False 时永远返回 OPEN(零成本短路)
- 任何异常降级为 WAIT(保守:不开新仓,不平仓),不阻断回测
- 字符串 -> GateAction 映射(OPEN/WAIT/CLEAR)
- 单股回测和组合回测都用同一个 gate 入口
"""

from pathlib import Path

import pytest

from modules.active_market_value import (
    GateAction,
    apply_active_mv_gate,
    get_active_market_gate,
)


def test_disabled_returns_open_regardless_of_data():
    """enabled=False 时永远返回 OPEN,不查 CSV/DuckDB。"""
    # 传入不存在的路径,只要 enabled=False 就直接返回 OPEN
    result = apply_active_mv_gate(
        "20260821",
        enabled=False,
        duckdb_path="/nonexistent/path.duckdb",
        path="/nonexistent/path.csv",
    )
    assert result is GateAction.OPEN


def test_string_to_gate_action_mapping(tmp_path):
    """get_active_market_gate 返回字符串时,apply_active_mv_gate 应正确映射为枚举。"""
    # 准备一个 CSV 触发不同 gate
    csv_path = tmp_path / "0amv.csv"
    csv_path.write_text(
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,102,98,98,1000,98000\n"  # -2%
        "2026-08-03,98,106,97,105,1200,126000\n",  # +7.14%(2日累计) -> OPEN
        encoding="utf-8",
    )

    # 2026-08-03 累计涨幅 > +4% -> OPEN
    result = apply_active_mv_gate("20260803", enabled=True, path=str(csv_path))
    assert result is GateAction.OPEN, f"应为 OPEN,实际 {result}"


def test_get_active_market_gate_returns_waits_string_maps_to_wait():
    """get_active_market_gate 返回 "WAIT" 时,apply_active_mv_gate 返回 GateAction.WAIT。"""
    from unittest.mock import patch

    with patch("modules.active_market_value.get_active_market_gate", return_value="WAIT"):
        result = apply_active_mv_gate("20260821", enabled=True)
    assert result is GateAction.WAIT


def test_get_active_market_gate_returns_clear_string_maps_to_clear():
    """get_active_market_gate 返回 "CLEAR" 时,apply_active_mv_gate 返回 GateAction.CLEAR。"""
    from unittest.mock import patch

    with patch("modules.active_market_value.get_active_market_gate", return_value="CLEAR"):
        result = apply_active_mv_gate("20260821", enabled=True)
    assert result is GateAction.CLEAR


def test_unknown_gate_string_falls_back_to_wait():
    """get_active_market_gate 返回未知字符串时,apply_active_mv_gate 降级为 WAIT(保守)。"""
    from unittest.mock import patch

    with patch("modules.active_market_value.get_active_market_gate", return_value="UNKNOWN"):
        result = apply_active_mv_gate("20260821", enabled=True)
    assert result is GateAction.WAIT


def test_exception_during_gate_query_returns_wait():
    """get_active_market_gate 抛异常时,apply_active_mv_gate 不抛异常,降级为 WAIT。"""
    from unittest.mock import patch

    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    with patch("modules.active_market_value.get_active_market_gate", side_effect=boom):
        result = apply_active_mv_gate("20260821", enabled=True)
    assert result is GateAction.WAIT


def test_gate_action_enum_has_three_values():
    """GateAction 必须有且仅有 OPEN/WAIT/CLEAR 三个值。"""
    assert set(GateAction) == {GateAction.OPEN, GateAction.WAIT, GateAction.CLEAR}
    assert GateAction.OPEN.value == "OPEN"
    assert GateAction.WAIT.value == "WAIT"
    assert GateAction.CLEAR.value == "CLEAR"


def test_old_get_active_market_gate_still_returns_string_for_backward_compat():
    """get_active_market_gate 仍返回字符串(不破坏 v4.2 及以前的调用方)。"""
    # 准备数据
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(
            "\ufeffdate,open,high,low,close,volume,amount\n"
            "2026-08-01,100,102,99,100,1000,100000\n"
            "2026-08-02,100,102,98,98,1000,98000\n"
            "2026-08-03,98,106,97,105,1200,126000\n"
        )
        csv_path = f.name
    try:
        result = get_active_market_gate("20260803", path=csv_path)
        assert isinstance(result, str)
        assert result in {"OPEN", "WAIT", "CLEAR"}
    finally:
        Path(csv_path).unlink()


def test_b1b2_backtest_uses_unified_gate():
    """b1_b2_backtest 必须用 apply_active_mv_gate(不是再调 get_active_market_gate 自己拼字符串)。"""
    from modules.backtest import b1_b2_backtest as b2b
    import inspect

    src = inspect.getsource(b2b)
    # 不应再有直接的 get_active_market_gate 字符串比较("CLEAR")
    assert "get_active_market_gate(" not in src or "apply_active_mv_gate(" in src, (
        "b1_b2_backtest 必须统一走 apply_active_mv_gate"
    )


def test_portfolio_uses_unified_gate_with_gateaction_enum():
    """portfolio.py 必须用 GateAction 枚举(不是字符串 "CLEAR")。"""
    from modules.backtest import portfolio as pf
    import inspect

    src = inspect.getsource(pf)
    assert "GateAction" in src, "portfolio.py 必须 import 并使用 GateAction 枚举"
    # 不应再用字符串 "CLEAR" 直接比较
    assert '== "CLEAR"' not in src, 'portfolio.py 不应再用字符串 == "CLEAR" 直接比较'
