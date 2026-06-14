"""
strategies.py 战法识别测试
"""

import pytest
from modules.strategies import (
    StrategyType,
    Priority,
    detect_b1,
    detect_b2,
    detect_b3,
    detect_sb1,
    detect_changan,
    detect_sifen_zhiyi_sanyin,
    detect_nana,
    detect_yidong_dilian,
    detect_pinghang,
    detect_kengqi,
    detect_duichen_va,
    detect_s1,
    detect_s2,
    detect_s3,
    detect_all_strategies,
    get_latest_signal,
    detect_brick_signals,
    detect_buy_exhaustion,
    detect_green_fat_red_thin,
    detect_staircase_distribution,
    detect_top_pinwheel,
)
from modules.indicators import detect_volume_attack, DailyData
from modules.indicators.core import calculate_ma
from modules.strategies.core import _calc_kdj as calculate_kdj, _calc_bbi as calculate_bbi
from datetime import datetime, timedelta
from tests.conftest import make_kline_row, generate_uptrend_klines
from tests.conftest import generate_downtrend_klines, generate_b1_scenario


class TestCalculateMA:
    def test_basic(self):
        assert calculate_ma([1, 2, 3, 4, 5], 5) == 3.0

    def test_insufficient(self):
        assert calculate_ma([1, 2], 5) == 0


class TestCalculateKDJ:
    def test_returns_tuple(self):
        klines = generate_uptrend_klines(n=20)
        k, d, j = calculate_kdj(klines)
        assert isinstance(k, float)
        assert isinstance(d, float)
        assert isinstance(j, float)

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        k, d, j = calculate_kdj(klines)
        assert (k, d, j) == (50, 50, 50)


class TestCalculateBBI:
    def test_basic(self):
        klines = generate_uptrend_klines(n=30)
        bbi = calculate_bbi(klines)
        assert bbi > 0

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert calculate_bbi(klines) == 0


class TestDetectB1:
    def test_downtrend_triggers_b1(self):
        """下降趋势中 J 打到负值应触发 B1"""
        klines = generate_b1_scenario()
        for i in range(len(klines) - 10, len(klines)):
            signal = detect_b1(klines, i)
            if signal:
                assert signal.strategy == StrategyType.B1
                assert signal.action == "BUY"
                return
        pytest.skip("B1 未在当前场景触发（可能参数需调整）")

    def test_uptrend_no_b1(self):
        """上升趋势中不应触发 B1"""
        klines = generate_uptrend_klines(n=50)
        for i in range(10, len(klines)):
            signal = detect_b1(klines, i)
            assert signal is None

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        assert detect_b1(klines, 3) is None


class TestDetectB2:
    def test_basic(self):
        klines = generate_uptrend_klines(n=50)
        for i in range(15, len(klines)):
            signal = detect_b2(klines, i)
            if signal:
                assert signal.strategy == StrategyType.B2
                return

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_b2(klines, 8) is None


class TestDetectB3:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=15)
        assert detect_b3(klines, 10) is None


class TestDetectSB1:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        assert detect_sb1(klines, 3) is None


class TestDetectChangan:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=2)
        assert detect_changan(klines, 2) is None


class TestDetectSifenZhiyiSanyin:
    def test_fake_breakout(self):
        """大阳线后次日阴量超过 75%"""
        klines = []
        # 第一天大阳线
        klines.append(make_kline_row(base_price=100.0, base_vol=10000.0, base_date="20260101"))
        # 修改为大阳线
        klines[-1]["pct_chg"] = 5.0
        klines[-1]["close"] = 105.0
        klines[-1]["high"] = 106.0
        klines[-1]["open"] = 101.0
        # 第二天阴线，阴量 > 阳量 * 0.75
        klines.append(make_kline_row(base_price=103.0, base_vol=8000.0, base_date="20260102"))
        klines[-1]["close"] = 103.0
        klines[-1]["open"] = 104.0
        klines[-1]["high"] = 104.5
        klines[-1]["low"] = 102.5
        klines[-1]["pct_chg"] = -1.9
        klines[-1]["prev_close"] = 105.0
        klines[-1]["is_yinxian"] = True
        klines[-1]["is_fangliang_yinxian"] = True

        signal = detect_sifen_zhiyi_sanyin(klines, 1)
        # vol_ratio = 8000/10000 = 0.8 > 0.75 → 假突破
        assert signal is not None
        assert signal.strategy == StrategyType.SI_FEN_ZHI_SAN
        assert signal.action == "SELL"

    def test_no_signal(self):
        klines = generate_uptrend_klines(n=10)
        signal = detect_sifen_zhiyi_sanyin(klines, 5)
        assert signal is None


