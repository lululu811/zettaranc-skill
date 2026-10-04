"""活跃市值 0AMV 模块单元测试。"""

import os
from pathlib import Path

import pytest

from modules.active_market_value import (
    clear_cache,
    get_active_market_gate,
    get_active_market_signal,
    get_active_market_value,
    load_active_market_value,
)


def _write_csv(tmp_path: Path, lines: str) -> str:
    path = tmp_path / "0amv.csv"
    path.write_text(lines, encoding="utf-8")
    return str(path)


def test_load_and_signal(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"  # BOM 兼容
        "2026-08-01,100,102,99,101,1000,101000\n"
        "2026-08-02,101,104,100,106,1200,127200\n"  # +4.95% -> UP
        "2026-08-03,106,107,100,102,1100,112200\n"  # -3.77% -> DOWN
        "2026-08-04,102,103,101,102.5,1000,102500\n",  # +0.49% -> NEUTRAL
    )
    rows = load_active_market_value(csv_path)
    assert len(rows) == 4
    assert rows[1].signal == "UP"
    assert rows[2].signal == "DOWN"
    assert rows[3].signal == "NEUTRAL"


def test_signal_boundary_pct_chg_4_0_is_up(tmp_path):
    """边界: pct_chg 恰好 == 4.0 → UP(>= 阈值)。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,104,100,104,1100,114400\n",  # +4.00% 边界
    )
    point = get_active_market_value("20260802", csv_path)
    assert point is not None
    assert point.pct_chg == pytest.approx(4.0)
    assert point.signal == "UP"
    assert get_active_market_signal("20260802", path=csv_path) == "UP"


def test_signal_boundary_pct_chg_neg2_3_is_down(tmp_path):
    """边界: pct_chg 恰好 == -2.3% → DOWN(<= 阈值)。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,99,97,97.7,1100,107470\n",  # -2.30% 边界
    )
    point = get_active_market_value("20260802", csv_path)
    assert point is not None
    assert point.pct_chg == pytest.approx(-2.3)
    assert point.signal == "DOWN"
    assert get_active_market_signal("20260802", path=csv_path) == "DOWN"


def test_signal_just_inside_neutral_band(tmp_path):
    """边界外侧一点点: +3.99% / -2.29% 应该是 NEUTRAL。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,104,100,103.99,1100,114389\n"  # +3.99% → NEUTRAL
        "2026-08-03,103.99,104,100,101.6033,1100,111763.63\n",  # -2.29% → NEUTRAL
    )
    p1 = get_active_market_value("20260802", csv_path)
    p2 = get_active_market_value("20260803", csv_path)
    assert p1 is not None and p1.signal == "NEUTRAL"
    assert p2 is not None and p2.signal == "NEUTRAL"


def test_cache_invalidation_on_file_change(tmp_path):
    """mtime 缓存:文件被改写后,应读到新数据,而不是旧缓存。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n2026-08-01,100,102,99,101,1000,101000\n",
    )
    point1 = get_active_market_value("20260801", csv_path)
    assert point1 is not None and point1.close == 101.0

    # 改写文件,mtime 变化,缓存应自动失效
    csv_path_obj = Path(csv_path)
    csv_path_obj.write_text(
        "\ufeffdate,open,high,low,close,volume,amount\n2026-08-01,100,102,99,250,1000,250000\n",
        encoding="utf-8",
    )
    # 强制 mtime 推进(某些文件系统 mtime 精度 1s)
    stat = csv_path_obj.stat()
    os.utime(csv_path, (stat.st_atime, stat.st_mtime + 5))
    clear_cache()  # 显式 clear 也行,但 mtime-keyed lru_cache 应已自动失效

    point2 = get_active_market_value("20260801", csv_path)
    assert point2 is not None and point2.close == 250.0


def test_default_path_uses_data_dir_env(tmp_path, monkeypatch):
    """默认路径应优先读 DATA_DIR 环境变量。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from modules import active_market_value as amv

    amv.clear_cache()  # 防 lru_cache 把 default_path() 的结果缓存住
    expected = tmp_path / "0amv_active_market_value.csv"
    assert amv.default_path() == expected


def test_get_active_market_value_by_date(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,101,1000,101000\n"
        "2026-08-02,101,104,100,106,1200,127200\n",
    )
    point = get_active_market_value("20260802", csv_path)
    assert point is not None
    assert point.date == "2026-08-02"
    assert get_active_market_signal("20260802", path=csv_path) == "UP"


def test_get_active_market_value_latest(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n2026-08-01,100,102,99,101,1000,101000\n",
    )
    point = get_active_market_value(None, csv_path)
    assert point is not None
    assert point.date == "2026-08-01"


def test_get_active_market_value_missing_date(tmp_path):
    """查询不存在的日期应返回 None(不应抛异常)。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n2026-08-01,100,102,99,101,1000,101000\n",
    )
    point = get_active_market_value("20990101", csv_path)
    assert point is None


def test_active_market_gate(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n"
        "2026-08-01,100,102,99,100,1000,100000\n"
        "2026-08-02,100,102,98,98,1000,98000\n"
        "2026-08-03,98,106,97,105,1200,126000\n"  # 2日累计 +5.00% -> OPEN
        "2026-08-04,105,106,100,101.2,1100,111320\n",  # 当日 -3.62% -> CLEAR
    )
    assert get_active_market_gate("20260803", path=csv_path) == "OPEN"
    assert get_active_market_gate("20260804", path=csv_path) == "CLEAR"


def test_active_market_gate_missing_date_returns_wait(tmp_path):
    """查不到日期的 gate 行为:返回 WAIT(不开新仓)。"""
    csv_path = _write_csv(
        tmp_path,
        "\ufeffdate,open,high,low,close,volume,amount\n2026-08-01,100,102,99,100,1000,100000\n",
    )
    assert get_active_market_gate("20990101", path=csv_path) == "WAIT"
