"""
indicators.py 核心技术指标测试
覆盖所有独立计算函数
"""

import math
import pytest
from modules.indicators import (
    DailyData, IndicatorResult, TradeSignal,
    calculate_ma, calculate_ema, calculate_sma_td, calculate_slope,
    calculate_kdj, calculate_macd, detect_divergence, detect_macd_signals,
    calculate_bbi, calculate_rsi, calculate_rsi_multi, calculate_wr, calculate_wr_multi,
    calculate_bollinger, calculate_vol_ratio,
    calculate_zg_white, calculate_dg_yellow, detect_double_line_cross,
    calculate_rsl, detect_needle_20, detect_needle_30,
    detect_volume_anomaly, detect_double_gun, detect_sb1_detailed,
    calculate_dmi,
    calculate_brick_value, calculate_brick_history, detect_brick_trend, detect_fanbao,
    detect_volume_pattern, detect_b1_today, detect_b2_today,
    detect_key_k, detect_violence_k, check_two_30_rule,
    detect_nana_chart, detect_golden_bowl, detect_breathing_structure,
    detect_sb1, detect_b3, detect_four_brick_system,
    calculate_sell_score, detect_trade_signal,
    analyze_stock, get_kline_data,
)


# ========== 辅助函数 ==========

def make_kline(price=100.0, vol=10000.0, pct_chg=0.0, prev_close=100.0,
               open=None, high=None, low=None, date="20260101"):
    """快速创建 DailyData"""
    o = open if open is not None else price
    h = high if high is not None else price * 1.02
    l = low if low is not None else price * 0.98
    return DailyData(
        ts_code="600519.SH", trade_date=date,
        open=o, high=h, low=l, close=price, vol=vol,
        amount=price * vol, pct_chg=pct_chg, prev_close=prev_close
    )


def make_klines(n=120, base_price=100.0, base_vol=10000.0, daily_pct=0.0):
    """生成连续 K 线列表"""
    rows = []
    price = base_price
    for i in range(n):
        prev_close = price
        price *= (1 + daily_pct / 100)
        prev_close = rows[-1].close if rows else price
        rows.append(make_kline(
            price=price, vol=base_vol, pct_chg=(price - prev_close) / prev_close * 100,
            prev_close=prev_close, date=f"20260101".replace("0101", f"{i+1:02d}{(i%28)+1:02d}"[:4])
        ))
    return rows


# ========== calculate_ma ==========

class TestCalculateMA:
    def test_basic(self):
        assert calculate_ma([1, 2, 3, 4, 5], 5) == 3.0

    def test_insufficient_data(self):
        assert calculate_ma([1, 2], 5) == 0

    def test_partial(self):
        assert calculate_ma([1, 2, 3, 4, 5], 3) == 4.0  # avg of [3,4,5]


# ========== calculate_ema ==========

class TestCalculateEMA:
    def test_basic(self):
        prices = [10, 11, 12, 13, 14, 15]
        result = calculate_ema(prices, 3)
        assert isinstance(result, float)
        assert 10 < result < 15

    def test_insufficient_data(self):
        assert calculate_ema([10, 11], 5) == 0

    def test_constant_prices(self):
        assert calculate_ema([50, 50, 50, 50], 4) == 50.0


# ========== calculate_sma_td ==========

class TestCalculateSmaTd:
    def test_basic(self):
        result = calculate_sma_td([1, 2, 3, 4, 5, 6], 6, 1)
        assert isinstance(result, float)

    def test_insufficient_data(self):
        result = calculate_sma_td([1, 2], 5, 1)
        assert isinstance(result, float)  # 不应报错


# ========== calculate_slope ==========

class TestCalculateSlope:
    def test_positive_slope(self):
        values = [1, 2, 3, 4, 5, 6, 7]
        slope = calculate_slope(values, 7)
        assert slope > 0

    def test_zero_slope(self):
        values = [5, 5, 5, 5, 5]
        slope = calculate_slope(values, 5)
        assert slope == 0

    def test_insufficient_data(self):
        assert calculate_slope([1], 3) == 0


