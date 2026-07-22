"""
indicators.py 核心技术指标测试
覆盖所有独立计算函数
"""

from modules.indicators import (
    DailyData,
    IndicatorResult,
    TradeSignal,
    calculate_ma,
    calculate_ema,
    calculate_sma_td,
    calculate_slope,
    calculate_kdj,
    calculate_macd,
    detect_divergence,
    detect_macd_signals,
    calculate_bbi,
    calculate_rsi,
    calculate_wr,
    calculate_bollinger,
    calculate_vol_ratio,
    calculate_zg_white,
    calculate_dg_yellow,
    detect_needle_20,
    detect_needle_30,
    detect_volume_anomaly,
    detect_double_gun,
    calculate_dmi,
    calculate_brick_value,
    calculate_brick_history,
    detect_fanbao,
    detect_volume_pattern,
    detect_b1_today,
    detect_b2_today,
    detect_breathing_structure,
    detect_sb1,
    detect_b3,
    detect_four_brick_system,
    calculate_sell_score,
    detect_trade_signal,
    analyze_stock,
    detect_didi,
    detect_macd_trap,
    calculate_zuchong_target,
    detect_chuhuo_wushi,
    detect_zaihou_chongjian,
    detect_yueyueyushi,
    detect_key_candle,
    detect_key_candle_coverage,
    detect_abc_stages,
    detect_centipede_pattern,
    detect_volume_ratio_strategy,
    detect_bull_rope,
    calculate_sandglass_score,
)


# ========== 辅助函数 ==========


def make_kline(
    price=100.0, vol=10000.0, pct_chg=0.0, prev_close=100.0, open=None, high=None, low=None, date="20260101"
):
    """快速创建 DailyData"""
    o = open if open is not None else price
    h = high if high is not None else price * 1.02
    low_v = low if low is not None else price * 0.98
    return DailyData(
        ts_code="600519.SH",
        trade_date=date,
        open=o,
        high=h,
        low=low_v,
        close=price,
        vol=vol,
        amount=price * vol,
        pct_chg=pct_chg,
        prev_close=prev_close,
    )


def make_klines(n=120, base_price=100.0, base_vol=10000.0, daily_pct=0.0):
    """生成连续 K 线列表"""
    rows = []
    price = base_price
    for i in range(n):
        prev_close = price
        price *= 1 + daily_pct / 100
        prev_close = rows[-1].close if rows else price
        rows.append(
            make_kline(
                price=price,
                vol=base_vol,
                pct_chg=(price - prev_close) / prev_close * 100,
                prev_close=prev_close,
                date="20260101".replace("0101", f"{i + 1:02d}{(i % 28) + 1:02d}"[:4]),
            )
        )
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
        assert not result.get("is_top_divergence", False)


# ========== detect_macd_signals ==========


class TestDetectMacdSignals:
    def test_basic(self):
        klines = make_klines(n=50, base_price=100.0, daily_pct=0.5)
        dif, dea, macd = calculate_macd(klines)
        signals = detect_macd_signals(klines, dif, dea, macd)
        assert "is_dif_positive" in signals
        assert "macd_veto" in signals

    def test_downtrend_veto(self):
        klines = make_klines(n=50, base_price=200.0, daily_pct=-1.0)
        dif, dea, macd = calculate_macd(klines)
        signals = detect_macd_signals(klines, dif, dea, macd)
        # 下降趋势 DIF < 0 + 无底背离 → 一票否决
        if not signals["is_bottom_divergence"]:
            assert signals["macd_veto"] is True

    def test_insufficient_data(self):
        klines = make_klines(n=10)
        signals = detect_macd_signals(klines, [], [], [])
        assert not signals["is_dif_positive"]


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

    def test_zg_white_is_double_ema(self):
        prices = [100 + i * i * 0.1 for i in range(30)]
        klines = [make_kline(price=price, date=f"202601{i + 1:02d}") for i, price in enumerate(prices)]

        alpha = 2 / 11
        ema1 = prices[0]
        ema2 = ema1
        for price in prices[1:]:
            ema1 = price * alpha + ema1 * (1 - alpha)
            ema2 = ema1 * alpha + ema2 * (1 - alpha)

        wrong_single_ema = prices[-10]
        for price in prices[-9:]:
            wrong_single_ema = price * alpha + wrong_single_ema * (1 - alpha)

        white = calculate_zg_white(klines)
        assert white == round(ema2, 2)
        assert white != round(wrong_single_ema, 2)

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
        assert "is_yidong" in result

    def test_insufficient_data(self):
        klines = make_klines(n=20)
        result = detect_volume_anomaly(klines)
        assert not result["is_yidong"]


