"""v1.0 验收股票池加载器测试"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

# 让 tests 能导入 scripts/optimize_for_v10_verify
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from modules.screener.models import StockScore
from modules.verify.pool import (
    CRITERIA_GROUPS,
    DEFAULT_VERIFY_POOL_GROUPS,
    _merge_group_results,
    _resolve_group_definitions,
    load_v10_stock_pool,
    load_v10_stock_pool_multi_criteria,
)
import optimize_for_v10_verify as opt_script


def _insert_stock_basic(db_conn, rows: list[dict]) -> None:
    """向 stock_basic 写入测试股票"""
    cursor = db_conn.cursor()
    for r in rows:
        cursor.execute(
            """
            INSERT OR REPLACE INTO stock_basic
            (ts_code, name, market, list_date)
            VALUES (?, ?, ?, ?)
            """,
            (r["ts_code"], r["name"], r["market"], r["list_date"]),
        )
    db_conn.commit()


def _insert_klines(db_conn, rows: list[dict]) -> None:
    """向 daily_kline 写入测试 K 线"""
    cursor = db_conn.cursor()
    for r in rows:
        cursor.execute(
            """
            INSERT OR REPLACE INTO daily_kline
            (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["ts_code"],
                r["trade_date"],
                r["open"],
                r["high"],
                r["low"],
                r["close"],
                r["vol"],
                r["amount"],
                r["pct_chg"],
            ),
        )
    db_conn.commit()


def _make_kline(ts_code: str, date: str, close: float, vol: float = 10000.0) -> dict:
    """快速构造一根 K 线字典"""
    return {
        "ts_code": ts_code,
        "trade_date": date,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "vol": vol,
        "amount": close * vol,
        "pct_chg": 0.0,
    }


class TestLoadV10StockPool:
    """load_v10_stock_pool 核心过滤逻辑测试"""

    def test_empty_db_returns_fallback(self, temp_db):
        """空数据库时回退到 stock_basic 前 N 只"""
        result = load_v10_stock_pool(limit=10)
        assert isinstance(result, list)

    def test_excludes_st_and_new_stocks(self, db_conn):
        """排除 ST 和上市时间不足的股票"""
        stocks = [
            {"ts_code": "000001.SZ", "name": "平安银行", "market": "主板", "list_date": "19910403"},
            {"ts_code": "000002.SZ", "name": "ST 万科", "market": "主板", "list_date": "19910129"},
            {"ts_code": "000003.SZ", "name": "新股", "market": "主板", "list_date": "20260101"},
        ]
        _insert_stock_basic(db_conn, stocks)

        # 构造 K 线：让 000001 满足流动性和涨幅
        klines = [
            _make_kline("000001.SZ", "20260101", 10.0),
            _make_kline("000001.SZ", "20260102", 11.0),
        ]
        _insert_klines(db_conn, klines)

        result = load_v10_stock_pool(
            limit=10,
            min_avg_amount=0,
            min_list_days=365,
            lookback_days=60,
            top_return_pct=None,
        )
        assert "000001.SZ" in result
        assert "000002.SZ" not in result
        assert "000003.SZ" not in result

    def test_liquidity_filter(self, db_conn):
        """日均成交额过滤生效"""
        stocks = [
            {"ts_code": "000001.SZ", "name": "高流动", "market": "主板", "list_date": "19910403"},
            {"ts_code": "000002.SZ", "name": "低流动", "market": "主板", "list_date": "19910129"},
        ]
        _insert_stock_basic(db_conn, stocks)

        klines = [
            _make_kline("000001.SZ", "20260101", 100.0, vol=1_000_000),  # amount=1e8
            _make_kline("000001.SZ", "20260102", 100.0, vol=1_000_000),
            _make_kline("000002.SZ", "20260101", 1.0, vol=100),  # amount=100
            _make_kline("000002.SZ", "20260102", 1.0, vol=100),
        ]
        _insert_klines(db_conn, klines)

        result = load_v10_stock_pool(
            limit=10,
            min_avg_amount=50_000_000,
            min_list_days=1,
            lookback_days=60,
            top_return_pct=None,
        )
        assert "000001.SZ" in result
        assert "000002.SZ" not in result

    def test_top_return_filter(self, db_conn):
        """取涨幅前 top_return_pct 的股票"""
        stocks = [
            {"ts_code": "000001.SZ", "name": "强势股", "market": "主板", "list_date": "19910403"},
            {"ts_code": "000002.SZ", "name": "弱势股", "market": "主板", "list_date": "19910129"},
            {"ts_code": "000003.SZ", "name": "中势股", "market": "主板", "list_date": "19910129"},
        ]
        _insert_stock_basic(db_conn, stocks)

        klines = [
            _make_kline("000001.SZ", "20260101", 10.0, vol=1_000_000),
            _make_kline("000001.SZ", "20260102", 15.0, vol=1_000_000),  # +50%
            _make_kline("000002.SZ", "20260101", 10.0, vol=1_000_000),
            _make_kline("000002.SZ", "20260102", 9.0, vol=1_000_000),  # -10%
            _make_kline("000003.SZ", "20260101", 10.0, vol=1_000_000),
            _make_kline("000003.SZ", "20260102", 11.0, vol=1_000_000),  # +10%
        ]
        _insert_klines(db_conn, klines)

        result = load_v10_stock_pool(
            limit=10,
            min_avg_amount=0,
            min_list_days=1,
            lookback_days=60,
            top_return_pct=0.34,  # 前 1/3，即 1 只
        )
        # 只有涨幅最高的 000001 应被保留
        assert result == ["000001.SZ"]

    def test_limit_caps_result(self, db_conn):
        """limit 参数最终截断结果"""
        stocks = [
            {"ts_code": f"{i:06d}.SZ", "name": f"股票{i}", "market": "主板", "list_date": "19910101"}
            for i in range(1, 11)
        ]
        _insert_stock_basic(db_conn, stocks)

        klines = []
        for i, s in enumerate(stocks, start=1):
            klines.append(_make_kline(s["ts_code"], "20260101", 10.0, vol=1_000_000))
            klines.append(_make_kline(s["ts_code"], "20260102", 10.0 + i * 0.1, vol=1_000_000))
        _insert_klines(db_conn, klines)

        result = load_v10_stock_pool(
            limit=3,
            min_avg_amount=0,
            min_list_days=1,
            lookback_days=60,
            top_return_pct=1.0,
        )
        assert len(result) == 3
        # 涨幅最高的三只：010.SZ, 009.SZ, 008.SZ
        assert result[0] == "000010.SZ"
        assert result[1] == "000009.SZ"
        assert result[2] == "000008.SZ"