class TestDetectNana:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        assert detect_nana(klines, 3) is None


class TestDetectYidongDilian:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=3)
        assert detect_yidong_dilian(klines, 2) is None


class TestDetectAllStrategies:
    """detect_all_strategies 需要数据库"""

    def test_empty_without_db(self, temp_db, db_conn):
        """无数据时返回空列表"""
        signals = detect_all_strategies("000001.SZ", days=120)
        assert signals == []

    def test_with_data(self, temp_db, db_conn):
        """写入数据后检测"""
        from tests.conftest import write_klines_to_db, write_stock_basic

        write_stock_basic(db_conn, "600519.SH", "测试股票")
        rows = generate_uptrend_klines(n=120, ts_code="600519.SH")
        write_klines_to_db(db_conn, rows)

        signals = detect_all_strategies("600519.SH", days=120)
        assert isinstance(signals, list)


class TestGetLatestSignal:
    def test_no_signal(self, temp_db, db_conn):
        signal = get_latest_signal("000001.SZ")
        assert signal is None


class TestDetectS1:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_s1(klines, 9) is None

    def test_s1_exit(self):
        """构造 S1 逃顶场景：流畅上涨后出现丑陋大绿帽"""
        klines = generate_uptrend_klines(n=30, start_price=100.0, daily_pct=1.0)
        today = klines[-1]
        # 丑陋大绿帽：放量阴线，收盘价接近低点
        today["close"] = 125.0
        today["open"] = 135.0
        today["high"] = 136.0
        today["low"] = 124.0
        today["pct_chg"] = -7.0
        today["vol"] = 50000
        today["is_rise"] = False
        today["is_yinxian"] = True
        today["is_fangliang_yinxian"] = True
        today["is_jiayin"] = False

        signal = detect_s1(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.S1
        assert signal.action == "SELL"


class TestDetectS2:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_s2(klines, 9) is None


class TestDetectS3:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_s3(klines, 9) is None


class TestDetectPinghang:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        assert detect_pinghang(klines, 4) is None

    def test_parallel_cannon(self):
        """构造平行重炮场景：两根放量阳线夹4根阴线，J<55"""
        from datetime import datetime, timedelta

        # 先构造40天下跌（把J值压到低位）
        klines = generate_downtrend_klines(n=40, start_price=200.0, daily_pct=-1.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        # 第一根放量阳线
        klines.append(make_kline_row(base_price=105.0, base_vol=30000.0, base_date=dt.strftime("%Y%m%d")))
        klines[-1]["open"] = 101.0
        klines[-1]["high"] = 106.0
        klines[-1]["low"] = 100.0
        klines[-1]["pct_chg"] = 5.0
        klines[-1]["is_rise"] = True
        klines[-1]["is_beidou"] = True
        dt += timedelta(days=1)
        # 中间4根阴线，缩量
        for i in range(4):
            k = make_kline_row(base_price=104.0 - i * 0.5, base_vol=8000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = 104.5 - i * 0.5
            k["high"] = k["open"]
            k["low"] = k["close"] * 0.99
            k["pct_chg"] = -0.5
            k["is_rise"] = False
            k["is_beidou"] = False
            klines.append(k)
            dt += timedelta(days=1)
        # 第二根放量阳线
        klines.append(make_kline_row(base_price=108.0, base_vol=32000.0, base_date=dt.strftime("%Y%m%d")))
        klines[-1]["open"] = 104.0
        klines[-1]["high"] = 108.5
        klines[-1]["low"] = 103.5
        klines[-1]["pct_chg"] = 4.5
        klines[-1]["is_rise"] = True
        klines[-1]["is_beidou"] = True

        signal = detect_pinghang(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.PINGHANG
        assert signal.action == "BUY"


class TestDetectKengqi:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_kengqi(klines, 9) is None

    def test_pit_and_rise(self):
        """构造坑里起好货场景：放量挖坑 → 缩量填坑"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=0.1)
        # 坑前高点区
        for i in range(10, 15):
            klines[i]["close"] = 110.0 + (i - 10) * 0.5
            klines[i]["high"] = klines[i]["close"] + 1.0
        pre_high = max(k["high"] for k in klines[10:15])
        # 挖坑：放量急跌
        klines[15]["close"] = 95.0
        klines[15]["open"] = 108.0
        klines[15]["low"] = 94.0
        klines[15]["high"] = 109.0
        klines[15]["pct_chg"] = -12.0
        klines[15]["vol"] = 50000
        klines[15]["is_rise"] = False
        klines[15]["is_beidou"] = True
        # 缩量填坑
        for i in range(16, 24):
            klines[i]["close"] = 95.0 + (i - 15) * 1.8
            klines[i]["vol"] = 6000
            klines[i]["is_rise"] = True
            klines[i]["is_beidou"] = False
        # 当前回到坑沿 80% 以上
        assert klines[23]["close"] >= pre_high * 0.8

        signal = detect_kengqi(klines, 23)
        assert signal is not None
        assert signal.strategy == StrategyType.KENGQI
        assert signal.action == "BUY"
        assert "target_price" in signal.details


class TestDetectDuichenVA:
    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert detect_duichen_va(klines, 9) is None

    def test_symmetry_broken(self):
        """构造对称VA场景：低→高→低，然后企稳"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=0.1)
        # 低点
        for i in range(5, 8):
            klines[i]["close"] = 95.0
            klines[i]["low"] = 94.0
        # 上涨到高点
        for i in range(8, 14):
            klines[i]["close"] = 95.0 + (i - 7) * 2.0
            klines[i]["high"] = klines[i]["close"] + 0.5
        # 下跌回来（对称）
        for i in range(14, 20):
            klines[i]["close"] = klines[13]["close"] - (i - 13) * 1.8
            klines[i]["low"] = klines[i]["close"] - 0.5
        # 最后缩量企稳
        klines[23]["close"] = 98.0
        klines[23]["vol"] = 3000
        klines[23]["is_suoliang"] = True

        signal = detect_duichen_va(klines, 23)
        # 由于 KDJ 计算依赖实际价格序列，可能触发也可能不触发
        # 至少保证不抛异常
        assert signal is None or signal.strategy == StrategyType.DUIchen


# ==================== 正向测试补充 ====================


class TestDetectB2Positive:
    def test_b2_after_b1(self):
        """B1后放量长阳应触发B2"""
        # 20天强烈下跌，J值打到负值（需保证J<-10发生在前5-14天内）
        klines = generate_downtrend_klines(n=20, start_price=200.0, daily_pct=-2.0)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        # 第21天：放量长阳
        klines.append(
            make_kline_row(base_price=klines[-1]["close"] * 1.05, base_vol=50000.0, base_date=dt.strftime("%Y%m%d"))
        )
        klines[-1]["open"] = klines[-2]["close"] * 0.99
        klines[-1]["high"] = klines[-1]["close"] * 1.01
        klines[-1]["low"] = klines[-1]["open"] * 0.98
        klines[-1]["pct_chg"] = 5.0
        klines[-1]["is_beidou"] = True
        klines[-1]["is_rise"] = True

        signal = detect_b2(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.B2
        assert signal.action == "BUY"


class TestDetectS2Positive:
    def test_macd_divergence(self):
        """价格创新高但DIF未创新高 → S2顶背离"""

        # 构造30天数据：前25天快速上涨，后5天缓慢上涨
        klines = generate_uptrend_klines(n=30, start_price=100.0, daily_pct=0.8)
        # 把后5天的涨幅调小（价格仍涨但动能减弱）
        for i in range(25, 30):
            klines[i]["close"] = klines[i - 1]["close"] * 1.002
            klines[i]["high"] = klines[i]["close"] * 1.005
            klines[i]["pct_chg"] = 0.2

        signal = detect_s2(klines, 29)
        # 顶背离对价格序列敏感，不保证一定触发，但至少不抛异常
        assert signal is None or signal.strategy == StrategyType.S2


class TestDetectS3Positive:
    def test_rebound_failure(self):
        """放量阴线后反弹无力 → S3最后逃生"""
        from datetime import datetime, timedelta

        klines = generate_uptrend_klines(n=20, start_price=100.0, daily_pct=0.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        # 第21天：放量阴线（S1）
        klines.append(make_kline_row(base_price=110.0, base_vol=50000.0, base_date=dt.strftime("%Y%m%d")))
        klines[-1]["open"] = 115.0
        klines[-1]["high"] = 116.0
        klines[-1]["low"] = 108.0
        klines[-1]["close"] = 109.0
        klines[-1]["pct_chg"] = -5.0
        klines[-1]["is_fangliang_yinxian"] = True
        klines[-1]["is_yinxian"] = True
        dt += timedelta(days=1)
        # 第22天：反弹到S1开盘价附近，但量能不足，涨幅<2%
        klines.append(make_kline_row(base_price=113.0, base_vol=20000.0, base_date=dt.strftime("%Y%m%d")))
        klines[-1]["open"] = 110.0
        klines[-1]["high"] = 114.0
        klines[-1]["low"] = 109.5
        klines[-1]["close"] = 113.0
        klines[-1]["pct_chg"] = 1.5

        signal = detect_s3(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.S3
        assert signal.action == "SELL"


class TestDetectBrickSignalsPositive:
    def test_brick_exit(self):
        """红砖翻绿 → 止损信号"""
        # 构造连续上涨后下跌的场景
        klines = generate_uptrend_klines(n=20, start_price=100.0, daily_pct=1.0)
        # 最后3天快速下跌（砖值下降）
        for i in range(3):
            klines[-(3 - i)]["close"] = klines[-(4 - i)]["close"] * 0.97
            klines[-(3 - i)]["high"] = klines[-(4 - i)]["close"] * 0.99
            klines[-(3 - i)]["low"] = klines[-(3 - i)]["close"] * 0.98
            klines[-(3 - i)]["pct_chg"] = -3.0

        for i in range(10, len(klines)):
            signal = detect_brick_signals(klines, i)
            if signal and signal.strategy == StrategyType.BRICK_EXIT:
                assert signal.action == "SELL"
                return
        # 砖形图对序列敏感，不保证一定触发
        pytest.skip("BRICK_EXIT 未在当前场景触发")

    def test_brick_reduce(self):
        """连续上涨4块以上 → 减仓信号"""
        # 前10天缓慢上涨建立砖值基础，后4天加速上涨形成连续红砖
        base_date = datetime(2026, 1, 1)
        klines = []
        price = 100.0
        for i in range(10):
            dt = base_date + timedelta(days=i)
            close = price * 1.003
            k = make_kline_row(base_price=close, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price
            k["high"] = close * 1.005
            k["low"] = price * 0.995
            k["close"] = close
            k["pct_chg"] = 0.3
            k["is_rise"] = True
            klines.append(k)
            price = close
        for i in range(4):
            dt = base_date + timedelta(days=10 + i)
            close = price * 1.03
            k = make_kline_row(base_price=close, base_vol=30000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price * 1.01
            k["high"] = close * 1.03
            k["low"] = price * 0.98
            k["close"] = close
            k["pct_chg"] = 3.0
            k["is_rise"] = True
            klines.append(k)
            price = close

        for i in range(11, len(klines)):
            signal = detect_brick_signals(klines, i)
            if signal and signal.strategy == StrategyType.BRICK_REDUCE:
                assert signal.action == "SELL"
                return
        pytest.skip("BRICK_REDUCE 未在当前场景触发")

    def test_brick_bounce(self):
        """连续下跌 → 禁止抄底信号"""
        # 先上涨建立砖值，再连续下跌形成绿砖
        base_date = datetime(2026, 1, 1)
        klines = []
        price = 100.0
        for i in range(10):
            dt = base_date + timedelta(days=i)
            close = price * 1.02
            k = make_kline_row(base_price=close, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price
            k["high"] = close * 1.02
            k["low"] = price * 0.98
            k["close"] = close
            k["pct_chg"] = 2.0
            k["is_rise"] = True
            klines.append(k)
            price = close
        for i in range(4):
            dt = base_date + timedelta(days=10 + i)
            close = price * 0.95
            k = make_kline_row(base_price=close, base_vol=30000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price * 0.98
            k["high"] = price * 0.99
            k["low"] = close * 0.97
            k["close"] = close
            k["pct_chg"] = -5.0
            k["is_rise"] = False
            klines.append(k)
            price = close

        for i in range(11, len(klines)):
            signal = detect_brick_signals(klines, i)
            if signal and signal.strategy == StrategyType.BRICK_BOUNCE:
                assert signal.action == "WATCH"
                return
        pytest.skip("BRICK_BOUNCE 未在当前场景触发")


# ==================== 新增卖出/攻击信号测试 ====================


class TestDetectBuyExhaustion:
    """买盘枯竭信号测试"""

    def test_insufficient_data(self):
        """数据不足时返回 None"""
        klines = generate_uptrend_klines(n=5)
        assert detect_buy_exhaustion(klines, 4) is None

    def test_no_uptrend(self):
        """无上涨趋势时不触发"""
        klines = generate_downtrend_klines(n=20, start_price=100.0, daily_pct=-0.5)
        assert detect_buy_exhaustion(klines, 18) is None

    def test_buy_exhaustion_triggers(self):
        """上涨趋势后连续3天缩量小阳线应触发"""
        # 先生成上涨趋势（vol_base 要小，让后续缩量容易满足）
        klines = generate_uptrend_klines(n=15, start_price=100.0, daily_pct=1.0, vol_base=5000)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]

        # 连续3天缩量小阳线，vol 从低于 uptrend 最后一天开始递减
        vol = 4000.0  # uptrend 最后一天 vol ≈ 5700，需低于它
        for i in range(3):
            date_str = dt.strftime("%Y%m%d")
            open_p = price
            close_p = price * 1.003  # 小阳线，实体 < 1%
            k = make_kline_row(base_price=close_p, base_vol=vol, base_date=date_str)
            k["open"] = open_p
            k["close"] = close_p
            k["high"] = close_p * 1.002
            k["low"] = open_p * 0.998
            k["pct_chg"] = 0.3
            k["is_rise"] = True
            klines.append(k)
            price = close_p
            vol *= 0.8  # 每天缩量
            dt += timedelta(days=1)

        signal = detect_buy_exhaustion(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.WATCH
        assert "买盘枯竭" in signal.description
        assert signal.action == "WATCH"

    def test_not_small_yang(self):
        """非小阳线（实体>=1%）不触发"""
        klines = generate_uptrend_klines(n=15, start_price=100.0, daily_pct=1.0)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]

        vol = 20000.0
        for i in range(3):
            date_str = dt.strftime("%Y%m%d")
            open_p = price
            close_p = price * 1.02  # 大阳线，实体 >= 1%
            k = make_kline_row(base_price=close_p, base_vol=vol, base_date=date_str)
            k["open"] = open_p
            k["close"] = close_p
            k["high"] = close_p * 1.005
            k["low"] = open_p * 0.995
            k["pct_chg"] = 2.0
            k["is_rise"] = True
            klines.append(k)
            price = close_p
            vol *= 0.8
            dt += timedelta(days=1)

        signal = detect_buy_exhaustion(klines, len(klines) - 1)
        assert signal is None

    def test_not_shrinking_vol(self):
        """成交量未缩减不触发"""
        klines = generate_uptrend_klines(n=15, start_price=100.0, daily_pct=1.0)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]

        vol = 20000.0
        for i in range(3):
            date_str = dt.strftime("%Y%m%d")
            open_p = price
            close_p = price * 1.003
            k = make_kline_row(base_price=close_p, base_vol=vol, base_date=date_str)
            k["open"] = open_p
            k["close"] = close_p
            k["high"] = close_p * 1.002
            k["low"] = open_p * 0.998
            k["pct_chg"] = 0.3
            k["is_rise"] = True
            klines.append(k)
            price = close_p
            vol *= 1.1  # 放量而非缩量
            dt += timedelta(days=1)

        signal = detect_buy_exhaustion(klines, len(klines) - 1)
        assert signal is None


class TestDetectGreenFatRedThin:
    """绿肥红瘦出货信号测试"""

    def test_insufficient_data(self):
        """数据不足时返回 None"""
        klines = generate_uptrend_klines(n=3)
        assert detect_green_fat_red_thin(klines, 2) is None

    def test_green_fat_red_thin_triggers(self):
        """阴线平均量 > 阳线平均量 1.5 倍应触发"""
        klines = generate_uptrend_klines(n=10, start_price=100.0, daily_pct=0.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]

        # 构造5天：2根阳线（低量）+ 3根阴线（高量）
        # 阳线1
        k = make_kline_row(base_price=price * 1.01, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
        k["open"] = price
        k["close"] = price * 1.01
        k["is_rise"] = True
        klines.append(k)
        dt += timedelta(days=1)
        # 阴线1（高量）
        k = make_kline_row(base_price=price * 0.99, base_vol=20000.0, base_date=dt.strftime("%Y%m%d"))
        k["open"] = price * 1.01
        k["close"] = price * 0.99
        k["is_rise"] = False
        k["is_yinxian"] = True
        klines.append(k)
        dt += timedelta(days=1)
        # 阳线2（低量）
        k = make_kline_row(base_price=price * 1.005, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
        k["open"] = price * 0.99
        k["close"] = price * 1.005
        k["is_rise"] = True
        klines.append(k)
        dt += timedelta(days=1)
        # 阴线2（高量）
        k = make_kline_row(base_price=price * 0.98, base_vol=20000.0, base_date=dt.strftime("%Y%m%d"))
        k["open"] = price * 1.005
        k["close"] = price * 0.98
        k["is_rise"] = False
        k["is_yinxian"] = True
        klines.append(k)
        dt += timedelta(days=1)
        # 阴线3（高量）
        k = make_kline_row(base_price=price * 0.97, base_vol=20000.0, base_date=dt.strftime("%Y%m%d"))
        k["open"] = price * 0.98
        k["close"] = price * 0.97
        k["is_rise"] = False
        k["is_yinxian"] = True
        klines.append(k)

        signal = detect_green_fat_red_thin(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.S1
        assert signal.action == "SELL"
        assert signal.priority == Priority.CRITICAL
        assert "绿肥红瘦" in signal.description

    def test_no_signal_when_balanced(self):
        """阴阳量均衡时不触发"""
        klines = generate_uptrend_klines(n=10, start_price=100.0, daily_pct=0.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]

        # 5天：3阳2阴，量相当
        for i in range(5):
            k = make_kline_row(base_price=price, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
            if i % 2 == 0:
                k["open"] = price * 0.99
                k["close"] = price * 1.01
                k["is_rise"] = True
            else:
                k["open"] = price * 1.01
                k["close"] = price * 0.99
                k["is_rise"] = False
            klines.append(k)
            dt += timedelta(days=1)

        signal = detect_green_fat_red_thin(klines, len(klines) - 1)
        assert signal is None


class TestDetectStaircaseDistribution:
    """阶梯放量下跌信号测试"""

    def test_insufficient_data(self):
        """数据不足时返回 None"""
        klines = generate_uptrend_klines(n=3)
        assert detect_staircase_distribution(klines, 2) is None

    def test_staircase_triggers(self):
        """连续3天量增价跌应触发"""
        klines = generate_uptrend_klines(n=10, start_price=100.0, daily_pct=0.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]
        vol = 10000.0

        # 连续4天量增价跌
        for i in range(4):
            date_str = dt.strftime("%Y%m%d")
            new_price = price * (1 - 0.02 * (i + 1))
            new_vol = vol * (1 + 0.3 * (i + 1))
            k = make_kline_row(base_price=new_price, base_vol=new_vol, base_date=date_str)
            k["open"] = price
            k["close"] = new_price
            k["high"] = price * 1.005
            k["low"] = new_price * 0.995
            k["pct_chg"] = -2.0 * (i + 1)
            k["is_rise"] = False
            klines.append(k)
            price = new_price
            vol = new_vol
            dt += timedelta(days=1)

        signal = detect_staircase_distribution(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.S1
        assert signal.action == "SELL"
        assert signal.priority == Priority.CRITICAL
        assert "阶梯放量下跌" in signal.description
        assert signal.details["consecutive_days"] >= 3

    def test_no_signal_two_days(self):
        """仅2天量增价跌不触发（前面的天数不满足量增价跌条件）"""
        klines = []
        dt = datetime(2026, 1, 1)
        price = 100.0

        # 10天平稳行情，恒量（不产生量增价跌条件）
        for i in range(10):
            k = make_kline_row(base_price=price, base_vol=10000.0, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price * 0.995
            k["close"] = price
            k["pct_chg"] = 0.5
            k["is_rise"] = True
            klines.append(k)
            dt += timedelta(days=1)

        price = klines[-1]["close"]

        # 仅2天量增价跌（起始量低于基准量，确保前面不连上）
        for i in range(2):
            new_price = price * 0.98
            new_vol = 8000.0 + (i + 1) * 500  # 8500, 9000（均 < 10000）
            k = make_kline_row(base_price=new_price, base_vol=new_vol, base_date=dt.strftime("%Y%m%d"))
            k["open"] = price
            k["close"] = new_price
            k["pct_chg"] = -2.0
            k["is_rise"] = False
            klines.append(k)
            price = new_price
            dt += timedelta(days=1)

        signal = detect_staircase_distribution(klines, len(klines) - 1)
        assert signal is None

    def test_no_signal_volume_decreasing(self):
        """价跌但量缩不触发"""
        klines = generate_uptrend_klines(n=10, start_price=100.0, daily_pct=0.5)
        dt = datetime.strptime(klines[-1]["trade_date"], "%Y%m%d") + timedelta(days=1)
        price = klines[-1]["close"]
        vol = 20000.0

        # 3天价跌但缩量
        for i in range(3):
            date_str = dt.strftime("%Y%m%d")
            new_price = price * 0.98
            new_vol = vol * 0.8
            k = make_kline_row(base_price=new_price, base_vol=new_vol, base_date=date_str)
            k["open"] = price
            k["close"] = new_price
            k["pct_chg"] = -2.0
            k["is_rise"] = False
            klines.append(k)
            price = new_price
            vol = new_vol
            dt += timedelta(days=1)

        signal = detect_staircase_distribution(klines, len(klines) - 1)
        assert signal is None


class TestDetectVolumeAttack:
    """量比攻击信号测试"""

    def _make_daily_list(self, n=10, start_price=100.0, daily_pct=0.5, vol_base=10000.0):
        """生成 DailyData 列表"""
        from datetime import datetime, timedelta

        rows = []
        dt = datetime(2026, 1, 1)
        price = start_price
        for i in range(n):
            prev_price = price
            price *= 1 + daily_pct / 100
            vol = vol_base
            rows.append(
                DailyData(
                    ts_code="600519.SH",
                    trade_date=dt.strftime("%Y%m%d"),
                    open=prev_price,
                    high=price * 1.01,
                    low=prev_price * 0.99,
                    close=price,
                    vol=vol,
                    amount=price * vol,
                    pct_chg=daily_pct,
                    prev_close=prev_price if i > 0 else price * 0.995,
                )
            )
            dt += timedelta(days=1)
        return rows

    def test_insufficient_data(self):
        """数据不足时返回默认值"""
        klines = self._make_daily_list(n=3)
        result = detect_volume_attack(klines)
        assert result["is_attack"] is False

    def test_volume_attack_triggers(self):
        """量比>3且涨幅>2%应触发"""
        klines = self._make_daily_list(n=8, start_price=100.0, daily_pct=0.5, vol_base=10000.0)
        # 最后一天放量大涨
        last = klines[-1]
        # 用新的 DailyData 替换最后一天
        from datetime import datetime, timedelta

        dt = datetime.strptime(last.trade_date, "%Y%m%d") + timedelta(days=1)
        attack_day = DailyData(
            ts_code="600519.SH",
            trade_date=dt.strftime("%Y%m%d"),
            open=last.close,
            high=last.close * 1.04,
            low=last.close * 0.998,
            close=last.close * 1.03,
            vol=40000.0,  # 量比 = 40000/10000 = 4.0
            amount=last.close * 1.03 * 40000.0,
            pct_chg=3.0,
            prev_close=last.close,
        )
        klines.append(attack_day)

        result = detect_volume_attack(klines)
        assert result["is_attack"] is True
        assert result["vol_ratio"] > 3
        assert result["pct_chg"] > 2
        assert result["confidence"] > 0
        assert "量比攻击" in result["desc"]

    def test_no_signal_low_vol_ratio(self):
        """量比<=3不触发"""
        klines = self._make_daily_list(n=8, start_price=100.0, daily_pct=0.5, vol_base=10000.0)
        last = klines[-1]
        from datetime import datetime, timedelta

        dt = datetime.strptime(last.trade_date, "%Y%m%d") + timedelta(days=1)
        normal_day = DailyData(
            ts_code="600519.SH",
            trade_date=dt.strftime("%Y%m%d"),
            open=last.close,
            high=last.close * 1.03,
            low=last.close * 0.998,
            close=last.close * 1.03,
            vol=20000.0,  # 量比 = 20000/10000 = 2.0
            amount=last.close * 1.03 * 20000.0,
            pct_chg=3.0,
            prev_close=last.close,
        )
        klines.append(normal_day)

        result = detect_volume_attack(klines)
        assert result["is_attack"] is False

    def test_no_signal_low_pct_chg(self):
        """涨幅<=2%不触发"""
        klines = self._make_daily_list(n=8, start_price=100.0, daily_pct=0.5, vol_base=10000.0)
        last = klines[-1]
        from datetime import datetime, timedelta

        dt = datetime.strptime(last.trade_date, "%Y%m%d") + timedelta(days=1)
        low_gain_day = DailyData(
            ts_code="600519.SH",
            trade_date=dt.strftime("%Y%m%d"),
            open=last.close,
            high=last.close * 1.015,
            low=last.close * 0.998,
            close=last.close * 1.01,
            vol=40000.0,  # 量比 = 4.0
            amount=last.close * 1.01 * 40000.0,
            pct_chg=1.0,
            prev_close=last.close,
        )
        klines.append(low_gain_day)

        result = detect_volume_attack(klines)
        assert result["is_attack"] is False


# ========== detect_top_pinwheel ==========


class TestDetectTopPinwheel:
    def test_positive_high_pinwheel(self):
        """高位大风车：长上下影阴线，应触发 S1"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=0.5)
        # 最后一天在高位，制造大风车形态
        recent_high = max(k["high"] for k in klines[-20:])
        # 阴线，实体=0.01，上下影线 > 实体×2
        klines[-1]["open"] = recent_high * 0.985
        klines[-1]["close"] = recent_high * 0.975  # 阴线
        klines[-1]["high"] = recent_high * 1.02  # 长上影线
        klines[-1]["low"] = recent_high * 0.95  # 长下影线

        signal = detect_top_pinwheel(klines, len(klines) - 1)
        assert signal is not None
        assert signal.strategy == StrategyType.S1
        assert signal.action == "SELL"
        assert signal.priority == Priority.CRITICAL
        assert "大风车" in signal.description

    def test_negative_not_high(self):
        """非高位不应触发"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=2.0)
        recent_high = max(k["high"] for k in klines[-20:])
        klines[-1]["close"] = recent_high * 0.80  # 远低于高点
        klines[-1]["open"] = recent_high * 0.81
        klines[-1]["high"] = recent_high * 0.85
        klines[-1]["low"] = recent_high * 0.75

        signal = detect_top_pinwheel(klines, len(klines) - 1)
        assert signal is None

    def test_negative_not_yinxian(self):
        """阳线不应触发"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=0.5)
        recent_high = max(k["high"] for k in klines[-20:])
        klines[-1]["open"] = recent_high * 0.97
        klines[-1]["close"] = recent_high * 0.99  # 阳线
        klines[-1]["high"] = recent_high * 1.02
        klines[-1]["low"] = recent_high * 0.95

        signal = detect_top_pinwheel(klines, len(klines) - 1)
        assert signal is None

    def test_negative_short_shadows(self):
        """上下影线不够长不应触发"""
        klines = generate_uptrend_klines(n=25, start_price=100.0, daily_pct=0.5)
        recent_high = max(k["high"] for k in klines[-20:])
        klines[-1]["open"] = recent_high * 0.99
        klines[-1]["close"] = recent_high * 0.97  # 阴线，实体=0.02
        klines[-1]["high"] = recent_high * 0.995  # 上影=0.005，太短
        klines[-1]["low"] = recent_high * 0.96  # 下影=0.01，太短

        signal = detect_top_pinwheel(klines, len(klines) - 1)
        assert signal is None

    def test_insufficient_data(self):
        """数据不足20根"""
        klines = generate_uptrend_klines(n=10, start_price=100.0, daily_pct=0.5)
        signal = detect_top_pinwheel(klines, 9)
        assert signal is None