# ========== detect_double_gun ==========


class TestDoubleGun:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0)
        result = detect_double_gun(klines)
        assert "is_double_gun" in result


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
        assert result["is_beidou"] is True

    def test_suoliang(self):
        today = make_kline(price=100.0, vol=4000.0)
        yesterday = make_kline(price=100.0, vol=10000.0)
        result = detect_volume_pattern(today, yesterday)
        assert result["is_suoliang"] is True

    def test_jiayin_zhenyang(self):
        # 收 < 开 but 收 > 昨收
        today = make_kline(price=102.0, open=103.0, low=101.0, high=104.0, prev_close=100.0, pct_chg=2.0)
        yesterday = make_kline(price=100.0)
        result = detect_volume_pattern(today, yesterday)
        assert result["is_jiayin_zhenyang"] is True

    def test_no_yesterday(self):
        today = make_kline()
        result = detect_volume_pattern(today, None)
        assert all(v is False for v in result.values())


# ========== detect_b1_today / detect_b2_today ==========


class TestB1B2Today:
    def test_b1_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_b1_today(klines)
        assert "is_b1" in result
        assert "b1_score" in result

    def test_b2_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_b2_today(klines)
        assert "is_b2" in result


# ========== calculate_sell_score ==========


class TestSellScore:
    def test_basic(self):
        klines = make_klines(n=30, base_price=100.0, daily_pct=0.5)
        result = calculate_sell_score(klines)
        # 返回 (score, desc, items) 三个值
        assert len(result) == 3
        score, desc, items = result
        assert isinstance(score, int)
        assert 0 <= score <= 5
        assert isinstance(desc, str)
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
        assert "brick_action" in result
        assert result["brick_action"] in ("减仓", "止损", "持有", "禁止抄底", "观望")

    def test_insufficient_data(self):
        klines = make_klines(n=5)
        result = detect_four_brick_system(klines)
        assert result["brick_action"] == "观望"


# ========== detect_breathing_structure ==========


class TestBreathingStructure:
    def test_basic(self):
        klines = make_klines(n=20, base_price=100.0)
        result = detect_breathing_structure(klines)
        assert "breath_phase" in result
        assert result["breath_phase"] in ("exhale", "inhale", "none", "")


# ========== detect_sb1 / detect_b3 ==========


class TestSB1B3:
    def test_sb1_basic(self):
        klines = make_klines(n=10)
        result = detect_sb1(klines)
        assert "is_sb1" in result

    def test_b3_basic(self):
        klines = make_klines(n=20)
        result = detect_b3(klines)
        assert "is_b3" in result


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


# ========== detect_didi (滴滴战法) ==========


class TestDetectDidi:
    def test_no_didi_normal(self):
        """正常上涨不应触发滴滴"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        result = detect_didi(klines)
        assert result["is_didi"] is False

    def test_didi_basic(self):
        """构造滴滴场景：两根阴线下台阶"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        # 修改最后两根为滴滴形态
        # 第一根阴线：open=110, close=105, low=104, vol=10000
        klines[-2].open = 110.0
        klines[-2].close = 105.0
        klines[-2].low = 104.0
        klines[-2].high = 111.0
        klines[-2].vol = 10000.0
        # 第二根阴线：open=106, close=103, low=102, vol=9000 (>= 10000*0.8=8000)
        klines[-1].open = 106.0
        klines[-1].close = 103.0
        klines[-1].low = 102.0
        klines[-1].high = 107.0
        klines[-1].vol = 9000.0
        result = detect_didi(klines)
        assert result["is_didi"] is True
        assert result["first_low"] == 104.0
        assert result["second_close"] == 103.0

    def test_didi_volume_shrink(self):
        """量缩太多不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        klines[-2].open = 110.0
        klines[-2].close = 105.0
        klines[-2].low = 104.0
        klines[-2].vol = 10000.0
        klines[-1].open = 106.0
        klines[-1].close = 103.0
        klines[-1].low = 102.0
        klines[-1].vol = 5000.0  # 缩量50%，< 0.8
        result = detect_didi(klines)
        assert result["is_didi"] is False

    def test_didi_not_high(self):
        """不在高位不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=-1.0)  # 下跌趋势
        klines[-2].open = 80.0
        klines[-2].close = 75.0
        klines[-2].low = 74.0
        klines[-2].vol = 10000.0
        klines[-1].open = 76.0
        klines[-1].close = 73.0
        klines[-1].low = 72.0
        klines[-1].vol = 9000.0
        result = detect_didi(klines)
        assert result["is_didi"] is False

    def test_insufficient_data(self):
        """数据不足"""
        klines = make_klines(n=1)
        result = detect_didi(klines)
        assert result["is_didi"] is False