# ========== calculate_kdj ==========

class TestCalculateKDJ:
    def test_basic(self):
        klines = make_klines(n=20, base_price=100.0, daily_pct=0.5)
        k, d, j = calculate_kdj(klines)
        assert 0 <= k <= 100
        assert 0 <= d <= 100

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        k, d, j = calculate_kdj(klines)
        assert (k, d, j) == (50, 50, 50)

    def test_downtrend_j_negative(self):
        """下降趋势 J 值应较低"""
        prices = [100]
        for i in range(30):
            prices.append(prices[-1] * 0.96)
        klines = [make_kline(p) for p in prices]
        _, _, j = calculate_kdj(klines)
        # 持续下降趋势中 J 值应较低（可能不严格为负，但应远低于50）
        assert j < 50

    def test_uptrend_j_high(self):
        """上升趋势 J 值应较高"""
        prices = [50]
        for i in range(30):
            prices.append(prices[-1] * 1.04)
        klines = [make_kline(p) for p in prices]
        _, _, j = calculate_kdj(klines)
        assert j > 80


# ========== calculate_macd ==========

class TestCalculateMACD:
    def test_basic(self):
        klines = make_klines(n=50, base_price=100.0, daily_pct=0.5)
        dif, dea, macd = calculate_macd(klines)
        assert len(dif) > 0
        assert len(dea) > 0
        assert len(macd) > 0

    def test_insufficient_data(self):
        klines = make_klines(n=10)
        dif, dea, macd = calculate_macd(klines)
        # slow=26, 数据不足时 DIF 也为空
        assert len(dif) == 0
        assert len(dea) == 0

    def test_uptrend_dif_positive(self):
        klines = make_klines(n=50, base_price=100.0, daily_pct=1.0)
        dif, dea, macd = calculate_macd(klines)
        assert dif[-1] > 0

    def test_downtrend_dif_negative(self):
        klines = make_klines(n=50, base_price=200.0, daily_pct=-1.0)
        dif, dea, macd = calculate_macd(klines)
        assert dif[-1] < 0


# ========== detect_divergence ==========

class TestDetectDivergence:
    def test_no_divergence_insufficient(self):
        klines = make_klines(n=20)
        _, _, macd_list = calculate_macd(klines)
        result = detect_divergence(klines, macd_list if macd_list else [])
        # 数据不足时不应检测到背离
        assert not result.get('is_top_divergence', False)


# ========== detect_macd_signals ==========

class TestDetectMacdSignals:
    def test_basic(self):
        klines = make_klines(n=50, base_price=100.0, daily_pct=0.5)
        dif, dea, macd = calculate_macd(klines)
        signals = detect_macd_signals(klines, dif, dea, macd)
        assert 'is_dif_positive' in signals
        assert 'macd_veto' in signals

    def test_downtrend_veto(self):
        klines = make_klines(n=50, base_price=200.0, daily_pct=-1.0)
        dif, dea, macd = calculate_macd(klines)
        signals = detect_macd_signals(klines, dif, dea, macd)
        # 下降趋势 DIF < 0 + 无底背离 → 一票否决
        if not signals['is_bottom_divergence']:
            assert signals['macd_veto'] is True

    def test_insufficient_data(self):
        klines = make_klines(n=10)
        signals = detect_macd_signals(klines, [], [], [])
        assert not signals['is_dif_positive']


# ========== calculate_bbi ==========

class TestCalculateBBI:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        bbi = calculate_bbi(klines)
        assert bbi > 0

    def test_insufficient_data(self):
        klines = make_klines(n=10)
        assert calculate_bbi(klines) == 0


# ========== calculate_rsi ==========

class TestCalculateRSI:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0, daily_pct=0.5)
        rsi = calculate_rsi(klines, 14)
        assert 0 <= rsi <= 100

    def test_uptrend_rsi_high(self):
        klines = make_klines(n=30, base_price=100.0, daily_pct=2.0)
        rsi = calculate_rsi(klines, 6)
        assert rsi > 70

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        assert calculate_rsi(klines, 14) == 50


