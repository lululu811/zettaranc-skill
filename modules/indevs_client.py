#!/usr/bin/env python3
"""
Indevs Tushare Replay API 客户端

文档: https://ai-tool.indevs.in/quant/tushare-pro-catalog/
调用方式:
  GET https://ai-tool.indevs.in/tushare/pro/<api_name>
  Header: X-API-Key: <api_key>
返回 envelope:
  {"code": 0, "msg": "ok", "count": N, "data": {"fields": [...], "items": [[...], ...]}}

v3.10.4: 接入 ZettarancError
- 内部 ``request()`` 在 API key 缺失 / 返回错误码 / 网络失败时抛
  ``ZettarancError(ErrorCode.INDEVS_NO_DATA, ...)``；
- 公开 ``get_*`` / ``get_kline_dicts`` 方法仍返回 ``Optional`` 以遵守 DataSource Protocol，
  但不再静默吞错——失败通过日志 + 上层 try/except 暴露。
"""

from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any

import pandas as pd
import requests

from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)

INDEVS_API_KEY = os.environ.get("INDEVS_API_KEY", "")
INDEVS_API_URL = os.environ.get("INDEVS_API_URL", "https://ai-tool.indevs.in/tushare/pro")

_DNS_FALLBACK_IPS = {
    "ai-tool.indevs.in": ["172.67.197.91"],
    "tushare.indevs.in": ["172.67.197.91"],
}
_DNS_PATCHED = False


def _install_dns_fallback() -> None:
    """如果域名解析失败，注入 DNS fallback（仅对 ai-tool.indevs.in / tushare.indevs.in）。"""
    global _DNS_PATCHED
    if _DNS_PATCHED:
        return

    def _normalize_host(host: Any) -> str:
        if isinstance(host, bytes):
            host = host.decode("ascii", "ignore")
        return host.rstrip(".") if isinstance(host, str) else host

    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname

    def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        try:
            return original_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror:
            fallback_ips = _DNS_FALLBACK_IPS.get(_normalize_host(host))
            if not fallback_ips:
                raise
            results = []
            for ip in fallback_ips:
                try:
                    results.extend(original_getaddrinfo(ip, port, family, type, proto, flags))
                except socket.gaierror:
                    continue
            if not results:
                raise
            return results

    def _gethostbyname(host):
        try:
            return original_gethostbyname(host)
        except socket.gaierror:
            fallback_ips = _DNS_FALLBACK_IPS.get(_normalize_host(host))
            if not fallback_ips:
                raise
            return fallback_ips[0]

    socket.getaddrinfo = _getaddrinfo
    socket.gethostbyname = _gethostbyname
    _DNS_PATCHED = True


def _dataframe_from_payload(payload: dict[str, Any] | None) -> pd.DataFrame | None:
    """把 Indevs 返回的 fields/items 结构转成 DataFrame。"""
    if payload is None:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not fields or not items:
        return pd.DataFrame(columns=fields) if fields else None
    return pd.DataFrame(items, columns=fields)