# ---------- v3.7.6 多指标分组选股池测试 ----------


def _make_score(ts_code: str, score: float) -> StockScore:
    return StockScore(ts_code=ts_code, name=ts_code, score=score)


class TestResolveGroupDefinitions:
    """分组定义解析"""

    def test_default_returns_default_groups(self):
        defs = _resolve_group_definitions(None)
        assert set(defs.keys()) == set(DEFAULT_VERIFY_POOL_GROUPS)
        for name in DEFAULT_VERIFY_POOL_GROUPS:
            assert defs[name] == CRITERIA_GROUPS[name]

    def test_list_of_known_names(self):
        defs = _resolve_group_definitions(["left_pullback", "quality_confirm"])
        assert set(defs.keys()) == {"left_pullback", "quality_confirm"}

    def test_unknown_group_is_skipped(self, caplog):
        defs = _resolve_group_definitions(["left_pullback", "not_a_group"])
        assert set(defs.keys()) == {"left_pullback"}
        assert "not_a_group" in caplog.text

    def test_custom_dict_passed_through(self):
        defs = _resolve_group_definitions({"custom": ["b1", "super_b1"]})
        assert defs == {"custom": ["b1", "super_b1"]}


class TestMergeGroupResults:
    """分组合并逻辑"""

    def test_union_dedup_and_keep_higher_score(self):
        g1 = [_make_score("A", 70), _make_score("B", 60)]
        g2 = [_make_score("A", 80), _make_score("C", 50)]
        merged = _merge_group_results({"g1": g1, "g2": g2}, "union")
        codes = {s.ts_code: s.score for s in merged}
        assert codes == {"A": 80, "B": 60, "C": 50}

    def test_union_sorts_by_score_descending(self):
        g1 = [_make_score("B", 60), _make_score("A", 90)]
        merged = _merge_group_results({"g1": g1}, "union")
        assert [s.ts_code for s in merged] == ["A", "B"]

    def test_intersection_requires_all_groups(self):
        g1 = [_make_score("A", 70), _make_score("B", 60)]
        g2 = [_make_score("A", 80), _make_score("C", 50)]
        merged = _merge_group_results({"g1": g1, "g2": g2}, "intersection")
        assert [s.ts_code for s in merged] == ["A"]

    def test_intersection_empty_when_one_group_empty(self):
        g1 = [_make_score("A", 70)]
        merged = _merge_group_results({"g1": g1, "g2": []}, "intersection")
        assert merged == []

    def test_empty_groups_return_empty(self):
        assert _merge_group_results({"g1": [], "g2": []}, "union") == []


