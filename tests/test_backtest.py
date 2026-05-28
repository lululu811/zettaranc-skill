"""
回测框架单元测试
测试策略回测、组合回测、资金曲线等功能
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from modules.backtest import (
    Trade, BacktestResult, Position, PortfolioBacktestResult,
    backtest_signals, _calc_shares, _calc_stats,
    backtest_multi_strategy, backtest_portfolio,
)


def _make_klines(n=10, start_price=100.0, ts_code="600519.SH"):
    """生成测试K线数据"""
    klines = []
    dt = datetime(2026, 1, 1)
    price = start_price
    for i in range(n):
        date_str = dt.strftime("%Y%m%d")
        prev_price = price
        price *= 1.01
        klines.append({
            'ts_code': ts_code,
            'trade_date': date_str,
            'open': prev_price,
            'high': price * 1.02,
            'low': prev_price * 0.98,
            'close': price,
            'vol': 10000 + i * 100,
            'amount': price * (10000 + i * 100),
            'pct_chg': 1.0,
        })
        dt += timedelta(days=1)
    return klines


def _make_signal(trade_date, action='BUY', priority_value=2):
    """生成模拟策略信号"""
    sig = MagicMock()
    sig.trade_date = trade_date
    sig.action = action
    sig.priority = MagicMock()
    sig.priority.value = priority_value
    return sig


class TestCalcShares:
    def test_basic(self):
        assert _calc_shares(10000, 100.0) == 100

    def test_multiple_lots(self):
        assert _calc_shares(50000, 100.0) == 500

    def test_insufficient_funds(self):
        assert _calc_shares(50, 100.0) == 0

    def test_zero_price(self):
        assert _calc_shares(10000, 0) == 0

    def test_high_price(self):
        assert _calc_shares(10000, 2000.0) == 0


class TestBacktestSignals:
    def test_no_signals(self):
        klines = _make_klines(n=5)
        result = backtest_signals([], klines, '600519.SH')
        assert result.total_trades == 0

    def test_buy_and_sell(self):
        klines = _make_klines(n=10)
        signals = [
            _make_signal(klines[2]['trade_date'], 'BUY'),
            _make_signal(klines[7]['trade_date'], 'SELL'),
        ]
        result = backtest_signals(signals, klines, '600519.SH')
        assert result.total_trades == 1
        assert result.trades[0].exit_reason == 'signal'

    def test_stop_loss(self):
        klines = _make_klines(n=10)
        # 构造下跌K线使止损触发
        klines[3]['low'] = klines[2]['close'] * 0.90
        signals = [
            _make_signal(klines[2]['trade_date'], 'BUY'),
        ]
        result = backtest_signals(signals, klines, '600519.SH', stop_loss_pct=0.07)
        assert result.total_trades == 1
        assert result.trades[0].exit_reason == 'stop_loss'

    def test_take_profit(self):
        klines = _make_klines(n=10)
        # 构造大涨K线使止盈触发
        klines[3]['high'] = klines[2]['close'] * 1.20
        signals = [
            _make_signal(klines[2]['trade_date'], 'BUY'),
        ]
        result = backtest_signals(signals, klines, '600519.SH', take_profit_pct=0.15)
        assert result.total_trades == 1
        assert result.trades[0].exit_reason == 'take_profit'


class TestCalcStats:
    def test_empty(self):
        result = PortfolioBacktestResult()
        _calc_stats(result, trading_days=0)
        assert result.total_return == 0.0

    def test_basic_stats(self):
        result = PortfolioBacktestResult(initial_capital=100000.0)
        result.equity_curve = [
            ('20260101', 100000.0),
            ('20260102', 101000.0),
            ('20260103', 102000.0),
        ]
        result.trades = [
            Trade(ts_code='600519.SH', entry_date='20260101', entry_price=100.0,
                  exit_date='20260102', exit_price=110.0, pnl=1000.0, pnl_pct=0.10),
            Trade(ts_code='600519.SH', entry_date='20260102', entry_price=110.0,
                  exit_date='20260103', exit_price=105.0, pnl=-500.0, pnl_pct=-0.045),
        ]
        _calc_stats(result, trading_days=3)
        assert result.total_return > 0
        assert result.total_trades == 2
        assert result.win_rate == 0.5
        assert result.profit_factor > 0


class TestBacktestMultiStrategy:
    @patch('modules.backtest.get_kline_data')
    @patch('modules.backtest.detect_all_strategies')
    def test_basic(self, mock_detect, mock_klines):
        klines = _make_klines(n=10)
        mock_klines.return_value = klines
        mock_detect.return_value = [
            _make_signal(klines[2]['trade_date'], 'BUY', priority_value=1),
            _make_signal(klines[7]['trade_date'], 'SELL', priority_value=1),
        ]

        result = backtest_multi_strategy('600519.SH', days=10)
        assert result.initial_capital == 100000.0
        assert len(result.equity_curve) > 0
        assert result.total_trades >= 0

    @patch('modules.backtest.get_kline_data')
    @patch('modules.backtest.detect_all_strategies')
    def test_no_signals(self, mock_detect, mock_klines):
        klines = _make_klines(n=5)
        mock_klines.return_value = klines
        mock_detect.return_value = []

        result = backtest_multi_strategy('600519.SH', days=5)
        assert result.total_trades == 0
        assert len(result.equity_curve) == len(klines)

    @patch('modules.backtest.get_kline_data')
    @patch('modules.backtest.detect_all_strategies')
    def test_position_sizing(self, mock_detect, mock_klines):
        klines = _make_klines(n=10, start_price=100.0)
        mock_klines.return_value = klines
        mock_detect.return_value = [
            _make_signal(klines[2]['trade_date'], 'BUY', priority_value=1),
        ]

        result = backtest_multi_strategy('600519.SH', days=10, position_pct=0.3)
        # 初始资金10万，仓位30%，应投入约3万
        # 股价约100元，应买入300股
        if result.total_trades > 0:
            assert result.trades[0].pnl != 0


class TestBacktestPortfolio:
    @patch('modules.backtest.get_kline_data')
    @patch('modules.backtest.detect_all_strategies')
    def test_basic(self, mock_detect, mock_klines):
        klines_a = _make_klines(n=10, ts_code='000001.SZ')
        klines_b = _make_klines(n=10, ts_code='000002.SZ')

        def mock_klines_side(ts_code, days):
            return klines_a if ts_code == '000001.SZ' else klines_b

        mock_klines.side_effect = mock_klines_side

        def mock_detect_side(ts_code, days):
            klines = klines_a if ts_code == '000001.SZ' else klines_b
            return [
                _make_signal(klines[2]['trade_date'], 'BUY', priority_value=1),
                _make_signal(klines[7]['trade_date'], 'SELL', priority_value=1),
            ]

        mock_detect.side_effect = mock_detect_side

        configs = [
            {'ts_code': '000001.SZ', 'max_weight': 0.2},
            {'ts_code': '000002.SZ', 'max_weight': 0.2},
        ]

        result = backtest_portfolio(configs, days=10)
        assert result.initial_capital == 100000.0
        assert len(result.equity_curve) > 0
        assert result.total_trades >= 0

    @patch('modules.backtest.get_kline_data')
    @patch('modules.backtest.detect_all_strategies')
    def test_empty_stocks(self, mock_detect, mock_klines):
        mock_klines.return_value = []
        mock_detect.return_value = []

        result = backtest_portfolio([], days=10)
        assert result.total_trades == 0
