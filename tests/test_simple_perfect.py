"""简单完美图形（三种形态）回归测试

来源：笔记《交易系统.md》§2.2.3
"""

from __future__ import annotations

import pytest


def _make(closes, vols=None, highs=None, lows=None, opens=None, start_price=10.0):
    """构造 DailyData 序列（未给的高/低/开按收盘价派生）"""
    from modules.indicators import DailyData

    n = len(closes)
    vols = vols or [1000.0] * n
    klines = []
    prev_close = closes[0]
    for i, close in enumerate(closes):
        open_ = opens[i] if opens else prev_close
        high = highs[i] if highs else max(open_, close) * 1.01
        low = lows[i] if lows else min(open_, close) * 0.99
        klines.append(
            DailyData(
                ts_code="TEST.SZ",
                trade_date=f"202501{i:02d}" if i < 31 else f"20250{i}",
                open=open_,
                high=high,
                low=low,
                close=close,
                vol=vols[i],
                amount=close * vols[i],
                pct_chg=0.0,
                prev_close=prev_close,
            )
        )
        prev_close = close
    return klines


def _flat(n: int, price: float = 10.0, vol: float = 800.0):
    return _make([price] * n, vols=[vol] * n)


# ==================== 通用契约 ====================


@pytest.mark.parametrize("fn_name", ["detect_simple_perfect_1", "detect_simple_perfect_2", "detect_simple_perfect_3"])
def test_result_contract(fn_name):
    """三个函数都返回统一结构，且空数据不抛异常"""
    from modules.screener import simple_perfect as sp

    fn = getattr(sp, fn_name)
    result = fn([])
    assert set(result) >= {"is_match", "reasons", "details"}
    assert result["is_match"] is False


# ==================== 类型 A：经典 ====================


def test_t1_pullback_must_be_half_volume():
    """缩量必须「缩半量」：单根缩到 0.4× 算达标，只缩到 0.8× 不算"""
    from modules.screener.simple_perfect import _find_rise_and_pullback

    base = [10.0] * 10
    vols = [1000.0] * 10
    # 上涨段：连续 2 根上行且量 > 昨量 × 1.2
    closes = base + [10.3, 10.8]
    up_vols = vols + [1600.0, 2000.0]
    seg_vol = (1600 + 2000) / 2

    ok = _make(closes + [10.7], vols=up_vols + [seg_vol * 0.4])
    assert _find_rise_and_pullback(ok) is not None

    too_soft = _make(closes + [10.7], vols=up_vols + [seg_vol * 0.8])
    assert _find_rise_and_pullback(too_soft) is None


def test_t1_pullback_min_bars_default_is_one():
    """默认只需 1 根缩量（可用 pullback_min_bars 调回 2）"""
    from modules.screener import simple_perfect as sp

    assert sp.PULLBACK_MIN_BARS == 1
    assert sp.PULLBACK_VOL_RATIO == 0.5


def test_t1_requires_min_bars():
    from modules.screener.simple_perfect import detect_simple_perfect_1

    result = detect_simple_perfect_1(_flat(10))
    assert result["is_match"] is False
    assert "数据不足" in result["reasons"][0]


def test_t1_rejects_dayetu_lower_lows():
    """大爷图：低点不断降低 → 不命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_1

    closes = [20 - i * 0.4 for i in range(40)]  # 单调下跌
    result = detect_simple_perfect_1(_make(closes, vols=[1000 + i * 20 for i in range(40)]))
    assert result["is_match"] is False


def test_t1_rejects_when_doubled():
    """绝对涨幅已翻倍 → 不命中（末端票）"""
    from modules.screener.simple_perfect import detect_simple_perfect_1

    closes = [5.0] * 20 + [5 + i * 0.5 for i in range(20)]  # 5 → 15（3 倍）
    vols = [800.0] * 20 + [2000.0] * 20
    result = detect_simple_perfect_1(_make(closes, vols=vols))
    assert result["is_match"] is False


# ==================== 类型 B：异动后的横盘 ====================


def test_t2_requires_min_bars():
    from modules.screener.simple_perfect import detect_simple_perfect_2

    result = detect_simple_perfect_2(_flat(10))
    assert result["is_match"] is False
    assert "数据不足" in result["reasons"][0]


def test_t2_rejects_trending_not_range():
    """非横盘（趋势票，振幅 > 15%）→ 不命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_2

    closes = [10 + i * 0.3 for i in range(40)]
    result = detect_simple_perfect_2(_make(closes))
    assert result["is_match"] is False
    assert any("非横盘" in r for r in result["reasons"])