class TestLoadV10StockPoolMultiCriteria:
    """多指标分组选股池加载器"""

    def test_custom_criteria_filter_and_ranking(self, db_conn, monkeypatch):
        """mock analyze + registry，验证 criteria 过滤和评分排序"""
        stocks = [
            {"ts_code": "000001.SZ", "name": "深A", "market": "主板", "list_date": "19910101"},
            {"ts_code": "000002.SZ", "name": "深B", "market": "主板", "list_date": "19910101"},
            {"ts_code": "600001.SH", "name": "沪A", "market": "主板", "list_date": "19910101"},
        ]
        _insert_stock_basic(db_conn, stocks)
        klines = []
        for s in stocks:
            klines.append(_make_kline(s["ts_code"], "20260101", 100.0, vol=1_000_000))
            klines.append(_make_kline(s["ts_code"], "20260102", 100.0, vol=1_000_000))
        _insert_klines(db_conn, klines)

        # mock get_recent_klines：返回 30 根 dummy klines，满足长度检查
        monkeypatch.setattr(
            "modules.screener.data.get_recent_klines",
            lambda code, days, datasource=None: list(range(30)),
        )

        # mock analyze_stock：SZ 评分 80，SH 评分 60
        def fake_analyze(ts_code, klines=None, datasource=None):
            return _make_score(ts_code, 80.0 if ts_code.endswith(".SZ") else 60.0)

        monkeypatch.setattr("modules.screener.engine.analyze_stock", fake_analyze)

        # mock registry：criteria "b1" 只选深A / 深B
        monkeypatch.setattr(
            "modules.screener.criteria._CRITERIA_REGISTRY",
            {"b1": lambda klines, score: score.ts_code.endswith(".SZ")},
        )

        result = load_v10_stock_pool_multi_criteria(
            groups={"custom": ["b1"]},
            limit=10,
            min_list_days=1,
            lookback_days=2,
            min_avg_amount=0,
        )
        # 两只 SZ，按评分 80 排序
        assert result == ["000001.SZ", "000002.SZ"]

    def test_unknown_group_fallback_to_quality_pool(self, db_conn):
        """非法 group 名时回退到基础质量池"""
        stocks = [
            {"ts_code": "000001.SZ", "name": "深A", "market": "主板", "list_date": "19910101"},
        ]
        _insert_stock_basic(db_conn, stocks)
        _insert_klines(
            db_conn,
            [
                _make_kline("000001.SZ", "20260101", 100.0, vol=1_000_000),
                _make_kline("000001.SZ", "20260102", 100.0, vol=1_000_000),
            ],
        )

        result = load_v10_stock_pool_multi_criteria(
            groups=["unknown_group"],
            limit=10,
            min_list_days=1,
            lookback_days=2,
            min_avg_amount=0,
        )
        # 回退到基础质量池，应该包含 000001.SZ
        assert "000001.SZ" in result


class TestOptimizeScriptPoolRouting:
    """optimize_for_v10_verify.py 的股票池参数路由"""

    def test_load_pool_routes_to_multi_criteria(self, monkeypatch):
        calls = []

        def fake_multi(groups, limit, mode):
            calls.append((groups, limit, mode))
            return ["000001.SZ"]

        monkeypatch.setattr(
            "modules.verify.pool.load_v10_stock_pool_multi_criteria",
            fake_multi,
        )

        args = Namespace(
            pool_groups="left_pullback,stage_accumulation",
            pool_mode="union",
            no_screener_pool=False,
            pool_criteria=None,
        )
        result = opt_script._load_pool(args, 50)
        assert result == ["000001.SZ"]
        assert calls == [(["left_pullback", "stage_accumulation"], 50, "union")]

    def test_load_pool_routes_to_custom_criteria(self, monkeypatch):
        calls = []

        def fake_multi(groups, limit, mode):
            calls.append((groups, limit, mode))
            return ["000002.SZ"]

        monkeypatch.setattr(
            "modules.verify.pool.load_v10_stock_pool_multi_criteria",
            fake_multi,
        )

        args = Namespace(
            pool_groups="left_pullback",
            pool_mode="union",
            no_screener_pool=False,
            pool_criteria="b1,super_b1",
        )
        result = opt_script._load_pool(args, 30)
        assert result == ["000002.SZ"]
        assert calls == [({"custom": ["b1", "super_b1"]}, 30, "union")]

    def test_load_pool_no_screener_fallback(self, monkeypatch):
        calls = []

        def fake_pool(limit):
            calls.append(("legacy", limit))
            return ["000003.SZ"]

        monkeypatch.setattr("modules.verify.pool.load_v10_stock_pool", fake_pool)

        args = Namespace(
            pool_groups="left_pullback",
            pool_mode="union",
            no_screener_pool=True,
            pool_criteria=None,
        )
        result = opt_script._load_pool(args, 20)
        assert result == ["000003.SZ"]
        assert calls == [("legacy", 20)]