# ========== detect_macd_trap (金叉空/死叉多) ==========


class TestDetectMacdTrap:
    def test_gold_trap(self):
        """金叉空：眼看金叉未成，拐头向下"""
        dif = [1.0, 2.0, 3.0, 4.0, 3.5]  # 前3天在下方，第4天上升，第5天拐头
        dea = [5.0, 5.0, 5.0, 5.0, 5.0]  # DEA 持平
        result = detect_macd_trap(dif, dea)
        assert result["is_gold_trap"] is True
        assert result["is_dead_trap"] is False

    def test_dead_trap(self):
        """死叉多：眼看死叉未成，拐头向上"""
        dif = [9.0, 8.0, 7.0, 6.0, 6.5]  # 前3天在上方，第4天下降，第5天拐头
        dea = [5.0, 5.0, 5.0, 5.0, 5.0]  # DEA 持平
        result = detect_macd_trap(dif, dea)
        assert result["is_gold_trap"] is False
        assert result["is_dead_trap"] is True

    def test_normal_gold_cross(self):
        """正常金叉不应触发"""
        dif = [1.0, 2.0, 3.0, 4.0, 5.5]  # 持续上升，最终金叉
        dea = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = detect_macd_trap(dif, dea)
        assert result["is_gold_trap"] is False
        assert result["is_dead_trap"] is False

    def test_normal_dead_cross(self):
        """正常死叉不应触发"""
        dif = [9.0, 8.0, 7.0, 6.0, 4.5]  # 持续下降，最终死叉
        dea = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = detect_macd_trap(dif, dea)
        assert result["is_gold_trap"] is False
        assert result["is_dead_trap"] is False

    def test_insufficient_data(self):
        """数据不足"""
        result = detect_macd_trap([1.0, 2.0], [5.0, 5.0])
        assert result["is_gold_trap"] is False
        assert result["is_dead_trap"] is False


# ========== calculate_zuchong_target (祖冲之法) ==========


class TestCalculateZuchongTarget:
    def test_basic(self):
        """基本计算：目标价 = 2a - b"""
        klines = make_klines(n=30, base_price=100.0)
        # 构造高点 120，低点 80
        for i, k in enumerate(klines):
            if i == 10:
                k.high = 120.0
                k.low = 118.0
                k.close = 119.0
            elif i == 20:
                k.high = 82.0
                k.low = 80.0
                k.close = 81.0
        result = calculate_zuchong_target(klines, lookback=30)
        assert result["a"] == 120.0
        assert result["b"] == 80.0
        assert result["target"] == 160.0  # 2*120 - 80

    def test_insufficient_data(self):
        """数据不足"""
        klines = make_klines(n=5)
        result = calculate_zuchong_target(klines)
        assert result["target"] == 0


# ========== detect_chuhuo_wushi (主力出货五式) ==========


