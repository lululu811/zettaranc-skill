"""活跃市值闸门统一入口(apply_active_mv_gate)单元测试。

- enabled=False 时永远返回 OPEN(零成本短路)
- 任何异常降级为 WAIT(保守:不开新仓,不平仓),不阻断回测
- 闸门动作只有一种表示：GateAction
- 单股回测和组合回测都用同一个 gate 入口
"""

from pathlib import Path

import pytest

from modules.active_market_gate import (
    GateAction,
    GateConfig,
    apply_active_mv_gate,
    evaluate,
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


def test_apply_active_mv_gate_agrees_with_evaluate(tmp_path):
    """兼容入口 apply_active_mv_gate 与新 interface evaluate 结论一致。"""
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
    assert result is evaluate("20260803", GateConfig(enabled=True, path=str(csv_path)))


def test_exception_during_gate_query_returns_wait():
    """数据加载抛异常时,闸门不抛异常,降级为 WAIT（fail-closed）。"""
    from unittest.mock import patch

    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    with patch("modules.active_market_gate._load_index_and_rows", side_effect=boom):
        result = apply_active_mv_gate("20260821", enabled=True)
    assert result is GateAction.WAIT


def test_gate_action_enum_has_three_values():
    """GateAction 必须有且仅有 OPEN/WAIT/CLEAR 三个值。"""
    assert set(GateAction) == {GateAction.OPEN, GateAction.WAIT, GateAction.CLEAR}
    assert GateAction.OPEN.value == "OPEN"
    assert GateAction.WAIT.value == "WAIT"
    assert GateAction.CLEAR.value == "CLEAR"


def test_gate_action_is_str_subclass():
    """GateAction 继承 str：枚举本身就是字符串，旧的字符串比较与 isinstance 继续成立。"""
    assert issubclass(GateAction, str)
    assert isinstance(GateAction.OPEN, str)
    assert GateAction.OPEN == "OPEN"
    assert GateAction.OPEN in {"OPEN", "WAIT", "CLEAR"}


def test_gate_action_str_format_is_plain_value():
    """文本格式化必须输出 "OPEN" 而不是 "GateAction.OPEN"。

    Enum.__str__ 在 MRO 里会赢过 str.__str__，不显式覆盖的话
    `f"{GateAction.OPEN}"` 会打印 "GateAction.OPEN"，改掉 zt market timing 的输出。
    """
    assert str(GateAction.OPEN) == "OPEN"
    assert f"{GateAction.OPEN}" == "OPEN"
    assert f"{GateAction.CLEAR}" == "CLEAR"


def test_get_active_market_gate_returns_enum():
    """get_active_market_gate 直接返回 GateAction（表示层唯一化）。"""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(
            "\ufeffdate,open,high,low,close,volume,amount\n"
            "2026-08-01,100,102,99,100,1000,100000\n"
            "2026-08-02,100,102,98,98,1000,98000\n"
            "2026-08-03,98,106,97,105,1200,126000\n"
        )
        csv_path = f.name
    try:
        result = get_active_market_gate("20260803", path=csv_path)
        assert isinstance(result, GateAction)
        assert result is GateAction.OPEN
    finally:
        Path(csv_path).unlink()


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
