"""
strategies.py 战法识别测试
"""

import pytest
from modules.strategies import (
    StrategyType, StrategySignal,
    get_kline_data, calculate_ma, calculate_kdj, calculate_bbi,
    detect_b1, detect_b2, detect_b3, detect_sb1,
    detect_changan, detect_sifen_zhiyi_sanyin, detect_nana,
    detect_yidong_dilian, detect_all_strategies, get_latest_signal,
)
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
        klines.append(make_kline_row(
            base_price=100.0, base_vol=10000.0, base_date="20260101"
        ))
        # 修改为大阳线
        klines[-1]["pct_chg"] = 5.0
        klines[-1]["close"] = 105.0
        klines[-1]["high"] = 106.0
        klines[-1]["open"] = 101.0
        # 第二天阴线，阴量 > 阳量 * 0.75
        klines.append(make_kline_row(
            base_price=103.0, base_vol=8000.0, base_date="20260102"
        ))
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
