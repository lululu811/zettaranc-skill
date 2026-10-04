"""B1观察+B2确认策略的单元测试。"""

from unittest.mock import patch

import pytest

from modules.indicators import DailyData
from modules.strategies.b1_b2 import B1B2Config, has_b1_in_window, is_b2_signal, is_high_open_skip
from modules.backtest.b1_b2_backtest import _run_stock_klines, _default_loop_config
from modules.active_market_value import GateAction


def _make_klines(n=40, start="20260101"):
    """构造简单的 DailyData 序列，允许手工设置 KDJ 属性以绕过价格计算。"""
    out = []
    base = 10.0
    for i in range(n):
        date = f"{int(start) + i:08d}"
        out.append(
            DailyData(
                ts_code="TEST.SZ",
                trade_date=date,
                open=base * 0.99,
                high=base * 1.01,
                low=base * 0.98,
                close=base,
                vol=10000.0,
                amount=base * 10000.0,
                pct_chg=0.0,
                prev_close=base,
            )
        )
    return out


def _make_b2_klines():
    klines = _make_klines(40)
    # B1 出现在 index=26（B2 前 4 个交易日）
    klines[26].kdj_j = -15.0
    # B2 当天：涨幅 +5%，量是前日 3 倍，J=40
    klines[30].pct_chg = 5.0
    klines[30].vol = 30000.0
    klines[30].kdj_j = 40.0
    return klines


def test_config_validate():
    B1B2Config().validate()
    with pytest.raises(ValueError):
        B1B2Config(observe_min=5, observe_max=3).validate()
    with pytest.raises(ValueError):
        B1B2Config(b2_min_pct=0).validate()
    with pytest.raises(ValueError):
        B1B2Config(b2_min_vol_ratio=0.5).validate()


def test_has_b1_in_window():
    klines = _make_b2_klines()
    cfg = B1B2Config(observe_min=3, observe_max=5)
    # index=30 往前 4 天有 B1
    assert has_b1_in_window(klines, 30, cfg) is True
    # index=21 往前找不到（不足窗口）
    assert has_b1_in_window(klines, 21, cfg) is False


def test_is_b2_signal_ok():
    klines = _make_b2_klines()
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is True


def test_is_b2_signal_reject_low_pct():
    klines = _make_b2_klines()
    klines[30].pct_chg = 2.0
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is False


def test_is_b2_signal_reject_low_volume():
    klines = _make_b2_klines()
    klines[30].vol = 12000.0  # 1.2 倍，不足 2 倍
    cfg = B1B2Config(observe_min=3, observe_max=5)
    assert is_b2_signal(klines, 30, cfg) is False


def test_is_high_open_skip():
    klines = _make_klines(40)
    # entry_idx=31 开盘较前收高开 8%
    klines[30].close = 100.0
    klines[31].open = 108.0
    cfg = B1B2Config(max_gap_open_pct=5.0)
    assert is_high_open_skip(klines, 30, 31, cfg) is True
    cfg2 = B1B2Config(max_gap_open_pct=None)
    assert is_high_open_skip(klines, 30, 31, cfg2) is False


def test_run_stock_klines_smoke():
    klines = _make_b2_klines()
    # 给足 B2 后一天的成交量/价格，至少能正常跑完不抛异常
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config())
    assert isinstance(trades, list)


# ---- CRITICAL regression:日期窗口过滤的 None 守卫 ----
# 之前:b1_b2_backtest.py:120 直接 `entry_k.trade_date > end_date`,在 end_date=None 时抛 TypeError
# 修复:start/end 任一为 None 时跳过该端比较
# 触发条件:walk-forward 调用时只传 start_date 不传 end_date(或反过来)


def test_date_window_start_only_no_typeerror():
    """只设 start_date、end_date=None 时不应抛 TypeError。"""
    klines = _make_b2_klines()
    with patch("modules.active_market_value.apply_active_mv_gate", return_value=GateAction.OPEN):
        trades = _run_stock_klines(
            klines,
            B1B2Config(),
            _default_loop_config(),
            start_date="20260101",
            end_date=None,
        )
    assert isinstance(trades, list)


def test_date_window_end_only_no_typeerror():
    """只设 end_date、start_date=None 时不应抛 TypeError。"""
    klines = _make_b2_klines()
    with patch("modules.active_market_value.apply_active_mv_gate", return_value=GateAction.OPEN):
        trades = _run_stock_klines(
            klines,
            B1B2Config(),
            _default_loop_config(),
            start_date=None,
            end_date="20260215",
        )
    assert isinstance(trades, list)


def test_date_window_both_none_no_typeerror():
    """start/end 都为 None(默认)不崩。"""
    klines = _make_b2_klines()
    with patch("modules.active_market_value.apply_active_mv_gate", return_value=GateAction.OPEN):
        trades = _run_stock_klines(
            klines,
            B1B2Config(),
            _default_loop_config(),
            start_date=None,
            end_date=None,
        )
    assert isinstance(trades, list)


def test_date_window_start_after_b2_excludes_entry():
    """start_date 设到 B2 之后 → 该 B2 不应被开仓(返回 trades 为空)。"""
    klines = _make_b2_klines()
    with patch("modules.active_market_value.apply_active_mv_gate", return_value=GateAction.OPEN):
        # B2 在 index=30 → 20260131;start 设到 20260201(之后),该 B2 被窗口过滤掉
        trades = _run_stock_klines(
            klines,
            B1B2Config(),
            _default_loop_config(),
            start_date="20260201",
            end_date=None,
        )
    # 20260201 之后的 klines 不再触发 B2,所以空仓
    assert trades == []


# ---- walk-forward happy path ----


def test_walkforward_happy_path_single_stock():
    """单股 walk-forward 至少能跑完不抛异常,返回 dict 结构。"""
    from modules.backtest import b1_b2_backtest as b2b
    from modules import active_market_value as amv

    # 准备一个长 K 线序列(_make_b2_klines 固定 40 天,这里直接造一个 600 天的)
    long_klines = _make_klines(600)

    with (
        patch.object(b2b, "get_kline_data", return_value=long_klines),
        patch.object(amv, "apply_active_mv_gate", return_value=GateAction.OPEN),
    ):
        result = b2b.run_b1_b2_walkforward(
            ts_codes=["TEST.SZ"],
            days=600,
            folds=2,
            window=50,
            config=B1B2Config(),
            loop_config=_default_loop_config(),
        )
    assert isinstance(result, dict)
    # 必须有 folds 列表
    assert "folds" in result
    assert isinstance(result["folds"], list)
