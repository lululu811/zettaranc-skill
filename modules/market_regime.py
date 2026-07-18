"""
市场状态分类器 — 基于大盘指数五因子模型

通过大盘指数（如上证指数 000001.SH）的K线数据，使用五因子模型判断市场状态：
- BULL（牛市）
- BEAR（熊市）
- SIDEWAYS（震荡）

五因子模型：
  1. 均线排列 (30%) — MA20/MA60/MA120 多头/空头排列
  2. 趋势斜率 (20%) — MA20 的 20 日线性回归斜率
  3. 白线/黄线关系 (20%) — Z哥体系核心（白线 vs 大哥线）
  4. 波动率信号 (15%) — 20日收益率标准差 × 方向
  5. 量能趋势 (15%) — 20日均量/60日均量 × 价格趋势

分类阈值：综合得分 > +0.3 → BULL，< -0.3 → BEAR，其他 → SIDEWAYS
"""

from __future__ import annotations

import math
from enum import Enum

from modules.indicators.core import DailyData, calculate_ma, calculate_slope
from modules.indicators.price_patterns.base import calculate_dg_yellow, calculate_zg_white
from .constants import (
    MARKET_REGIME_WEIGHT_MA_ALIGNMENT,
    MARKET_REGIME_WEIGHT_TREND_SLOPE,
    MARKET_REGIME_WEIGHT_WHITE_YELLOW,
)


class MarketRegime(Enum):
    """市场状态枚举"""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


# 默认五因子权重
_DEFAULT_WEIGHTS = {
    "ma_alignment": MARKET_REGIME_WEIGHT_MA_ALIGNMENT,  # 均线排列
    "trend_slope": MARKET_REGIME_WEIGHT_TREND_SLOPE,  # 趋势斜率
    "white_yellow": MARKET_REGIME_WEIGHT_WHITE_YELLOW,  # 白线/黄线关系
    "volatility": 0.15,  # 波动率信号
    "volume_trend": 0.15,  # 量能趋势
}


