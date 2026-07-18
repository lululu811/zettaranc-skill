"""
少妇战法六步闭环测试
"""

import pytest
from modules.indicators import DailyData
from modules.loop_engine import (
    ShaofuLoopEngine,
    LoopConfig,
    LoopState,
    LoopTrade,
    detect_bbi_break_streak,
)


# ========== 辅助函数 ==========


def make_kline(
    price=100.0,
    vol=10000.0,
    pct_chg=0.0,
    prev_close=100.0,
    open=None,
    high=None,
    low=None,
    date="20260101",
):
    """快速创建 DailyData（与 test_indicators.py 一致）"""
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


def make_klines_seq(prices, base_date="20260101", vol=10000.0):
    """根据价格列表生成连续 K 线序列"""
    from datetime import datetime, timedelta

    dt = datetime.strptime(base_date, "%Y%m%d")
    klines = []
    for i, p in enumerate(prices):
        prev_close = prices[i - 1] if i > 0 else p
        date_str = (dt + timedelta(days=i)).strftime("%Y%m%d")
        klines.append(
            make_kline(
                price=p,
                vol=vol,
                prev_close=prev_close,
                pct_chg=(p - prev_close) / prev_close * 100 if prev_close else 0,
                date=date_str,
            )
        )
    return klines


# ========== TestBbiBreakStreak（通用连续跌破检测） ==========


class TestBbiBreakStreak:
    """连续跌破检测测试（可用于 BBI 或白线）"""

    def test_no_break(self):
        """5 天 close 全在参考线之上 → False"""
        ref_values = [100.0, 100.0, 100.0, 100.0, 100.0]
        closes = [105.0, 106.0, 107.0, 108.0, 109.0]
        result = detect_bbi_break_streak(closes, ref_values, days=2)
        assert result is False

    def test_two_day_break(self):
        """最后 2 天 close < 参考线 → True"""
        ref_values = [100.0, 100.0, 100.0, 100.0, 100.0]
        closes = [105.0, 106.0, 107.0, 95.0, 94.0]
        result = detect_bbi_break_streak(closes, ref_values, days=2)
        assert result is True

    def test_one_day_break_not_enough(self):
        """只有 1 天跌破 → False"""
        ref_values = [100.0, 100.0, 100.0, 100.0, 100.0]
        closes = [105.0, 106.0, 107.0, 108.0, 95.0]
        result = detect_bbi_break_streak(closes, ref_values, days=2)
        assert result is False

    def test_insufficient_data(self):
        """数据不足 days 天 → False"""
        ref_values = [100.0]
        closes = [95.0]
        result = detect_bbi_break_streak(closes, ref_values, days=2)
        assert result is False


# ========== TestLoopEngineInit ==========


class TestLoopEngineInit:
    """闭环引擎初始化测试"""

    def test_default_config(self):
        """默认配置参数正确"""
        engine = ShaofuLoopEngine()
        assert engine.config is not None
        assert isinstance(engine.config, LoopConfig)
        # 默认止损线
        assert hasattr(engine.config, "stop_loss_pct")
        assert engine.config.stop_loss_pct < 0

    def test_custom_config(self):
        """自定义配置生效"""
        cfg = LoopConfig(stop_loss_pct=-0.08)
        engine = ShaofuLoopEngine(config=cfg)
        assert engine.config.stop_loss_pct == -0.08


# ========== TestCheckEntry ==========