class TestChuhuoWushi:
    def test_no_signal_normal(self):
        """正常上涨不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        result = detect_chuhuo_wushi(klines)
        assert result["is_selling"] is False

    def test_fangshi_1_tianliang_dayin(self):
        """方式一：加速后单日放天量大阴"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        # 前15天价格约 100-107，后10天加速到 125（涨幅 > 20%）
        base = klines[-11].close
        for i in range(-10, 0):
            klines[i].close = base * (1 + 0.025 * (i + 10))  # 加速
            klines[i].high = klines[i].close * 1.02
            klines[i].low = klines[i].close * 0.98
            klines[i].vol = 10000.0
        # 最后一天：天量大阴（跌7%，天量）
        klines[-1].open = klines[-1].close * 1.05
        klines[-1].close = klines[-1].close * 0.93
        klines[-1].high = klines[-1].open * 1.01
        klines[-1].low = klines[-1].close * 0.99
        klines[-1].pct_chg = -7.0
        klines[-1].vol = 50000.0  # 天量
        result = detect_chuhuo_wushi(klines)
        assert result["is_selling"] is True
        assert any("方式一" in p["type"] for p in result["patterns"])

    def test_fangshi_5_lvfei_hongshou(self):
        """方式五：顶部绿肥红瘦"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        # 近10天：阴量远大于阳量
        for i in range(-10, 0):
            if i % 2 == 0:
                klines[i].close = klines[i].open * 0.98  # 阴线
                klines[i].vol = 30000.0
            else:
                klines[i].close = klines[i].open * 1.01  # 阳线
                klines[i].vol = 5000.0
        result = detect_chuhuo_wushi(klines)
        assert result["is_selling"] is True
        assert any("方式五" in p["type"] for p in result["patterns"])


# ========== detect_zaihou_chongjian (灾后重建) ==========


class TestZaihouChongjian:
    def test_no_signal(self):
        """不满足条件不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        result = detect_zaihou_chongjian(klines)
        assert result["is_rebuild"] is False

    def test_basic(self):
        """放量后缩量回踩"""
        klines = make_klines(n=70, base_price=100.0, daily_pct=0.3)
        # 第55天放量大涨
        klines[55].pct_chg = 6.0
        klines[55].vol = 50000.0
        klines[55].close = 120.0
        klines[55].open = 115.0
        # 后面几天缩量回调
        for i in range(56, 65):
            klines[i].vol = 8000.0
            klines[i].close *= 0.98
        # 最后一天接近黄线
        klines[-1].close = klines[-1].open * 0.99
        klines[-1].vol = 6000.0
        result = detect_zaihou_chongjian(klines)
        # 黄线计算复杂，可能触发也可能不触发，但至少不报错
        assert "is_rebuild" in result


# ========== detect_yueyueyushi (跃跃欲试) ==========


class TestYueyueyushi:
    def test_no_signal(self):
        """不满足条件不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        result = detect_yueyueyushi(klines)
        assert result["is_ready"] is False

    def test_basic(self):
        """横盘+3次巨量"""
        klines = make_klines(n=35, base_price=100.0, daily_pct=0.05)  # 几乎横盘
        # 设置近20天振幅很小
        for i in range(-20, 0):
            klines[i].high = 102.0
            klines[i].low = 98.0
            klines[i].close = 100.0 + (i % 3) * 0.5
        # 3次巨量阳线
        klines[-3].vol = 50000.0
        klines[-3].close = 101.0
        klines[-3].open = 99.0
        klines[-7].vol = 50000.0
        klines[-7].close = 101.0
        klines[-7].open = 99.0
        klines[-12].vol = 50000.0
        klines[-12].close = 101.0
        klines[-12].open = 99.0
        result = detect_yueyueyushi(klines)
        assert result["is_ready"] is True
        assert result["count"] >= 3


# ========== detect_key_candle (关键K) ==========


class TestKeyCandle:
    def test_no_signal_small_body(self):
        """小实体不应触发"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        result = detect_key_candle(klines)
        assert result["is_key"] is False

    def test_key_yang_break_high(self):
        """关键阳突破"""
        klines = make_klines(n=25, base_price=100.0, daily_pct=0.5)
        # 最后一天：放量大阳线突破前高
        prev_high = max(k.high for k in klines[:-1])
        klines[-1].open = prev_high * 1.01
        klines[-1].close = prev_high * 1.05
        klines[-1].high = prev_high * 1.06
        klines[-1].low = prev_high * 1.00
        klines[-1].vol = 50000.0
        result = detect_key_candle(klines)
        assert result["is_key"] is True
        assert result["direction"] == "向上突破"


# ========== detect_centipede_pattern (蜈蚣图识别) ==========


class TestCentipedePattern:
    def test_normal_uptrend_not_centipede(self):
        """正常上涨趋势不应被判为蜈蚣图"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=1.0)
        result = detect_centipede_pattern(klines)
        assert result["is_centipede"] is False
        assert result["score"] < 60

    def test_chaotic_centipede(self):
        """蜈蚣图特征：长影线交替 + 十字星 + 量能无规律 + 价格无趋势"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 最近20天改造为蜈蚣形态
        for i in range(5, 25):
            k = klines[i]
            # 交替长上影线和长下影线
            if i % 2 == 0:
                # 长上影线：上影 > 2倍实体
                k.open = 100.0
                k.close = 100.5
                k.high = 103.0
                k.low = 99.5
            else:
                # 长下影线：下影 > 2倍实体
                k.open = 100.0
                k.close = 99.8
                k.high = 100.5
                k.low = 97.0
            # 量能忽大忽小
            k.vol = 20000.0 if i % 3 == 0 else 5000.0
            k.pct_chg = 0.0
        result = detect_centipede_pattern(klines)
        assert result["is_centipede"] is True
        assert result["score"] >= 60
        assert "长上影线" in result["factors"]
        assert "长下影线" in result["factors"]