class IndevsClient:
    """Indevs Tushare Replay API 客户端。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or INDEVS_API_KEY
        self.base_url = (base_url or INDEVS_API_URL).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-API-Key": self.api_key,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "User-Agent": "zettaranc-skill-indevs/1.0",
            }
        )
        self._session.trust_env = False
        self._session.proxies.update({"http": "", "https": ""})
        self._min_interval = 0.5
        self._last_request_time = 0.0
        _install_dns_fallback()

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def request(
        self,
        api_name: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """调用单个 API，返回原始 JSON envelope。

        v3.10.4: 不再返回 None。失败时抛 ``ZettarancError(INDEVS_NO_DATA, ...)``：
        - API key 未配置
        - 接口返回 ``code != 0``
        - 重试 3 次仍失败（网络/HTTP 异常）
        """
        if not self.api_key:
            raise ZettarancError(
                ErrorCode.INDEVS_NO_DATA,
                f"Indevs {api_name}: INDEVS_API_KEY 未配置",
            )

        self._rate_limit()
        url = f"{self.base_url}/{api_name}"
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "zettaranc-skill-indevs/1.0",
        }

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    url,
                    params=params or {},
                    headers=headers,
                    timeout=timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("code") != 0:
                    raise ZettarancError(
                        ErrorCode.INDEVS_NO_DATA,
                        f"Indevs {api_name} 返回错误: {payload.get('msg')}",
                    )
                return payload
            except ZettarancError:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < 2:
                    sleep_time = 0.5 * (attempt + 1)
                    logger.debug("Indevs %s 第 %d 次重试: %s", api_name, attempt + 1, e)
                    time.sleep(sleep_time)
                continue

        raise ZettarancError(
            ErrorCode.INDEVS_NO_DATA,
            f"Indevs {api_name} 请求失败 (3 次重试耗尽): {last_error}",
            cause=last_error,
        )

    def get_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return _dataframe_from_payload(self.request("daily", params))
        except ZettarancError as e:
            logger.warning("Indevs get_daily 失败: %s", e.message)
            return None

    def get_index_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return _dataframe_from_payload(self.request("index_daily", params))
        except ZettarancError as e:
            logger.warning("Indevs get_index_daily 失败: %s", e.message)
            return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        # 复用 rt_k 全市场快照接口，按 ts_code 过滤
        try:
            payload = self.request(
                "rt_k",
                params={"limit": 7000, "fields": "ts_code,trade_date,open,high,low,close,vol,amount,pct_chg"},
            )
        except ZettarancError as e:
            logger.warning("Indevs get_realtime_quote 失败: %s", e.message)
            return None
        df = _dataframe_from_payload(payload)
        if df is None or df.empty:
            return None
        return df[df["ts_code"].isin(ts_codes)].copy() if "ts_code" in df.columns else None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        try:
            return _dataframe_from_payload(
                self.request("moneyflow", params={"ts_code": ts_code, "trade_date": trade_date})
            )
        except ZettarancError as e:
            logger.warning("Indevs get_moneyflow 失败: %s", e.message)
            return None

    def get_daily_basic(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return _dataframe_from_payload(self.request("daily_basic", params))
        except ZettarancError as e:
            logger.warning("Indevs get_daily_basic 失败: %s", e.message)
            return None

    def get_stk_factor(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return _dataframe_from_payload(self.request("stk_factor", params))
        except ZettarancError as e:
            logger.warning("Indevs get_stk_factor 失败: %s", e.message)
            return None

    def get_stock_basic(
        self,
        ts_code: str | None = None,
        name: str | None = None,
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"list_status": "L"}
        if ts_code:
            params["ts_code"] = ts_code
        if name:
            params["name"] = name
        try:
            df = _dataframe_from_payload(self.request("stock_basic", params))
        except ZettarancError as e:
            logger.warning("Indevs get_stock_basic 失败: %s", e.message)
            return None
        if df is not None and "is_hs" not in df.columns:
            df["is_hs"] = ""
        return df

    def get_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {"exchange": exchange}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return _dataframe_from_payload(self.request("trade_cal", params))
        except ZettarancError as e:
            logger.warning("Indevs get_trade_cal 失败: %s", e.message)
            return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        df = self.get_stock_basic()
        if df is None or df.empty:
            return []
        columns = ["ts_code", "name", "industry", "market"]
        available = [c for c in columns if c in df.columns]
        return df[available].to_dict("records")

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        # 指数代码走 index_daily
        if ts_code and ts_code.upper() in _INDEX_CODES:
            df = self.get_index_daily(ts_code, start_date, end_date)
        else:
            df = self.get_daily(ts_code, start_date, end_date)
        if df is None or df.empty:
            return []
        # Indevs 返回 pre_close，DailyData 期望 prev_close
        if "pre_close" in df.columns:
            df = df.rename(columns={"pre_close": "prev_close"})
        records = df.to_dict("records")
        # 字段标准化：DailyData 用 prev_close，部分接口返回 pre_close / change 会冲突
        for rec in records:
            if "pre_close" in rec:
                rec["prev_close"] = rec.pop("pre_close")
            rec.pop("change", None)
        records.sort(key=lambda x: x.get("trade_date", ""))
        if not start_date and days > 0:
            records = records[-days:]
        return records

    def health_check(self) -> bool:
        try:
            payload = self.request("stock_basic", params={"ts_code": "000001.SZ"})
        except ZettarancError:
            return False
        return payload is not None and payload.get("code") == 0


_INDEX_CODES = {
    "000001.SH",
    "000002.SH",
    "000003.SH",
    "000016.SH",
    "000300.SH",
    "000688.SH",
    "000905.SH",
    "399001.SZ",
    "399006.SZ",
    "399005.SZ",
    "399300.SZ",
    "399016.SZ",
    "399905.SZ",
    "000852.SH",
}