def test_t2_rejects_range_without_yidong():
    """横盘但无放量异动 → 不命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_2

    result = detect_simple_perfect_2(_flat(40, price=10.0, vol=800.0))
    assert result["is_match"] is False
    assert any("无放量异动" in r for r in result["reasons"])


def test_t2_positive_range_then_yidong():
    """长期横盘 → 放量大阳（>5%，量 ≥ 前5日均量×1.5）→ 异动后横住 → 命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_2

    n = 30
    closes = [10.0] * n
    vols = [800.0] * n
    yidong = 21
    closes[yidong] = 10.7  # 较前一日 10.0 上涨 7%
    vols[yidong] = 3000.0  # 前5日均量约 1240 → 2.4×
    for i in range(yidong + 1, n):
        closes[i] = 10.5  # 异动后横住在箱体内
        vols[i] = 900.0

    result = detect_simple_perfect_2(_make(closes, vols=vols))
    assert result["is_match"] is True, result["reasons"]
    assert result["details"].get("yidong_date")


def test_t2_rejects_breakout_after_yidong():
    """异动后未横住（突破箱体上沿）→ 不命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_2

    n = 30
    closes = [10.0] * n
    vols = [800.0] * n
    yidong = 21
    closes[yidong] = 10.7
    vols[yidong] = 3000.0
    for i in range(yidong + 1, n):
        closes[i] = 10.7 + (i - yidong) * 0.6  # 一路向上，突破箱体
        vols[i] = 2000.0

    result = detect_simple_perfect_2(_make(closes, vols=vols))
    # 注：突破后先被「非横盘」（20 根振幅 > 15%）拦下，「未横住」是其后的第二道闸门，
    # 此处只断言不命中且给出了原因。
    assert result["is_match"] is False
    assert result["reasons"]


# ==================== 类型 C：完美绿帽 / W型 ====================


def test_t3_requires_min_bars():
    from modules.screener.simple_perfect import detect_simple_perfect_3

    result = detect_simple_perfect_3(_flat(100))
    assert result["is_match"] is False
    assert "数据不足" in result["reasons"][0]


def _green_hat_series(digest_closes: list[float]):
    """构造「横盘 → 放量站上大哥线 → 一波流 → 大绿帽 → 消化」序列

    注意：黄线需 114 根窗口，因此「放量站上」必须发生在 index ≥ 113 之后，
    且一波流涨幅要在最后 60 根窗口内完成，否则判定窗口扫不到。
    """
    closes = [10.0] * 114
    vols = [800.0] * 114
    closes[113] = 10.12  # 放量站上大哥线（量 > 前5日均量 × 1.5）
    vols[113] = 4000.0
    for j in range(34):  # 一波流：10.12 → 13.52（+33%）
        closes.append(10.12 + (j + 1) * 0.1)
        vols.append(800.0)
    closes.append(closes[-1] * 0.94)  # 顶部放量下杀（大绿帽）
    vols.append(3500.0)
    closes += digest_closes
    vols += [400.0] * len(digest_closes)  # 消化期缩量（需低于上涨段均量 × 0.7）
    return _make(closes, vols=vols)


def test_t3_positive_green_hat():
    """放量站上大哥线 → 一波流 ≥20% → 顶部放量下杀 → 缩量消化且不破黄线 → 命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_3

    result = detect_simple_perfect_3(_green_hat_series([12.7] * 30))
    assert result["is_match"] is True, result["reasons"]
    assert result["details"].get("gain", 0) >= 0.20


def test_t3_rejects_breakdown():
    """消化期一路阴跌、跌破大哥线 → 不命中"""
    from modules.screener.simple_perfect import detect_simple_perfect_3

    digest = [13.0 - i * 0.18 for i in range(30)]  # 13 → 7.8
    result = detect_simple_perfect_3(_green_hat_series(digest))
    assert result["is_match"] is False
    assert any(("跌破" in r) or ("创新低" in r) or ("死叉" in r) for r in result["reasons"])