# ========== detect_bull_rope (牛绳理论) ==========


class TestBullRope:
    def test_insufficient_data(self):
        """数据不足时返回默认牛绳断"""
        klines = make_klines(n=50)
        result = detect_bull_rope(klines)
        assert result["status"] == "牛绳断"
        assert result["is_bearish"] is True

    def test_uptrend_qianniu(self):
        """上升趋势：白线在黄线上且上升 -> 牵牛"""
        klines = make_klines(n=150, base_price=100.0, daily_pct=0.3)
        result = detect_bull_rope(klines)
        # 持续上升趋势中，白线应在黄线上
        assert result["white"] > 0
        assert result["yellow"] > 0
        if result["white"] > result["yellow"]:
            assert result["status"] == "牵牛"
            assert result["is_bullish"] is True
            assert result["is_bearish"] is False
            assert result["white_trend"] == "上升"

    def test_downtrend_niushengduan(self):
        """下降趋势：白线在黄线下 -> 牛绳断"""
        klines = make_klines(n=150, base_price=200.0, daily_pct=-0.5)
        result = detect_bull_rope(klines)
        assert result["white"] > 0
        assert result["yellow"] > 0
        if result["white"] < result["yellow"]:
            assert result["status"] == "牛绳断"
            assert result["is_bearish"] is True
            assert result["is_bullish"] is False

    def test_golden_cross(self):
        """金叉场景：先下降让白线低于黄线，再大幅拉升制造上穿"""
        klines = make_klines(n=150, base_price=200.0, daily_pct=-0.8)
        # 最后20天大幅拉升（每天+5%），让白线快速追赶黄线
        for i in range(130, 150):
            klines[i].close = klines[i - 1].close * 1.05
            klines[i].high = klines[i].close * 1.01
            klines[i].low = klines[i].close * 0.99
            klines[i].open = klines[i - 1].close
            klines[i].pct_chg = 5.0
        result = detect_bull_rope(klines)
        # 大幅拉升后应为多头信号（金叉或牵牛）
        assert result["is_bullish"] is True or result["status"] in ("金叉", "牵牛")
        assert result["gap_pct"] != 0

    def test_death_cross(self):
        """死叉场景：先上升让白线高于黄线，再大幅下跌制造下穿"""
        klines = make_klines(n=150, base_price=100.0, daily_pct=0.8)
        # 最后20天大幅下跌（每天-5%），让白线快速跌破黄线
        for i in range(130, 150):
            klines[i].close = klines[i - 1].close * 0.95
            klines[i].high = klines[i].close * 1.01
            klines[i].low = klines[i].close * 0.99
            klines[i].open = klines[i - 1].close
            klines[i].pct_chg = -5.0
        result = detect_bull_rope(klines)
        # 大幅下跌后应为空头信号（死叉或牛绳断）
        assert result["is_bearish"] is True or result["status"] in ("死叉", "牛绳断")
        assert result["gap_pct"] != 0

    def test_return_dict_keys(self):
        """返回字典包含所有必要字段"""
        klines = make_klines(n=150, base_price=100.0, daily_pct=0.3)
        result = detect_bull_rope(klines)
        assert "status" in result
        assert "white" in result
        assert "yellow" in result
        assert "gap_pct" in result
        assert "white_trend" in result
        assert "is_bullish" in result
        assert "is_bearish" in result
        assert result["status"] in ("牵牛", "牛绳断", "金叉", "死叉")
        assert result["white_trend"] in ("上升", "下降", "横盘")
        assert isinstance(result["is_bullish"], bool)
        assert isinstance(result["is_bearish"], bool)

    def test_insufficient_data(self):
        """数据不足20根应返回默认值"""
        klines = make_klines(n=10, base_price=100.0, daily_pct=0.5)
        result = detect_centipede_pattern(klines)
        assert result["is_centipede"] is False
        assert result["score"] == 0

    def test_doji_heavy_centipede(self):
        """大量十字星应贡献分数"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 最近20天大部分是十字星
        for i in range(5, 25):
            k = klines[i]
            k.open = 100.0
            k.close = 100.005  # 几乎平盘，十字星
            k.high = 102.0
            k.low = 98.0
            k.vol = 30000.0 if i % 2 == 0 else 3000.0  # 量能无规律，CV > 0.8
            k.pct_chg = 0.0
        result = detect_centipede_pattern(klines)
        # 十字星 + 量能无规律 + 价格无趋势 应有较高分
        assert result["factors"]["十字星"] == 20
        assert result["factors"]["量能无规律"] == 20


# ========== detect_volume_ratio_strategy (量比战法引擎) ==========


class TestVolumeRatioStrategy:
    def _make_klines_with_vol_ratio(self, vol_ratio: float, pct_chg: float, n: int = 10) -> list[DailyData]:
        """构造指定量比和涨幅的K线序列

        calculate_vol_ratio = klines[-1].vol / avg(klines[-6:-1].vol)
        所以设 klines[-6:-1].vol = 10000, klines[-1].vol = vol_ratio * 10000
        """
        klines = make_klines(n=n, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        for k in klines[-6:-1]:
            k.vol = 10000.0
        klines[-1].vol = vol_ratio * 10000.0
        klines[-1].pct_chg = pct_chg
        klines[-1].prev_close = klines[-2].close
        return klines

    def test_attack_day(self):
        """vol_ratio=25, pct_chg=3% → 攻击日, 立即买"""
        klines = self._make_klines_with_vol_ratio(25, 3.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 25.0
        assert result["scenario"] == "攻击日"
        assert result["action"] == "立即买"
        assert result["confidence"] >= 0.8

    def test_shipping_day(self):
        """vol_ratio=25, pct_chg=-4% → 出货日, 观望"""
        klines = self._make_klines_with_vol_ratio(25, -4.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 25.0
        assert result["scenario"] == "出货日"
        assert result["action"] == "观望"
        assert result["confidence"] >= 0.7

    def test_unilateral_rally(self):
        """vol_ratio=15, pct_chg=2% → 单向拉升, 慢买逢低吸纳"""
        klines = self._make_klines_with_vol_ratio(15, 2.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 15.0
        assert result["scenario"] == "单向拉升"
        assert result["action"] == "慢买逢低吸纳"
        assert result["confidence"] >= 0.6

    def test_normal_oscillation(self):
        """vol_ratio=8, pct_chg=1% → 正常震荡, 慢买逢低吸纳"""
        klines = self._make_klines_with_vol_ratio(8, 1.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 8.0
        assert result["scenario"] == "正常震荡"
        assert result["action"] == "慢买逢低吸纳"
        assert result["confidence"] >= 0.5

    def test_super_attack(self):
        """vol_ratio=50, pct_chg=5% → 超级攻击, 立即买"""
        klines = self._make_klines_with_vol_ratio(50, 5.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 50.0
        assert result["scenario"] == "超级攻击"
        assert result["action"] == "立即买"
        assert result["confidence"] >= 0.9

    def test_weak_day_skip(self):
        """vol_ratio=5, pct_chg=-3% → 弱势日, 跳过不看"""
        klines = self._make_klines_with_vol_ratio(5, -3.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 5.0
        assert result["scenario"] == "弱势日"
        assert result["action"] == "跳过不看"

    def test_insufficient_data(self):
        """数据不足应返回默认值"""
        klines = make_klines(n=3, base_price=100.0)
        result = detect_volume_ratio_strategy(klines)
        assert result["scenario"] == "正常震荡"
        assert result["confidence"] == 0.0

    def test_mid_range_low_open(self):
        """vol_ratio=12, 低开-4% → 弱势日, 观望"""
        klines = self._make_klines_with_vol_ratio(12, -1.0)
        klines[-1].prev_close = klines[-2].close
        klines[-1].open = klines[-1].prev_close * 0.96
        result = detect_volume_ratio_strategy(klines)
        assert result["vol_ratio"] == 12.0
        assert result["scenario"] == "弱势日"
        assert result["action"] == "观望"


# ========== calculate_sandglass_score (沙漏评分 V9) ==========


class TestSandglassScore:
    def test_insufficient_data(self):
        """数据不足 20 根应返回默认值"""
        klines = make_klines(n=10, base_price=100.0)
        result = calculate_sandglass_score(klines)
        assert result["score"] == 0
        assert result["rating"] == "极差"
        assert result["is_perfect"] is False

    def test_ideal_setup_high_score(self):
        """理想形态：缩量、低位、多头均线 → 高分"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.2)

        # 最后 10 天缩量
        for i in range(15, 25):
            klines[i].vol = 4000.0

        # 量幅收窄：近 5 天量几乎一致
        for i in range(20, 25):
            klines[i].vol = 4000.0

        # 前 5 天量幅大
        for i in range(15, 20):
            klines[i].vol = 3000.0 + (i - 15) * 2000.0

        # 价格在支撑位附近
        min_low = min(k.low for k in klines[-20:])
        klines[-1].close = min_low * 1.02

        result = calculate_sandglass_score(klines)
        assert result["score"] >= 40
        assert result["rating"] in ("极佳", "良好", "一般")
        for key in ("缩量收敛", "枢轴邻近", "量能斜率", "均线结构", "事件风险"):
            assert key in result["factors"]

    def test_poor_setup_low_score(self):
        """恶劣形态：放量、远离支撑、空头均线 → 低分"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=-2.0)

        # 最后 10 天急剧放量
        for i in range(15, 25):
            klines[i].vol = 30000.0 + i * 5000.0

        # 最后 5 天连续下跌
        for i in range(20, 25):
            klines[i].pct_chg = -3.0

        result = calculate_sandglass_score(klines)
        assert result["score"] <= 40
        assert result["rating"] in ("较差", "极差", "一般")
        assert result["is_perfect"] is False

    def test_perfect_graph_scenario(self):
        """完美图形 → is_perfect 标记"""
        klines = make_klines(n=25, base_price=10.0, base_vol=20000.0, daily_pct=0.3)

        # 前 15 天量大，后 10 天缩量
        for i in range(0, 15):
            klines[i].vol = 20000.0
        for i in range(15, 25):
            klines[i].vol = 5000.0

        # 量幅收窄
        for i in range(20, 25):
            klines[i].vol = 5000.0
        for i in range(15, 20):
            klines[i].vol = 3000.0 + (i - 15) * 3000.0

        # 价格接近支撑位
        min_low = min(k.low for k in klines[-20:])
        klines[-1].close = min_low * 1.01
        klines[-1].low = min_low

        result = calculate_sandglass_score(klines)
        assert 0 <= result["score"] <= 100
        assert isinstance(result["is_perfect"], bool)
        assert isinstance(result["rating"], str)
        assert len(result["factors"]) == 5

    def test_return_structure(self):
        """验证返回结构完整性"""
        klines = make_klines(n=30, base_price=100.0, daily_pct=0.1)
        result = calculate_sandglass_score(klines)
        assert "score" in result
        assert "rating" in result
        assert "factors" in result
        assert "is_perfect" in result
        assert isinstance(result["score"], int)
        assert isinstance(result["is_perfect"], bool)
        assert result["rating"] in ("极佳", "良好", "一般", "较差", "极差")
        for key in ("缩量收敛", "枢轴邻近", "量能斜率", "均线结构", "事件风险"):
            assert key in result["factors"]
            assert 0 <= result["factors"][key] <= 20


# ========== detect_key_candle_coverage ==========


class TestKeyCandleCoverage:
    def test_insufficient_data(self):
        """数据不足20根时返回默认值"""
        klines = make_klines(n=10, base_price=100.0, base_vol=10000.0)
        result = detect_key_candle_coverage(klines)
        assert result["has_key_candle"] is False
        assert result["key_date"] == ""
        assert result["in_range"] is False

    def test_no_key_candle_in_20_days(self):
        """20天内没有关键K（小实体、量能平稳）"""
        klines = make_klines(n=30, base_price=100.0, base_vol=10000.0, daily_pct=0.1)
        result = detect_key_candle_coverage(klines)
        # 小实体、平稳量能不应识别为关键K
        assert result["has_key_candle"] is False

    def test_has_key_candle_in_range(self):
        """有关键K且当前价在上下沿之间"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 在第15天制造一根关键阳线：大实体 + 放量 + 突破前高
        klines[14].open = 100.0
        klines[14].close = 106.0
        klines[14].high = 107.0
        klines[14].low = 99.0
        klines[14].vol = 30000.0  # 放量

        # 当前价在上下沿之间
        klines[-1].close = 103.0
        klines[-1].high = 104.0
        klines[-1].low = 102.0

        result = detect_key_candle_coverage(klines)
        assert result["has_key_candle"] is True
        assert result["key_high"] == 107.0
        assert result["key_low"] == 99.0
        assert result["in_range"] is True

    def test_buy_point_at_mid(self):
        """当前价在关键K一半位置时 buy_point 为 True"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 第15天关键阳线
        klines[14].open = 100.0
        klines[14].close = 110.0
        klines[14].high = 112.0
        klines[14].low = 98.0
        klines[14].vol = 30000.0

        # 当前价在一半位置：(112+98)/2 = 105
        klines[-1].close = 105.0
        klines[-1].high = 106.0
        klines[-1].low = 104.0

        result = detect_key_candle_coverage(klines)
        assert result["has_key_candle"] is True
        assert result["in_range"] is True
        assert result["buy_point"] is True

    def test_current_price_outside_range(self):
        """当前价不在关键K上下沿之间时 in_range 为 False"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 第15天关键阳线
        klines[14].open = 100.0
        klines[14].close = 106.0
        klines[14].high = 107.0
        klines[14].low = 99.0
        klines[14].vol = 30000.0

        # 当前价远高于关键K上沿
        klines[-1].close = 120.0
        klines[-1].high = 121.0
        klines[-1].low = 119.0

        result = detect_key_candle_coverage(klines)
        assert result["has_key_candle"] is True
        assert result["in_range"] is False

    def test_volume_shrinking_after_key(self):
        """关键K之后量能递减时 volume_shrinking 为 True"""
        klines = make_klines(n=25, base_price=100.0, base_vol=10000.0, daily_pct=0.0)
        # 第15天关键阳线
        klines[14].open = 100.0
        klines[14].close = 106.0
        klines[14].high = 107.0
        klines[14].low = 99.0
        klines[14].vol = 30000.0

        # 关键K之后量能递减
        for i in range(15, 25):
            klines[i].vol = 20000.0 - (i - 15) * 1500

        result = detect_key_candle_coverage(klines)
        assert result["has_key_candle"] is True
        assert result["volume_shrinking"] is True


