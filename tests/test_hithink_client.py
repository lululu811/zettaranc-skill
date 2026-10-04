"""hithink_client.py 测试 — 同花顺金融数据服务客户端（全 mock，零网络）

注意：本地 .env 可能配置了真实 HITHINK_FINANCE_API_KEY（modules/__init__.py 导入时加载），
所有用例必须显式 monkeypatch 该变量保证隔离。
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import requests

import modules.hithink_client as m
from modules.core.errors import ZettarancError
from modules.datasource import CompositeDataSource, get_datasource
from modules.hithink_client import (
    HithinkFinanceClient,
    _date_to_ms,
    _derive_market,
    _ms_to_date,
    _normalize_thscode,
)

_TZ = ZoneInfo("Asia/Shanghai")


# ==================== mock 工具 ====================


def _mock_resp(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = body
    return resp


def _ok(data) -> MagicMock:
    return _mock_resp({"code": 0, "message": "success", "request_id": "req-test", "data": data})


def _err(code: int, message: str) -> MagicMock:
    return _mock_resp({"code": code, "message": message, "request_id": "req-test", "data": None})


def _bar(date_str: str, close: float, open_: float | None = None, vol: float = 1000.0, amount: float = 1e5) -> dict:
    ms = int(datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=_TZ).timestamp() * 1000)
    o = open_ if open_ is not None else close * 0.99
    return {
        "date_ms": ms,
        "open_price": o,
        "high_price": max(o, close) * 1.01,
        "low_price": min(o, close) * 0.99,
        "close_price": close,
        "volume": vol,
        "turnover": amount,
    }


def _snapshot_item(thscode: str) -> dict:
    return {
        "thscode": thscode,
        "ticker": thscode.split(".")[0],
        "volume": 3347231,
        "turnover": 4278311000.0,
        "last_price": 1272.83,
        "price_change": -18.67,
        "price_change_ratio_pct": -1.4456,
        "open_price": 1291.5,
        "high_price": 1291.5,
        "low_price": 1272.01,
        "prev_price": 1291.5,
    }


def _valuation_item(thscode: str, name: str) -> dict:
    return {
        "thscode": thscode,
        "ticker": thscode.split(".")[0],
        "name": name,
        "pe_ttm": 19.54,
        "pe_mrq": 17.87,
        "pb_mrq": 6.33,
        "ps_ttm": 9.18,
        "pcf_ttm": 13.36,
    }


@pytest.fixture()
def client(monkeypatch) -> HithinkFinanceClient:
    """已配置 key 的客户端（隔离本地 .env 真实配置）"""
    monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-key")
    return HithinkFinanceClient(api_key=None, base_url="https://mock.local")


# ==================== 工具函数 ====================


class TestHelpers:
    def test_normalize_thscode(self):
        assert _normalize_thscode("600519.SH") == "600519.SH"
        assert _normalize_thscode("600519.sh") == "600519.SH"
        assert _normalize_thscode("000001.SZ") == "000001.SZ"
        assert _normalize_thscode("600519") == ""
        assert _normalize_thscode("abc.SH") == ""
        assert _normalize_thscode("") == ""

    def test_date_roundtrip(self):
        ms = _date_to_ms("20250701")
        assert ms is not None
        assert _ms_to_date(ms) == "20250701"

    def test_date_to_ms_invalid(self):
        assert _date_to_ms("not-a-date") is None

    def test_derive_market(self):
        assert _derive_market("688111.SH") == "科创板"
        assert _derive_market("300750.SZ") == "创业板"
        assert _derive_market("600519.SH") == "主板"
        assert _derive_market("000001.SZ") == "主板"
        assert _derive_market("430047.BJ") == "北交所"


# ==================== 信封与重试 ====================


class TestEnvelope:
    def test_success_returns_data(self, client):
        with patch.object(m.requests, "get", return_value=_ok({"item": [1]})) as mock_get:
            data = client._get("/api/meta/tickers/search", {"q": "600519"})
        assert data == {"item": [1]}
        assert mock_get.call_args.kwargs["headers"]["X-api-key"] == "test-key"

    def test_business_error_no_retry(self, client):
        with patch.object(m.requests, "get", return_value=_err(1002, "bad param")) as mock_get:
            data = client._get("/api/x", {})
        assert data is None
        assert mock_get.call_count == 1

    def test_rate_limit_retries_then_succeeds(self, client):
        with (
            patch.object(m.requests, "get", side_effect=[_err(4001, "slow"), _ok({"v": 1})]),
            patch.object(m.time, "sleep"),
        ):
            data = client._get("/api/x", {})
        assert data == {"v": 1}

    def test_network_error_exhausts_retries(self, client):
        with (
            patch.object(m.requests, "get", side_effect=requests.ConnectionError("boom")),
            patch.object(m.time, "sleep"),
        ):
            data = client._get("/api/x", {})
        assert data is None

    def test_invalid_json_counts_as_failure(self, client):
        bad = MagicMock()
        bad.json.side_effect = ValueError("not json")
        with patch.object(m.requests, "get", return_value=bad), patch.object(m.time, "sleep"):
            assert client._get("/api/x", {}) is None


class TestUnconfigured:
    def test_no_key_short_circuits(self, monkeypatch):
        monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
        c = HithinkFinanceClient()
        assert not c.is_configured
        with patch.object(m.requests, "get") as mock_get:
            assert c._get("/api/x", {}) is None
            assert c.health_check() is False
            assert c.get_daily("600519.SH", "20250701", "20250801") is None
        assert mock_get.call_count == 0


# ==================== 日线行情 ====================


class TestGetDaily:
    def test_maps_fields_and_trims_window(self, client):
        # 回看段 20250620(closes=10) + 窗口段 20250702..04，首行 pct_chg 应由回看段前收盘算出
        bars = [
            _bar("20250620", 10.0),
            _bar("20250701", 11.0),
            _bar("20250702", 12.0),
            _bar("20250703", 13.0),
            _bar("20250704", 14.0),
        ]
        with patch.object(m.requests, "get", return_value=_ok({"timestamp": 1, "item": bars})) as mock_get:
            df = client.get_daily("600487.SH", "20250702", "20250704")
        assert df is not None
        params = mock_get.call_args.kwargs["params"]
        assert params["thscode"] == "600487.SH"
        assert params["interval"] == "1d"
        assert params["adjust"] == "none"
        assert list(df.columns) == ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg"]
        assert df["trade_date"].min() == "20250702"
        assert df["trade_date"].max() == "20250704"
        first_pct = df.iloc[0]["pct_chg"]
        assert first_pct == pytest.approx((12.0 - 11.0) / 11.0 * 100)

    def test_default_days_window_when_no_dates(self, client):
        # 用相对当前的近期日期，避免窗口裁剪把写死的老日期过滤掉
        recent = (m.datetime_now_shanghai() - timedelta(days=1)).strftime("%Y%m%d")
        with patch.object(m.requests, "get", return_value=_ok({"item": [_bar(recent, 10.0)]})):
            df = client.get_daily("600487.SH")
        assert df is not None
        assert len(df) == 1

    def test_empty_items_returns_none(self, client):
        with patch.object(m.requests, "get", return_value=_ok({"item": []})):
            assert client.get_daily("600487.SH", "20250702", "20250704") is None

    def test_invalid_ts_code_no_request(self, client):
        with patch.object(m.requests, "get") as mock_get:
            assert client.get_daily("bad-code", "20250702", "20250704") is None
        assert mock_get.call_count == 0

    def test_index_daily_hits_index_path(self, client):
        with patch.object(m.requests, "get", return_value=_ok({"item": [_bar("20250801", 4000.0)]})) as mock_get:
            df = client.get_index_daily("000300.SH", "20250701", "20250801")
        assert df is not None
        assert mock_get.call_args.args[0] == "https://mock.local/api/a-share-index/prices/historical"


# ==================== 实时行情 / 基础指标 ====================


class TestRealtimeAndBasic:
    def test_realtime_quote_merges_snapshot_and_valuations(self, client):
        snapshot = _ok({"timestamp": 1, "total": 1, "item": [_snapshot_item("600519.SH")]})
        valuations = _ok({"timestamp": 2, "total": 1, "item": [_valuation_item("600519.SH", "贵州茅台")]})
        with patch.object(m.requests, "get", side_effect=[snapshot, valuations]) as mock_get:
            df = client.get_realtime_quote(["600519.SH"])
        assert df is not None
        row = df.iloc[0]
        assert row["ts_code"] == "600519.SH"
        assert row["name"] == "贵州茅台"
        assert row["price"] == 1272.83
        assert row["last_close"] == 1291.5
        assert row["change_pct"] == pytest.approx(-1.4456)
        assert row["pe_ttm"] == 19.54
        assert row["pb"] == 6.33
        paths = [c.args[0] for c in mock_get.call_args_list]
        assert "/api/a-share/prices/snapshot" in paths[0]
        assert "/api/a-share/valuations/snapshot" in paths[1]

    def test_moneyflow_not_supported(self, client):
        with patch.object(m.requests, "get") as mock_get:
            assert client.get_moneyflow("600519.SH", "20250801") is None
        assert mock_get.call_count == 0

    def test_stk_factor_not_supported(self, client):
        assert client.get_stk_factor("600519.SH", "20250701", "20250801") is None

    def test_daily_basic_from_valuations(self, client):
        valuations = _ok({"timestamp": 1, "total": 1, "item": [_valuation_item("600519.SH", "贵州茅台")]})
        with patch.object(m.requests, "get", return_value=valuations):
            df = client.get_daily_basic("600519.SH", "20250801", "20250822")
        assert df is not None
        row = df.iloc[0]
        assert row["ts_code"] == "600519.SH"
        assert row["pe_ttm"] == 19.54
        assert row["pe"] == 17.87
        assert row["pb"] == 6.33


# ==================== 标的目录 / 交易日历 ====================


class TestCatalogAndCalendar:
    def _ticker(self, thscode: str, name: str) -> dict:
        code, ex = thscode.split(".")
        return {
            "thscode": thscode,
            "ticker": code,
            "name": name,
            "exchange": ex,
            "asset_type": "a-share",
            "currency": "CNY",
        }

    def test_stock_basic_by_ts_code(self, client):
        items = {"item": [self._ticker("600519.SH", "贵州茅台")]}
        with patch.object(m.requests, "get", return_value=_ok(items)) as mock_get:
            df = client.get_stock_basic(ts_code="600519.SH")
        assert df is not None
        assert df.iloc[0]["name"] == "贵州茅台"
        assert df.iloc[0]["market"] == "主板"
        assert mock_get.call_args.kwargs["params"]["q"] == "600519.SH"

    def test_stock_basic_ts_code_miss_returns_none(self, client):
        items = {"item": [self._ticker("000001.SZ", "平安银行")]}
        with patch.object(m.requests, "get", return_value=_ok(items)):
            assert client.get_stock_basic(ts_code="600519.SH") is None

    def test_stock_basic_by_name(self, client):
        items = {"item": [self._ticker("600519.SH", "贵州茅台"), self._ticker("600809.SH", "山西汾酒")]}
        with patch.object(m.requests, "get", return_value=_ok(items)):
            df = client.get_stock_basic(name="贵州")
        assert df is not None
        assert len(df) == 2

    def test_stock_list_pagination_stops_on_short_page(self, client):
        page_full = {
            "item": [
                {"thscode": f"60000{i}.SH", "ticker": f"60000{i}", "name": f"s{i}", "exchange": "SH"} for i in range(2)
            ]
        }
        page_short = {"item": [{"thscode": "600099.SH", "ticker": "600099", "name": "tail", "exchange": "SH"}]}
        with patch.object(m.requests, "get", side_effect=[_ok(page_full), _ok(page_short)]) as mock_get:
            records = client.list_all_a_share(exchanges=("SH",), page_size=2)
        assert len(records) == 3
        offsets = [c.kwargs["params"]["offset"] for c in mock_get.call_args_list]
        assert offsets == [0, 2]

    def test_stock_list_exchange_alias(self, client):
        with patch.object(m.requests, "get", return_value=_ok({"item": []})) as mock_get:
            client.get_stock_list("SSE")
        assert mock_get.call_args.kwargs["params"]["exchange"] == "SH"

    def test_trade_cal_filters_window(self, client):
        days = {"item": [{"date_ms": _date_to_ms(d), "date": d} for d in ("20250820", "20250821", "20250822")]}
        with patch.object(m.requests, "get", return_value=_ok(days)):
            df = client.get_trade_cal(exchange="SSE", start_date="20250821", end_date="20250822")
        assert df is not None
        assert list(df["cal_date"]) == ["20250821", "20250822"]
        assert (df["is_open"] == 1).all()

    def test_kline_dicts_shape_and_trim(self, client):
        # 相对当前生成近 5 个日历日，days=3 只保留最近 3 条
        now = m.datetime_now_shanghai()
        bars = [_bar((now - timedelta(days=i)).strftime("%Y%m%d"), 10.0 + i) for i in range(4, -1, -1)]
        with patch.object(m.requests, "get", return_value=_ok({"item": bars})):
            dicts = client.get_kline_dicts("600487.SH", days=3)
        assert len(dicts) == 3
        assert set(dicts[0].keys()) == {
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
            "pct_chg",
        }
        latest_date = now.strftime("%Y%m%d")
        assert dicts[-1]["trade_date"] == latest_date


# ==================== 健康检查 ====================


class TestHealthCheck:
    def test_healthy(self, client):
        with patch.object(
            m.requests,
            "get",
            return_value=_ok({"item": [{"thscode": "600519.SH", "ticker": "600519", "name": "贵州茅台"}]}),
        ):
            assert client.health_check() is True

    def test_unhealthy_on_error(self, client):
        with patch.object(m.requests, "get", return_value=_err(2003, "invalid key")):
            assert client.health_check() is False


# ==================== CompositeDataSource 集成 ====================


class TestCompositeIntegration:
    def test_valid_preferred_contains_hithink(self):
        assert "hithink" in CompositeDataSource.VALID_PREFERRED

    def test_invalid_preferred_raises(self):
        with pytest.raises(ZettarancError):
            CompositeDataSource(preferred="nope")

    def test_factory_returns_hithink_source(self, monkeypatch):
        monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-key")
        ds = get_datasource("hithink")
        assert ds.name == "hithink"

    def test_auto_chain_prefers_hithink_when_key_set(self, monkeypatch):
        monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-key")
        names = [s.name for s in CompositeDataSource()._auto_sources()]
        assert names[0] == "hithink"
        assert "a-stock-data" in names

    def test_auto_chain_falls_back_without_key(self, monkeypatch):
        monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
        monkeypatch.delenv("INDEVS_API_KEY", raising=False)
        names = [s.name for s in CompositeDataSource()._auto_sources()]
        assert names[0] == "a-stock-data"

    def test_explicit_preferred_dispatches_to_hithink(self, monkeypatch):
        monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-key")
        c = CompositeDataSource(preferred="hithink")
        assert c.get_moneyflow("600519.SH", "20250801") is None  # 显式不支持接口返回 None
        assert c.name == "composite(hithink)"
