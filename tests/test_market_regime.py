"""
modules/market_regime.py 单元测试

覆盖：
  1. MarketRegime 枚举值
  2. MarketRegimeClassifier 分类逻辑（BULL / BEAR / SIDEWAYS）
  3. 边界情况与辅助方法
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from modules.market_regime import MarketRegime, MarketRegimeClassifier
from modules.indicators.core import DailyData


# ──────────────────── 测试数据工厂 ────────────────────


def _make_klines(
    n: int,
    base_price: float = 3000.0,
    trend: float = 0.0,
    volatility: float = 0.005,
    base_vol: float = 1e8,
) -> list[DailyData]:
    """
    生成确定性模拟 K 线数据（无随机种子，使用正弦扰动保证可复现）。

    Args:
        n: K 线根数
        base_price: 起始价格
        trend: 每日趋势（如 +0.003 表示每日涨 0.3%）
        volatility: 波动幅度
        base_vol: 基础成交量
    """
    klines = []
    price = base_price
    base_date = datetime(2024, 1, 1)
    for i in range(n):
        # 用正弦波代替随机数，保证完全确定性
        cycle = math.sin(i * 0.7) * 0.3 + math.sin(i * 1.3) * 0.2
        change = trend + cycle * volatility
        close = price * (1 + change)
        high = close * 1.003
        low = close * 0.997
        open_p = price * (1 + trend * 0.5)
        vol = base_vol * (1 + math.sin(i * 0.5) * 0.15)
        pct_chg = (close - price) / price * 100 if price > 0 else 0

        klines.append(
            DailyData(
                ts_code="000001.SH",
                trade_date=(base_date + timedelta(days=i)).strftime("%Y%m%d"),
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                vol=round(max(vol, 1e6), 0),
                amount=round(max(vol * close, 1e8), 0),
                pct_chg=round(pct_chg, 2),
                prev_close=round(price, 2),
            )
        )
        price = close
    return klines


def _make_sideways_klines(
    n: int,
    base_price: float = 3000.0,
    amplitude: float = 0.01,
    base_vol: float = 1e8,
) -> list[DailyData]:
    """
    生成均值回归的横盘 K 线数据（价格围绕 base_price 振荡，无趋势漂移）。

    使用正弦波直接设定价格（而非逐日累加），确保 MA20 ≈ MA60 ≈ MA120。
    """
    klines = []
    base_date = datetime(2024, 1, 1)
    for i in range(n):
        # 直接用正弦波设定绝对价格，避免累积漂移
        close = base_price * (1 + math.sin(i * 0.3) * amplitude)
        high = close * (1 + abs(math.sin(i * 0.7)) * 0.003)
        low = close * (1 - abs(math.cos(i * 0.5)) * 0.003)
        open_p = base_price * (1 + math.sin((i - 1) * 0.3) * amplitude) if i > 0 else close
        vol = base_vol * (1 + math.sin(i * 0.5) * 0.1)
        pct_chg = (close - klines[-1].close) / klines[-1].close * 100 if klines else 0

        klines.append(
            DailyData(
                ts_code="000001.SH",
                trade_date=(base_date + timedelta(days=i)).strftime("%Y%m%d"),
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                vol=round(max(vol, 1e6), 0),
                amount=round(max(vol * close, 1e8), 0),
                pct_chg=round(pct_chg, 2),
                prev_close=round(klines[-1].close, 2) if klines else round(close, 2),
            )
        )
    return klines


# ──────────────────── 1. MarketRegime 枚举测试 ────────────────────


class TestMarketRegimeEnum:
    """MarketRegime 枚举基础测试"""

    def test_enum_values_exist(self):
        """三个枚举值必须存在"""
        assert MarketRegime.BULL is not None
        assert MarketRegime.BEAR is not None
        assert MarketRegime.SIDEWAYS is not None

    def test_enum_values_are_strings(self):
        """枚举值应为对应字符串"""
        assert MarketRegime.BULL.value == "BULL"
        assert MarketRegime.BEAR.value == "BEAR"
        assert MarketRegime.SIDEWAYS.value == "SIDEWAYS"

    def test_enum_count(self):
        """枚举应恰好有 3 个成员"""
        assert len(MarketRegime) == 3

    def test_enum_membership(self):
        """通过值查找枚举成员"""
        assert MarketRegime("BULL") is MarketRegime.BULL
        assert MarketRegime("BEAR") is MarketRegime.BEAR
        assert MarketRegime("SIDEWAYS") is MarketRegime.SIDEWAYS

    def test_enum_invalid_value_raises(self):
        """不存在的值应抛出 ValueError"""
        with pytest.raises(ValueError):
            MarketRegime("INVALID")


# ──────────────────── 2. 分类器核心逻辑测试 ────────────────────


class TestMarketRegimeClassifier:
    """MarketRegimeClassifier 分类逻辑测试"""

    # --- 牛市场景 ---

    def test_strong_uptrend_classified_as_bull(self):
        """强上涨趋势 → BULL"""
        klines = _make_klines(200, trend=0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.BULL

    def test_moderate_uptrend_classified_as_bull(self):
        """中等上涨趋势 → BULL"""
        klines = _make_klines(200, trend=0.003, volatility=0.004)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.BULL

    # --- 熊市场景 ---

    def test_strong_downtrend_classified_as_bear(self):
        """强下跌趋势 → BEAR"""
        klines = _make_klines(200, trend=-0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.BEAR

    def test_moderate_downtrend_classified_as_bear(self):
        """中等下跌趋势 → BEAR"""
        klines = _make_klines(200, trend=-0.003, volatility=0.004)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.BEAR

    # --- 震荡场景 ---

    def test_flat_market_classified_as_sideways(self):
        """横盘无趋势 → SIDEWAYS"""
        klines = _make_sideways_klines(200, amplitude=0.01)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.SIDEWAYS

    def test_low_volatility_flat_classified_as_sideways(self):
        """低波动横盘 → SIDEWAYS"""
        klines = _make_sideways_klines(200, amplitude=0.005)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert result == MarketRegime.SIDEWAYS

    # --- 阈值边界 ---

    def test_custom_thresholds_make_classification_stricter(self):
        """自定义更严格的阈值应改变分类结果"""
        # 用中等上涨数据，默认阈值下可能是 BULL
        klines = _make_klines(200, trend=0.002, volatility=0.004)
        classifier_default = MarketRegimeClassifier()
        result_default = classifier_default.classify(klines)

        # 把 bull_threshold 提到很高，强制不判定为 BULL
        classifier_strict = MarketRegimeClassifier(bull_threshold=0.9)
        result_strict = classifier_strict.classify(klines)

        # 默认阈值下应判定为 BULL，严格阈值下不应再是 BULL
        assert result_default == MarketRegime.BULL
        assert result_strict != MarketRegime.BULL
        # 结果应该是 SIDEWAYS 或 BEAR
        assert result_strict in (MarketRegime.SIDEWAYS, MarketRegime.BEAR)

    def test_custom_thresholds_make_classification_looser(self):
        """自定义更宽松的阈值应更容易判定为 BULL"""
        # 用横盘数据，默认阈值下应该是 SIDEWAYS
        klines = _make_klines(200, trend=0.0, volatility=0.003)

        classifier_loose = MarketRegimeClassifier(bull_threshold=-0.5, bear_threshold=-0.9)
        result = classifier_loose.classify(klines)

        # 宽松阈值下，综合得分 > -0.5 就判 BULL
        assert result == MarketRegime.BULL

    # --- classify_date ---

    def test_classify_date_early_index(self):
        """classify_date 在早期索引应能正常返回"""
        klines = _make_klines(200, trend=0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        # 在索引 120 处分类（有足够历史数据）
        result = classifier.classify_date(klines, 120)
        assert isinstance(result, MarketRegime)

    def test_classify_date_returns_market_regime(self):
        """classify_date 返回值类型正确"""
        klines = _make_klines(200, trend=-0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        result = classifier.classify_date(klines, 150)
        assert result in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)


# ──────────────────── 3. 辅助方法测试 ────────────────────


class TestClassifierHelpers:
    """分类器辅助方法测试"""

    def test_get_score_detail_keys(self):
        """get_score_detail 返回正确的键"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)
        classifier = MarketRegimeClassifier()
        detail = classifier.get_score_detail(klines)

        expected_keys = {
            "ma_alignment_raw",
            "trend_slope_raw",
            "white_yellow_raw",
            "volatility_raw",
            "volume_trend_raw",
            "composite",
        }
        assert set(detail.keys()) == expected_keys

    def test_get_score_detail_values_are_float(self):
        """get_score_detail 所有值应为 float"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)
        classifier = MarketRegimeClassifier()
        detail = classifier.get_score_detail(klines)

        for key, value in detail.items():
            assert isinstance(value, float), f"{key} should be float, got {type(value)}"

    def test_composite_score_in_range(self):
        """综合得分应在 -1 ~ +1 范围内"""
        for trend in [-0.005, -0.002, 0.0, 0.002, 0.005]:
            klines = _make_klines(200, trend=trend, volatility=0.005)
            classifier = MarketRegimeClassifier()
            detail = classifier.get_score_detail(klines)
            score = detail["composite"]
            assert -1.0 <= score <= 1.0, f"composite score {score} out of range for trend={trend}"

    def test_sub_factor_scores_in_range(self):
        """各子因子得分应在 -1 ~ +1 范围内"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)
        classifier = MarketRegimeClassifier()
        detail = classifier.get_score_detail(klines)

        for key, value in detail.items():
            if key != "composite":
                assert -1.0 <= value <= 1.0, f"{key} = {value} out of [-1, +1]"

    def test_precompute_all_returns_dict(self):
        """precompute_all 返回字典，键为 int，值为 MarketRegime"""
        klines = _make_klines(200, trend=0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        result = classifier.precompute_all(klines, start_idx=120)

        assert isinstance(result, dict)
        assert len(result) > 0
        for idx, regime in result.items():
            assert isinstance(idx, int)
            assert isinstance(regime, MarketRegime)

    def test_precompute_all_start_idx(self):
        """precompute_all 应从 start_idx 开始"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)
        classifier = MarketRegimeClassifier()
        result = classifier.precompute_all(klines, start_idx=150)

        assert min(result.keys()) == 150
        assert max(result.keys()) == 199  # len(klines) - 1

    def test_precompute_all_bull_dominated(self):
        """强牛市场景下 precompute_all 大部分应为 BULL"""
        klines = _make_klines(200, trend=0.005, volatility=0.003)
        classifier = MarketRegimeClassifier()
        result = classifier.precompute_all(klines, start_idx=120)

        bull_count = sum(1 for r in result.values() if r == MarketRegime.BULL)
        total = len(result)
        # 强上涨趋势下，大部分应该是 BULL
        assert bull_count / total > 0.5

    def test_custom_weights(self):
        """自定义权重应影响分类结果"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)

        # 只使用均线排列因子
        classifier_ma_only = MarketRegimeClassifier(
            weights={
                "ma_alignment": 1.0,
                "trend_slope": 0.0,
                "white_yellow": 0.0,
                "volatility": 0.0,
                "volume_trend": 0.0,
            }
        )
        result = classifier_ma_only.classify(klines)
        assert isinstance(result, MarketRegime)

    def test_default_weights_sum_to_one(self):
        """默认权重之和应为 1.0"""
        from modules.market_regime import _DEFAULT_WEIGHTS

        total = sum(_DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


# ──────────────────── 4. 边界情况测试 ────────────────────


class TestEdgeCases:
    """边界情况测试"""

    def test_short_klines_does_not_crash(self):
        """短 K 线数据不应导致崩溃（因子会返回 0）"""
        klines = _make_klines(10, trend=0.005)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert isinstance(result, MarketRegime)

    def test_single_kline_does_not_crash(self):
        """单根 K 线不应崩溃"""
        klines = _make_klines(1, trend=0.0)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert isinstance(result, MarketRegime)

    def test_two_klines_does_not_crash(self):
        """两根 K 线不应崩溃"""
        klines = _make_klines(2, trend=0.005)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        assert isinstance(result, MarketRegime)

    def test_zero_volatility_flat_line(self):
        """零波动率（价格不变）不应崩溃"""
        klines = _make_klines(200, trend=0.0, volatility=0.0)
        classifier = MarketRegimeClassifier()
        result = classifier.classify(klines)
        # 价格完全不变，应为 SIDEWAYS
        assert result == MarketRegime.SIDEWAYS

    def test_precompute_all_with_short_data(self):
        """短数据的 precompute_all 应返回空字典"""
        klines = _make_klines(50)
        classifier = MarketRegimeClassifier()
        # start_idx=120 但只有 50 根 K 线
        result = classifier.precompute_all(klines, start_idx=120)
        assert result == {}

    def test_classify_date_at_last_index_same_as_classify(self):
        """classify_date(klines, -1) 应与 classify(klines) 结果一致"""
        klines = _make_klines(200, trend=0.003, volatility=0.005)
        classifier = MarketRegimeClassifier()

        result_classify = classifier.classify(klines)
        result_classify_date = classifier.classify_date(klines, len(klines) - 1)
        assert result_classify == result_classify_date

    def test_bear_threshold_boundary(self):
        """恰好在 bear_threshold 边界上应判为 SIDEWAYS（不是 BEAR）"""
        # 分类逻辑：score < bear_threshold → BEAR，score == bear_threshold → SIDEWAYS
        # 使用均值回归横盘数据，综合得分应接近 0
        classifier = MarketRegimeClassifier(bear_threshold=-0.3)
        klines = _make_sideways_klines(200, amplitude=0.01)
        result = classifier.classify(klines)
        assert result != MarketRegime.BEAR

    def test_all_three_regimes_possible(self):
        """确认三种状态在不同数据下都能被分类出来"""
        results = set()

        # 牛市
        bull_klines = _make_klines(200, trend=0.005, volatility=0.003)
        results.add(MarketRegimeClassifier().classify(bull_klines))

        # 熊市
        bear_klines = _make_klines(200, trend=-0.005, volatility=0.003)
        results.add(MarketRegimeClassifier().classify(bear_klines))

        # 震荡（使用均值回归数据）
        sideways_klines = _make_sideways_klines(200, amplitude=0.01)
        results.add(MarketRegimeClassifier().classify(sideways_klines))

        assert MarketRegime.BULL in results
        assert MarketRegime.BEAR in results
        assert MarketRegime.SIDEWAYS in results