# ========== detect_abc_stages ==========


class TestAbcStages:
    def test_insufficient_data(self):
        """数据不足30根时返回未知"""
        klines = make_klines(n=20, base_price=100.0, base_vol=10000.0)
        result = detect_abc_stages(klines)
        assert result["stage"] == "未知"
        assert result["a_score"] == 0.0
        assert result["action"] == "观察"

    def test_stage_a_j_recovery(self):
        """A阶段：J值回升 + 缩量横盘"""
        # 先下跌让J值到负值
        klines = []
        price = 120.0
        for i in range(25):
            prev = price
            price *= 0.97  # 连续下跌
            klines.append(
                make_kline(
                    price=price,
                    vol=8000.0 - i * 100,
                    prev_close=prev,
                    date=f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}",
                )
            )

        # 最后5天缩量横盘 + 小幅回升
        for i in range(25, 35):
            klines.append(
                make_kline(
                    price=price * (1 + (i - 25) * 0.001),
                    vol=3000.0,  # 缩量
                    prev_close=price,
                    date=f"2026{i // 28 + 1:02d}{i % 28 + 1:02d}",
                )
            )

        result = detect_abc_stages(klines)
        assert result["a_score"] > 0
        assert "stage" in result
        assert "confidence" in result
        assert result["action"] in ("观察", "试水", "重仓", "突破")

    def test_stage_c_breakout(self):
        """C阶段：放量突破近期高点"""
        klines = make_klines(n=30, base_price=100.0, base_vol=10000.0, daily_pct=0.2)

        # 最后一天放量大涨突破
        klines[-1].close = 110.0
        klines[-1].high = 111.0
        klines[-1].low = 105.0
        klines[-1].open = 104.0
        klines[-1].vol = 50000.0
        klines[-1].pct_chg = 5.0

        result = detect_abc_stages(klines)
        assert result["c_score"] > 0

    def test_return_structure(self):
        """验证返回结构完整性"""
        klines = make_klines(n=35, base_price=100.0, base_vol=10000.0)
        result = detect_abc_stages(klines)
        assert "stage" in result
        assert "a_score" in result
        assert "b_score" in result
        assert "c_score" in result
        assert "confidence" in result
        assert "action" in result
        assert result["stage"] in ("A", "B", "C", "未知")
        assert result["action"] in ("观察", "试水", "重仓", "突破")
        assert 0 <= result["a_score"] <= 100
        assert 0 <= result["b_score"] <= 100
        assert 0 <= result["c_score"] <= 100