class MarketRegimeClassifier:
    """
    市场状态分类器

    基于大盘指数K线的五因子模型，输出 BULL / BEAR / SIDEWAYS 三态分类。
    支持对最新状态分类、对历史某日分类、以及批量预计算。

    Args:
        weights: 五因子权重字典，键名见 _DEFAULT_WEIGHTS。
                 传 None 使用默认权重。
        bull_threshold: 综合得分超过此值判定为 BULL，默认 +0.3
        bear_threshold: 综合得分低于此值判定为 BEAR，默认 -0.3
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        bull_threshold: float = 0.3,
        bear_threshold: float = -0.3,
    ):
        self.weights = weights if weights is not None else dict(_DEFAULT_WEIGHTS)
        self.bull_threshold = bull_threshold
        self.bear_threshold = bear_threshold

    # ──────────────────── 公开接口 ────────────────────

    def classify(self, klines: list[DailyData]) -> MarketRegime:
        """
        对最新状态进行分类

        Args:
            klines: 大盘指数K线数据列表，按日期升序排列（最新在最后）

        Returns:
            MarketRegime 枚举值
        """
        return self.classify_date(klines, len(klines) - 1)

    def classify_date(self, klines: list[DailyData], date_idx: int) -> MarketRegime:
        """
        对历史某日进行分类

        Args:
            klines: 大盘指数K线数据列表，按日期升序排列
            date_idx: 要分类的日期在列表中的索引位置

        Returns:
            MarketRegime 枚举值
        """
        score = self._compute_score(klines, date_idx)
        if score > self.bull_threshold:
            return MarketRegime.BULL
        elif score < self.bear_threshold:
            return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS

    def precompute_all(self, klines: list[DailyData], start_idx: int = 120) -> dict[int, MarketRegime]:
        """
        预计算所有日期的市场状态（用于历史回测）

        Args:
            klines: 大盘指数K线数据列表，按日期升序排列
            start_idx: 起始索引（需要足够历史数据，默认 120）

        Returns:
            {日期索引: MarketRegime} 字典
        """
        result: dict[int, MarketRegime] = {}
        for i in range(start_idx, len(klines)):
            result[i] = self.classify_date(klines, i)
        return result

    def get_score_detail(self, klines: list[DailyData]) -> dict[str, float]:
        """
        获取各因子得分明细（调试用）

        Args:
            klines: 大盘指数K线数据列表

        Returns:
            各因子原始得分与加权得分的字典
        """
        idx = len(klines) - 1
        sub = klines[: idx + 1]
        return {
            "ma_alignment_raw": self._score_ma_alignment(sub),
            "trend_slope_raw": self._score_trend_slope(sub),
            "white_yellow_raw": self._score_white_yellow(sub),
            "volatility_raw": self._score_volatility(sub),
            "volume_trend_raw": self._score_volume_trend(sub),
            "composite": self._compute_score(klines, idx),
        }

    # ──────────────────── 综合得分 ────────────────────

    def _compute_score(self, klines: list[DailyData], date_idx: int) -> float:
        """计算综合得分（-1 ~ +1）"""
        sub = klines[: date_idx + 1]
        return (
            self.weights.get("ma_alignment", 0) * self._score_ma_alignment(sub)
            + self.weights.get("trend_slope", 0) * self._score_trend_slope(sub)
            + self.weights.get("white_yellow", 0) * self._score_white_yellow(sub)
            + self.weights.get("volatility", 0) * self._score_volatility(sub)
            + self.weights.get("volume_trend", 0) * self._score_volume_trend(sub)
        )

    # ──────────────────── 因子1: 均线排列 ────────────────────

    def _score_ma_alignment(self, klines: list[DailyData]) -> float:
        """
        均线排列因子

        MA20 > MA60 > MA120 → 多头排列 → +1
        MA20 < MA60 < MA120 → 空头排列 → -1
        其他情况 → 按偏离程度映射到 (-1, +1)

        Returns:
            -1 ~ +1 的得分
        """
        closes = [k.close for k in klines]
        ma20 = calculate_ma(closes, 20)
        ma60 = calculate_ma(closes, 60)
        ma120 = calculate_ma(closes, 120)

        if ma20 == 0 or ma60 == 0 or ma120 == 0:
            return 0.0

        # 完全多头排列
        if ma20 > ma60 > ma120:
            return 1.0
        # 完全空头排列
        if ma20 < ma60 < ma120:
            return -1.0

        # 部分排列：根据 MA20 相对 MA60/MA120 的位置打分
        # 综合信号：短期均线偏离长期均线的程度
        spread_20_120 = (ma20 - ma120) / ma120  # 标准化
        # 典型A股指数偏离 ±5% 已算显著
        score = max(-1.0, min(1.0, spread_20_120 * 20))
        return score

    # ──────────────────── 因子2: 趋势斜率 ────────────────────

    def _score_trend_slope(self, klines: list[DailyData]) -> float:
        """
        趋势斜率因子

        计算 MA20 序列的 20 日线性回归斜率，归一化后映射到 (-1, +1)

        Returns:
            -1 ~ +1 的得分
        """
        closes = [k.close for k in klines]
        if len(closes) < 40:
            return 0.0

        # 计算 MA20 序列（最近 40 个点）
        ma20_series = []
        for i in range(len(closes) - 39, len(closes) + 1):
            ma_val = calculate_ma(closes[:i], 20)
            if ma_val > 0:
                ma20_series.append(ma_val)

        if len(ma20_series) < 20:
            return 0.0

        slope = calculate_slope(ma20_series, 20)

        # 归一化：斜率 / 当前价格 × 100（百分比变化率）
        current_ma20 = ma20_series[-1]
        if current_ma20 == 0:
            return 0.0
        normalized_slope = slope / current_ma20 * 100

        # A股指数日均波动约 0.5-1.5%，斜率 ±0.1%/bar 已算强趋势
        return max(-1.0, min(1.0, normalized_slope * 10))

    # ──────────────────── 因子3: 白线/黄线关系 ────────────────────

    def _score_white_yellow(self, klines: list[DailyData]) -> float:
        """
        白线/黄线关系因子（Z哥体系核心）

        白线（EMA双平滑短期动能）> 大哥线（四均线平均长期生命线）→ 多头
        白线 < 大哥线 → 空头

        Returns:
            -1 ~ +1 的得分
        """
        white = calculate_zg_white(klines)
        yellow = calculate_dg_yellow(klines)

        if white == 0 or yellow == 0:
            return 0.0

        # 白线相对大哥线的偏离率
        deviation = (white - yellow) / yellow

        # 典型偏离 ±3% 已算显著信号
        return max(-1.0, min(1.0, deviation * 30))

    # ──────────────────── 因子4: 波动率信号 ────────────────────

    def _score_volatility(self, klines: list[DailyData]) -> float:
        """
        波动率信号因子

        20日收益率标准差 × 方向（价格趋势方向）
        高波动+上涨 → 正分（牛市特征：放量上攻）
        高波动+下跌 → 负分（恐慌性抛售）
        低波动 → 接近0（方向不明）

        Returns:
            -1 ~ +1 的得分
        """
        if len(klines) < 21:
            return 0.0

        # 计算日收益率（百分比）
        returns = []
        for i in range(1, min(21, len(klines))):
            if klines[-i - 1].close != 0:
                r = (klines[-i].close - klines[-i - 1].close) / klines[-i - 1].close
                returns.append(r)

        if len(returns) < 10:
            return 0.0

        # 标准差（波动率）
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r)

        # 方向：用收益率均值判断
        direction = 1.0 if mean_r >= 0 else -1.0

        # A股指数日波动率通常在 0.5%-2% 之间
        # 将 std_r 映射到 0~1（0.005→0, 0.02→1）
        vol_score = max(0.0, min(1.0, (std_r - 0.005) / 0.015))

        return direction * vol_score

    # ──────────────────── 因子5: 量能趋势 ────────────────────

    def _score_volume_trend(self, klines: list[DailyData]) -> float:
        """
        量能趋势因子

        20日均量 / 60日均量（量能比率）× 价格趋势方向
        放量上涨 → 正分（健康上涨）
        放量下跌 → 负分（恐慌抛售）
        缩量 → 信号减弱

        Returns:
            -1 ~ +1 的得分
        """
        if len(klines) < 60:
            return 0.0

        volumes = [k.vol for k in klines]
        closes = [k.close for k in klines]

        # 20日均量 / 60日均量
        vol_20 = sum(volumes[-20:]) / 20
        vol_60 = sum(volumes[-60:]) / 60

        if vol_60 == 0:
            return 0.0

        vol_ratio = vol_20 / vol_60

        # 价格趋势方向：用 MA20 斜率方向判断
        ma_recent = calculate_ma(closes, 5)
        ma_old = calculate_ma(closes[: len(closes) - 15], 5) if len(closes) > 15 else 0

        if ma_old == 0:
            direction = 0.0
        else:
            direction = 1.0 if ma_recent > ma_old else -1.0

        # 量能比率映射：
        # 0.7 以下缩量 → 信号弱（×0.5）
        # 0.7~1.3 正常 → 信号正常
        # 1.3 以上放量 → 信号强
        if vol_ratio < 0.7:
            vol_weight = 0.3  # 缩量，信号弱
        elif vol_ratio > 1.3:
            vol_weight = 1.0  # 放量，信号强
        else:
            vol_weight = 0.6 + (vol_ratio - 0.7) / 0.6 * 0.4  # 线性插值

        return direction * vol_weight


# ──────────────────── 测试入口 ────────────────────

if __name__ == "__main__":
    """简单的测试入口：生成模拟数据验证分类器行为"""
    from datetime import datetime, timedelta

    def _make_klines(
        n: int,
        base_price: float = 3000.0,
        trend: float = 0.0,
        volatility: float = 0.01,
        base_vol: float = 1e8,
    ) -> list[DailyData]:
        """生成模拟K线数据"""
        import random

        random.seed(42)
        klines = []
        price = base_price
        base_date = datetime(2024, 1, 1)
        for i in range(n):
            change = trend + random.gauss(0, volatility)
            close = price * (1 + change)
            high = close * (1 + abs(random.gauss(0, 0.005)))
            low = close * (1 - abs(random.gauss(0, 0.005)))
            open_p = price * (1 + random.gauss(0, volatility * 0.5))
            vol = base_vol * (1 + random.gauss(0, 0.2))
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

    print("=" * 60)
    print("市场状态分类器 — 模拟测试")
    print("=" * 60)

    classifier = MarketRegimeClassifier()

    # 场景1: 上涨趋势（趋势=+0.003/日）
    bull_klines = _make_klines(200, trend=0.003, volatility=0.008)
    bull_result = classifier.classify(bull_klines)
    detail = classifier.get_score_detail(bull_klines)
    print("\n【牛市场景】trend=+0.3%/日")
    print(f"  分类结果: {bull_result.value}")
    print(f"  综合得分: {detail['composite']:.4f}")
    for k, v in detail.items():
        if k != "composite":
            print(f"  {k}: {v:.4f}")

    # 场景2: 下跌趋势（趋势=-0.003/日）
    bear_klines = _make_klines(200, trend=-0.003, volatility=0.008)
    bear_result = classifier.classify(bear_klines)
    detail = classifier.get_score_detail(bear_klines)
    print("\n【熊市场景】trend=-0.3%/日")
    print(f"  分类结果: {bear_result.value}")
    print(f"  综合得分: {detail['composite']:.4f}")
    for k, v in detail.items():
        if k != "composite":
            print(f"  {k}: {v:.4f}")

    # 场景3: 横盘震荡（趋势=0, 高波动）
    side_klines = _make_klines(200, trend=0.0, volatility=0.015)
    side_result = classifier.classify(side_klines)
    detail = classifier.get_score_detail(side_klines)
    print("\n【震荡场景】trend=0, vol=1.5%")
    print(f"  分类结果: {side_result.value}")
    print(f"  综合得分: {detail['composite']:.4f}")
    for k, v in detail.items():
        if k != "composite":
            print(f"  {k}: {v:.4f}")

    # 场景4: 历史回测（precompute_all）
    print("\n【历史回测】200日K线，从第120日开始分类")
    regime_history = classifier.precompute_all(bull_klines, start_idx=120)
    regime_counts: dict[str, int] = {}
    for regime in regime_history.values():
        regime_counts[regime.value] = regime_counts.get(regime.value, 0) + 1
    print(f"  牛市场景统计: {regime_counts}")

    regime_history_bear = classifier.precompute_all(bear_klines, start_idx=120)
    regime_counts_bear: dict[str, int] = {}
    for regime in regime_history_bear.values():
        regime_counts_bear[regime.value] = regime_counts_bear.get(regime.value, 0) + 1
    print(f"  熊市场景统计: {regime_counts_bear}")

    print("\n" + "=" * 60)
    print("测试完成")
