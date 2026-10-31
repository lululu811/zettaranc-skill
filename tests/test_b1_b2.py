"""B1观察+B2确认策略的单元测试。"""

from unittest.mock import patch

import pytest

from modules.indicators import DailyData
from modules.strategies.b1_b2 import B1B2Config, has_b1_in_window, is_b2_signal, is_high_open_skip
from modules.backtest.b1_b2_backtest import _run_stock_klines, _default_loop_config
from modules.active_market_gate import GateAction


class _FakeGate:
    """假闸门 adapter —— 注入给 engine，替代真实闸门实现。

    这是"注入而非现场创建"换来的好处：测试不再 patch module 属性，
    而是直接给 engine 一个满足闸门 interface 的替身。
    """

    def __init__(self, action: GateAction = GateAction.OPEN, by_date: dict | None = None) -> None:
        self.action = action
        self.by_date = by_date or {}
        self.calls: list[str] = []

    def evaluate(self, date: str) -> GateAction:
        self.calls.append(date)
        return self.by_date.get(date, self.action)


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
    trades = _run_stock_klines(
        klines,
        B1B2Config(),
        _default_loop_config(),
        start_date="20260101",
        end_date=None,
        gate=_FakeGate(GateAction.OPEN),
    )
    assert isinstance(trades, list)


def test_date_window_end_only_no_typeerror():
    """只设 end_date、start_date=None 时不应抛 TypeError。"""
    klines = _make_b2_klines()
    trades = _run_stock_klines(
        klines,
        B1B2Config(),
        _default_loop_config(),
        start_date=None,
        end_date="20260215",
        gate=_FakeGate(GateAction.OPEN),
    )
    assert isinstance(trades, list)


def test_date_window_both_none_no_typeerror():
    """start/end 都为 None(默认)不崩。"""
    klines = _make_b2_klines()
    trades = _run_stock_klines(
        klines,
        B1B2Config(),
        _default_loop_config(),
        start_date=None,
        end_date=None,
        gate=_FakeGate(GateAction.OPEN),
    )
    assert isinstance(trades, list)


def test_date_window_start_after_b2_excludes_entry():
    """start_date 设到 B2 之后 → 该 B2 不应被开仓(返回 trades 为空)。"""
    klines = _make_b2_klines()
    # B2 在 index=30 → 20260131;start 设到 20260201(之后),该 B2 被窗口过滤掉
    trades = _run_stock_klines(
        klines,
        B1B2Config(),
        _default_loop_config(),
        start_date="20260201",
        end_date=None,
        gate=_FakeGate(GateAction.OPEN),
    )
    # 20260201 之后的 klines 不再触发 B2,所以空仓
    assert trades == []


# ---- walk-forward happy path ----


def test_walkforward_happy_path_single_stock():
    """单股 walk-forward 至少能跑完不抛异常,返回 dict 结构。"""
    from modules.backtest import b1_b2_backtest as b2b

    # 准备一个长 K 线序列(_make_b2_klines 固定 40 天,这里直接造一个 600 天的)
    long_klines = _make_klines(600)

    with patch.object(b2b, "get_kline_data", return_value=long_klines):
        result = b2b.run_b1_b2_walkforward(
            ts_codes=["TEST.SZ"],
            days=600,
            folds=2,
            window=50,
            config=B1B2Config(),
            loop_config=_default_loop_config(),
            gate=_FakeGate(GateAction.OPEN),
        )
    assert isinstance(result, dict)
    # 必须有 folds 列表
    assert "folds" in result
    assert isinstance(result["folds"], list)


# ---- CRITICAL regression：活跃市值闸门的开仓判定 ----
# 2026-08-23 的统一重构 3e882b9 把 _gate 的返回类型从 str 改成 GateAction，
# 迁移了 `== "CLEAR"` 却漏掉 `!= "OPEN"`。GateAction 是普通 Enum（不是 str, Enum），
# `GateAction.OPEN != "OPEN"` 恒为 True，导致 B1/B2 的开仓判断永远为真跳过，
# 自 v4.3.0 发布起 zt backtest b1_b2 恒返回 0 笔成交。
# 下面的测试锁死"闸门动作 → 是否开仓"的真实行为，而不是源码文本形状。


def test_gate_open_allows_entry():
    """闸门 OPEN → B2 信号应当真的开仓。"""
    klines = _make_b2_klines()
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config(), gate=_FakeGate(GateAction.OPEN))
    assert len(trades) == 1, f"闸门 OPEN 时应有一笔成交，实际 {len(trades)} 笔"
    # B2 在 index=30，次一交易日(index=31)开盘买入
    assert trades[0].entry_date == klines[31].trade_date


def test_gate_wait_blocks_entry():
    """闸门 WAIT → 不允许开新仓。"""
    klines = _make_b2_klines()
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config(), gate=_FakeGate(GateAction.WAIT))
    assert trades == []


def test_gate_clear_blocks_entry():
    """闸门 CLEAR → 不允许开新仓（无持仓可强平时为空）。"""
    klines = _make_b2_klines()
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config(), gate=_FakeGate(GateAction.CLEAR))
    assert trades == []


def test_gate_clear_forces_position_exit():
    """持仓后闸门转 CLEAR → 强制平仓。"""
    klines = _make_b2_klines()
    entry_date = klines[31].trade_date

    # 开仓日放行，之后转 CLEAR 触发强平
    class _DatedGate:
        """开仓日放行，之后转 CLEAR。"""

        def evaluate(self, date: str) -> GateAction:
            return GateAction.CLEAR if date > entry_date else GateAction.OPEN

    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config(), gate=_DatedGate())
    assert len(trades) == 1, f"应有一笔被强平的成交，实际 {len(trades)} 笔"
    assert trades[0].exit_reason == "活跃市值清仓"


def test_gate_disabled_allows_entry():
    """闸门关闭（enabled=False，默认）→ 等价于 OPEN，不应阻断开仓。

    闸门默认在所有入口都是关闭的，修复前即使闸门关闭也会因比较方式错误而跳过全部开仓。
    """
    klines = _make_b2_klines()
    # enabled=False 时 apply_active_mv_gate 直接返回 OPEN，不查数据
    trades = _run_stock_klines(klines, B1B2Config(), _default_loop_config())
    assert len(trades) == 1, f"闸门关闭时应正常开仓，实际 {len(trades)} 笔"
