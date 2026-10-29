"""活跃市值闸门 module(``modules.active_market_gate``)的 interface 测试。

interface 是 test surface：这些测试只通过 ``evaluate(date, config)`` 与公开
API 观察行为，不断言实现细节。判定逻辑、阈值与失败降级策略都在 module
内部，调用方不需要知道。
"""

from pathlib import Path

import pytest

from modules.active_market_gate import (
    GATE_THRESHOLDS,
    GateAction,
    GateConfig,
    GateThresholds,
    apply_active_mv_gate,
    evaluate,
    get_active_market_gate,
)


def _write_csv(tmp_path: Path, rows: str) -> str:
    csv_path = tmp_path / "0amv.csv"
    csv_path.write_text(
        "\ufeffdate,open,high,low,close,volume,amount\n" + rows,
        encoding="utf-8",
    )
    return str(csv_path)


# 2026-08-02 当日 -3%（<= clear 阈值 -2.3%）→ CLEAR
# 2026-08-03 两日累计 +5%（> open 阈值 +4%）→ OPEN
_ROWS = (
    "2026-08-01,100,102,99,100,1000,100000\n2026-08-02,100,102,97,97,1000,97000\n2026-08-03,97,106,96,105,1200,126000\n"
)


def test_evaluate_disabled_returns_open_without_touching_data():
    """闸门关闭 → OPEN，且完全不查数据源。"""
    result = evaluate(
        "20260803",
        GateConfig(enabled=False, path="/nonexistent/does-not-exist.csv"),
    )
    assert result is GateAction.OPEN


def test_evaluate_no_data_is_wait_fail_closed():
    """无数据 → WAIT（fail-closed：闸门存在却读不到数据时不得放行开仓）。"""
    result = evaluate(
        "20260803",
        GateConfig(enabled=True, path="/nonexistent/does-not-exist.csv"),
    )
    assert result is GateAction.WAIT


def test_evaluate_date_not_in_index_is_wait():
    """日期不在索引里 → WAIT。"""
    csv_path = _write_csv(Path("/tmp"), _ROWS)
    try:
        result = evaluate("20260901", GateConfig(enabled=True, path=csv_path))
        assert result is GateAction.WAIT
    finally:
        Path(csv_path).unlink()


def test_evaluate_open_when_cumulative_above_threshold(tmp_path):
    """两日累计涨幅 > open 阈值 → OPEN。"""
    csv_path = _write_csv(tmp_path, _ROWS)
    result = evaluate("20260803", GateConfig(enabled=True, path=csv_path))
    assert result is GateAction.OPEN


def test_evaluate_clear_when_daily_drop_below_threshold(tmp_path):
    """当日跌幅 <= clear 阈值 → CLEAR。"""
    csv_path = _write_csv(tmp_path, _ROWS)
    result = evaluate("20260802", GateConfig(enabled=True, path=csv_path))
    assert result is GateAction.CLEAR


def test_evaluate_swallows_loader_exception_to_wait(monkeypatch):
    """加载异常 → WAIT，不抛异常阻断回测。"""
    from modules import active_market_gate

    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(active_market_gate, "_load_index_and_rows", boom)
    result = evaluate("20260821", GateConfig(enabled=True))
    assert result is GateAction.WAIT


def test_evaluate_and_legacy_api_agree(tmp_path):
    """新 interface 与旧公开 API 对同一份数据给出一致结论。"""
    csv_path = _write_csv(tmp_path, _ROWS)
    for date in ("20260802", "20260803"):
        assert evaluate(date, GateConfig(enabled=True, path=csv_path)) is get_active_market_gate(date, path=csv_path)


def test_legacy_path_still_resolves_to_same_objects():
    """旧导入路径（已发布到 PyPI）指向同一批对象。"""
    from modules import active_market_value

    assert active_market_value.get_active_market_gate is get_active_market_gate
    assert active_market_value.apply_active_mv_gate is apply_active_mv_gate
    assert active_market_value.GateAction is GateAction
    assert active_market_value.GateConfig is GateConfig
    assert active_market_value.evaluate is evaluate


def test_gate_thresholds_defaults():
    """闸门阈值：两日累计口径，open +4% / clear -2.3% / lookback 2。"""
    assert GATE_THRESHOLDS.open == 4.0
    assert GATE_THRESHOLDS.clear == -2.3
    assert GATE_THRESHOLDS.open_lookback == 2
    assert GateThresholds() == GATE_THRESHOLDS


def test_gate_config_defaults_to_enabled_without_paths():
    cfg = GateConfig()
    assert cfg.enabled is True
    assert cfg.duckdb_path is None
    assert cfg.path is None