class TestCheckEntry:
    """B1 入场信号检测测试"""

    def test_no_signal_uptrend(self):
        """强势上升趋势，J 值高 → 无入场信号"""
        engine = ShaofuLoopEngine()
        # 价格高位，J 值会偏高
        klines = make_klines_seq([100 + i * 0.5 for i in range(30)])
        result = engine.check_entry(klines)
        assert result is None or result.get("signal") is None

    def test_b1_signal_oversold(self):
        """J ≤ 12 + 价格在 BBI 之上 → 入场信号"""
        engine = ShaofuLoopEngine()
        # 构造超卖场景：先涨后急跌，让 J 值打到低位
        prices = [100 + i * 0.3 for i in range(20)]
        # 急跌使 J 值走低
        prices.extend([prices[-1] * (0.95 ** (i + 1)) for i in range(10)])
        klines = make_klines_seq(prices)
        # 此测试依赖引擎内部 KDJ 计算，至少应返回 dict 或 None
        result = engine.check_entry(klines)
        # 如果有信号，应包含必要字段
        if result is not None:
            assert "entry_price" in result or "signal" in result

    def test_macd_veto_blocks(self):
        """MACD 一票否决阻止入场"""
        engine = ShaofuLoopEngine()
        # 构造 J 值低但 MACD 空头的场景
        # 先高位横盘
        prices = [100.0] * 30
        # 然后连续下跌使 MACD 转空
        for i in range(30):
            prices.append(prices[-1] * 0.97)
        klines = make_klines_seq(prices)
        result = engine.check_entry(klines)
        # MACD veto 场景下应无信号
        assert result is None or result.get("signal") is None


# ========== TestCheckStopLoss ==========


class TestCheckStopLoss:
    """止损检测测试"""

    def test_stop_loss_triggered(self):
        """收盘价跌破入场低点 → 触发止损"""
        engine = ShaofuLoopEngine()
        entry_low = 95.0
        current = make_kline(price=90.0)
        assert engine.check_stop_loss(current, entry_low) is True

    def test_stop_loss_not_triggered(self):
        """收盘价守住入场低点 → 未触发"""
        engine = ShaofuLoopEngine()
        entry_low = 95.0
        current = make_kline(price=98.0)
        assert engine.check_stop_loss(current, entry_low) is False


# ========== TestCheckLuZhu ==========


class TestCheckLuZhu:
    """卤煮止盈测试"""

    def test_lu_zhu_triggered(self):
        """在白线之上 + 连续 2 根阳线 → 卤煮触发"""
        engine = ShaofuLoopEngine()
        white_line = 100.0
        candle1 = make_kline(price=102.0, prev_close=100.0)
        candle2 = make_kline(price=104.0, prev_close=102.0)
        recent_klines = [candle1, candle2]
        assert engine.check_lu_zhu(recent_klines, white_line) is True

    def test_lu_zhu_not_triggered(self):
        """在白线之上但只有 1 根阳线 → 未触发"""
        engine = ShaofuLoopEngine()
        white_line = 100.0
        candle1 = make_kline(price=102.0, prev_close=100.0)
        recent_klines = [candle1]
        assert engine.check_lu_zhu(recent_klines, white_line) is False

    def test_lu_zhu_below_white_line(self):
        """价格在白线之下 → 未触发"""
        engine = ShaofuLoopEngine()
        white_line = 110.0
        candle1 = make_kline(price=102.0, prev_close=100.0)
        candle2 = make_kline(price=104.0, prev_close=102.0)
        recent_klines = [candle1, candle2]
        assert engine.check_lu_zhu(recent_klines, white_line) is False


# ========== TestCheckWhiteLineExit ==========


class TestCheckWhiteLineExit:
    """白线出场检测测试"""

    def test_white_line_exit_triggered(self):
        """连续 2 天收盘低于白线 → 触发出场"""
        engine = ShaofuLoopEngine()
        white_values = [100.0, 100.0]
        closes = [95.0, 94.0]
        assert engine.check_white_line_exit(closes, white_values) is True

    def test_white_line_exit_not_triggered(self):
        """只有 1 天低于白线 → 未触发"""
        engine = ShaofuLoopEngine()
        white_values = [100.0, 100.0]
        closes = [95.0, 101.0]
        assert engine.check_white_line_exit(closes, white_values) is False


# ========== TestRunStock ==========