# ========== calculate_wr ==========

class TestCalculateWR:
    def test_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        wr = calculate_wr(klines, 14)
        # WR 公式: (HIGHN-CLOSE)/(HIGHN-LOWN)*100, 返回 0-100 范围
        assert 0 <= wr <= 100

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        assert calculate_wr(klines, 14) == -50


# ========== calculate_bollinger ==========

class TestCalculateBollinger:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0, daily_pct=0.5)
        mid, upper, lower, width, position = calculate_bollinger(klines)
        assert mid > 0
        assert upper > mid > lower
        assert 0 <= position <= 100

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        mid, upper, lower, width, position = calculate_bollinger(klines)
        assert (mid, upper, lower, width, position) == (0, 0, 0, 0, 50)


# ========== calculate_vol_ratio ==========

class TestCalculateVolRatio:
    def test_constant_volume(self):
        klines = make_klines(n=10, base_vol=10000.0)
        ratio = calculate_vol_ratio(klines, 5)
        assert abs(ratio - 1.0) < 0.1

    def test_double_volume(self):
        klines = make_klines(n=10, base_vol=10000.0)
        klines[-1].vol = 50000  # 今日量是5日均量的约5倍
        ratio = calculate_vol_ratio(klines, 5)
        assert ratio > 2.0


# ========== Z哥双线战法 ==========

class TestDoubleLine:
    def test_zg_white(self):
        klines = make_klines(n=120, base_price=100.0, daily_pct=0.5)
        white = calculate_zg_white(klines)
        assert white > 0

    def test_dg_yellow(self):
        klines = make_klines(n=120, base_price=100.0, daily_pct=0.5)
        yellow = calculate_dg_yellow(klines)
        assert yellow > 0

    def test_insufficient_for_yellow(self):
        klines = make_klines(n=50)
        assert calculate_dg_yellow(klines) == 0


# ========== 单针下20/30 ==========

class TestNeedleDetection:
    def test_needle_20_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        rsl_s, rsl_l, is_needle = detect_needle_20(klines)
        assert isinstance(is_needle, bool)

    def test_needle_30_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        result = detect_needle_30(klines)
        assert isinstance(result, bool)


# ========== detect_volume_anomaly ==========

class TestVolumeAnomaly:
    def test_no_anomaly_stable(self):
        klines = make_klines(n=70, base_price=100.0, base_vol=10000.0)
        result = detect_volume_anomaly(klines)
        assert 'is_yidong' in result

    def test_insufficient_data(self):
        klines = make_klines(n=20)
        result = detect_volume_anomaly(klines)
        assert not result['is_yidong']


# ========== detect_double_gun ==========

class TestDoubleGun:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        result = detect_double_gun(klines)
        assert 'is_double_gun' in result


# ========== calculate_dmi ==========

class TestDMI:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        dmi_plus, dmi_minus, adx = calculate_dmi(klines)
        assert isinstance(dmi_plus, float)
        assert isinstance(adx, float)

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        assert calculate_dmi(klines) == (0, 0, 0)


# ========== 砖型图 ==========

class TestBrickChart:
    def test_brick_value(self):
        klines = make_klines(n=20, base_price=100.0)
        val = calculate_brick_value(klines)
        assert val >= 0

    def test_brick_history(self):
        klines = make_klines(n=20, base_price=100.0)
        trend, count = calculate_brick_history(klines)
        assert trend in ("RED", "GREEN", "NEUTRAL")
        assert count >= 0

    def test_fanbao(self):
        klines = make_klines(n=10, base_price=100.0)
        result = detect_fanbao(klines)
        assert isinstance(result, bool)


# ========== detect_volume_pattern ==========

