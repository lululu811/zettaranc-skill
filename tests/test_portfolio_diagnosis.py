"""
portfolio_diagnosis.py 持股诊断测试
"""

import pytest
from modules.portfolio_diagnosis import (
    diagnose_stock, DiagnosisReport,
    _judge_price_position, _judge_trend,
    _make_recommendation, _daily_to_dict,
    format_report,
)
from modules.indicators import IndicatorResult, DailyData


class TestDailyToDict:
    def test_basic(self):
        klines = [
            DailyData("600519.SH", "20260101", 100, 102, 99, 101, 10000, 1010000, 1.0),
            DailyData("600519.SH", "20260102", 101, 103, 100, 102, 20000, 2040000, 1.0),
        ]
        result = _daily_to_dict(klines)
        assert len(result) == 2
        assert result[1]["is_beidou"] is True  # 20000 >= 10000 * 2
        assert result[1]["is_rise"] is True


class TestJudgePricePosition:
    def test_above_bbi(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101",
                              bbi=100, zg_white=105, dg_yellow=95)
        pos = _judge_price_position(ind, price=110)
        assert "BBI之上" in pos
        assert "白线之上" in pos
        assert "黄线之上" in pos

    def test_below_bbi(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101",
                              bbi=100, zg_white=105, dg_yellow=95)
        pos = _judge_price_position(ind, price=90)
        assert "BBI之下" in pos


class TestJudgeTrend:
    def test_dead_cross(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101",
                              is_dead_cross=True)
        assert "死叉" in _judge_trend(ind)

    def test_macd_veto(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101",
                              macd_veto=True, is_dif_positive=True)
        assert "一票否决" in _judge_trend(ind)


class TestMakeRecommendation:
    def test_s1_critical(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101")
        exit_sigs = [{"strategy": "S1", "date": "20260101", "description": "test"}]
        rec, risk = _make_recommendation(ind, 5, exit_sigs, [], {})
        assert risk == "CRITICAL"
        assert "S1" in rec

    def test_dead_cross_high(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101", is_dead_cross=True)
        rec, risk = _make_recommendation(ind, 3, [], [], {})
        assert risk == "HIGH"
        assert "死叉" in rec

    def test_good_hold(self):
        ind = IndicatorResult(ts_code="600519.SH", trade_date="20260101")
        rec, risk = _make_recommendation(ind, 5, [], [], {})
        assert risk == "LOW"
        assert "利润" in rec


class TestFormatReport:
    def test_output(self):
        report = DiagnosisReport(
            ts_code="600519.SH",
            name="贵州茅台",
            price=1500.0,
            sell_score=4,
            sell_score_desc="强势",
            kirin_phase="拉升",
            kirin_confidence=0.8,
            risk_level="LOW",
            recommendation="持股",
        )
        text = format_report(report)
        assert "600519.SH" in text
        assert "贵州茅台" in text
        assert "拉升" in text


class TestDiagnoseStock:
    def test_without_data(self, temp_db, db_conn):
        """无数据时应返回基本报告不抛异常"""
        from tests.conftest import write_stock_basic
        write_stock_basic(db_conn, "000001.SZ", "平安银行")
        report = diagnose_stock("000001.SZ")
        assert report.ts_code == "000001.SZ"
        assert isinstance(report, DiagnosisReport)