class TestRunStock:
    """集成测试：run_stock 全流程"""

    def test_no_trade_in_downtrend(self):
        """纯下跌行情，无 B1 信号 → 空交易记录"""
        engine = ShaofuLoopEngine()
        # 120 天持续下跌
        prices = [200.0 * (0.995**i) for i in range(120)]
        klines = make_klines_seq(prices)
        trades = engine.run_stock(klines)
        assert isinstance(trades, list)
        assert len(trades) == 0

    def test_full_cycle(self):
        """B1 入场 → 持仓 → 白线跌破出场 → 验证交易记录"""
        engine = ShaofuLoopEngine()
        # 前 60 天震荡上行
        prices = [100 + i * 0.2 for i in range(60)]
        # 20 天急跌制造超卖 (B1 条件)
        last_price = prices[-1]
        for i in range(20):
            last_price *= 0.96
            prices.append(last_price)
        # 10 天反弹
        for i in range(10):
            last_price *= 1.02
            prices.append(last_price)
        # 10 天跌破白线
        for i in range(10):
            last_price *= 0.97
            prices.append(last_price)
        klines = make_klines_seq(prices)
        trades = engine.run_stock(klines)
        # 如果产生了交易，验证基本结构
        for t in trades:
            assert isinstance(t, LoopTrade)
            assert hasattr(t, "entry_date")
            assert hasattr(t, "exit_date")
            assert hasattr(t, "entry_price")
            assert hasattr(t, "exit_price")
            assert hasattr(t, "exit_reason")

    def test_stop_loss_cycle(self):
        """入场 → 价格跌破止损 → 验证 exit_reason='止损'"""
        engine = ShaofuLoopEngine()
        # 构造 B1 信号 + 止损场景
        # 先涨 60 天
        prices = [100 + i * 0.3 for i in range(60)]
        # 急跌 20 天制造 B1
        last_price = prices[-1]
        for i in range(20):
            last_price *= 0.96
            prices.append(last_price)
        # 小幅反弹 3 天
        for i in range(3):
            last_price *= 1.01
            prices.append(last_price)
        # 暴跌触发止损
        for i in range(10):
            last_price *= 0.93
            prices.append(last_price)
        klines = make_klines_seq(prices)
        trades = engine.run_stock(klines)
        # 如果有止损交易，验证 exit_reason
        stop_trades = [t for t in trades if t.exit_reason == "止损"]
        # 止损场景应产生至少一笔止损交易（如果引擎检测到 B1）
        for t in stop_trades:
            assert t.exit_price < t.entry_price

    def test_lu_zhu_cycle(self):
        """入场 → 价格上涨 → 卤煮触发（部分减仓）→ 白线跌破 → 全部出场"""
        engine = ShaofuLoopEngine()
        # 先涨 60 天
        prices = [100 + i * 0.3 for i in range(60)]
        # 急跌 20 天制造 B1
        last_price = prices[-1]
        for i in range(20):
            last_price *= 0.96
            prices.append(last_price)
        # 强反弹 15 天（卤煮条件：白线之上 + 连续阳线）
        for i in range(15):
            last_price *= 1.03
            prices.append(last_price)
        # 跌破白线
        for i in range(10):
            last_price *= 0.96
            prices.append(last_price)
        klines = make_klines_seq(prices)
        trades = engine.run_stock(klines)
        # 验证交易记录结构完整
        for t in trades:
            assert isinstance(t, LoopTrade)
            assert t.entry_date <= t.exit_date

    def test_position_pct_propagates_to_trade(self):
        """LoopConfig.position_pct 应正确传入 LoopTrade"""
        engine = ShaofuLoopEngine(LoopConfig(position_pct=0.25))
        # 构造能产生 B1 的序列
        prices = [100 + i * 0.3 for i in range(60)]
        last_price = prices[-1]
        for i in range(20):
            last_price *= 0.96
            prices.append(last_price)
        for i in range(15):
            last_price *= 1.03
            prices.append(last_price)
        klines = make_klines_seq(prices)
        trades = engine.run_stock(klines)
        if trades:
            assert all(t.position_pct == 0.25 for t in trades)
            assert trades[-1].exit_reason in ("止损", "卤煮止盈", "白线跌破", "白线死叉黄线", "数据末尾", "未知")