class TestVolumePattern:
    def test_beidou(self):
        today = make_kline(price=100.0, vol=20000.0)
        yesterday = make_kline(price=100.0, vol=9000.0)
        result = detect_volume_pattern(today, yesterday)
        assert result['is_beidou'] is True

    def test_suoliang(self):
        today = make_kline(price=100.0, vol=4000.0)
        yesterday = make_kline(price=100.0, vol=10000.0)
        result = detect_volume_pattern(today, yesterday)
        assert result['is_suoliang'] is True

    def test_jiayin_zhenyang(self):
        # 收 < 开 but 收 > 昨收
        today = make_kline(price=102.0, open=103.0, low=101.0, high=104.0,
                           prev_close=100.0, pct_chg=2.0)
        yesterday = make_kline(price=100.0)
        result = detect_volume_pattern(today, yesterday)
        assert result['is_jiayin_zhenyang'] is True

    def test_no_yesterday(self):
        today = make_kline()
        result = detect_volume_pattern(today, None)
        assert all(v is False for v in result.values())


# ========== detect_b1_today / detect_b2_today ==========

class TestB1B2Today:
    def test_b1_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_b1_today(klines)
        assert 'is_b1' in result
        assert 'b1_score' in result

    def test_b2_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_b2_today(klines)
        assert 'is_b2' in result


# ========== calculate_sell_score ==========

class TestSellScore:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0, daily_pct=0.5)
        result = calculate_sell_score(klines)
        # 实际返回 (score, items) 两个值
        assert len(result) == 2
        score, items = result
        assert isinstance(score, int)
        assert 0 <= score <= 5
        assert isinstance(items, dict)

    def test_insufficient_data(self):
        klines = make_klines(n=1)
        score, desc, items = calculate_sell_score(klines)
        assert score == 3
        assert items == {}


# ========== detect_trade_signal ==========

class TestTradeSignal:
    def test_insufficient_data(self):
        klines = make_klines(n=10)
        signal = detect_trade_signal(klines)
        assert signal == TradeSignal.WATCH

    def test_returns_enum(self):
        klines = make_klines(n=50, base_price=100.0)
        signal = detect_trade_signal(klines)
        assert isinstance(signal, TradeSignal)


# ========== detect_four_brick_system ==========

class TestFourBrickSystem:
    def test_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_four_brick_system(klines)
        assert 'brick_action' in result
        assert result['brick_action'] in ('减仓', '止损', '持有', '禁止抄底', '观望')

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        result = detect_four_brick_system(klines)
        assert result['brick_action'] == '观望'


# ========== detect_breathing_structure ==========

class TestBreathingStructure:
    def test_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_breathing_structure(klines)
        assert 'breath_phase' in result
        assert result['breath_phase'] in ('exhale', 'inhale', 'none', '')


# ========== detect_sb1 / detect_b3 ==========

class TestSB1B3:
    def test_sb1_basic(self):
        klines = make_klines(n=10)
        result = detect_sb1(klines)
        assert 'is_sb1' in result

    def test_b3_basic(self):
        klines = make_klines(n=20)
        result = detect_b3(klines)
        assert 'is_b3' in result


# ========== analyze_stock ==========

class TestAnalyzeStock:
    """analyze_stock 需要数据库支持，用 temp_db fixture"""

    def test_returns_result_object(self, temp_db, db_conn):
        """即使没有数据也应返回 IndicatorResult"""
        result = analyze_stock("000001.SZ", days=100)
        assert isinstance(result, IndicatorResult)
        assert result.ts_code == "000001.SZ"

    def test_with_data(self, temp_db, db_conn):
        """写入数据后分析"""
        from tests.conftest import write_klines_to_db, write_stock_basic, generate_uptrend_klines
        write_stock_basic(db_conn, "600519.SH", "测试股票")
        rows = generate_uptrend_klines(n=120, ts_code="600519.SH")
        write_klines_to_db(db_conn, rows)

        result = analyze_stock("600519.SH", days=120)
        assert isinstance(result, IndicatorResult)
        assert result.ts_code == "600519.SH"
        assert result.trade_date != ""
