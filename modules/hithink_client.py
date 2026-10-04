#!/usr/bin/env python3
"""同花顺金融数据服务（hithink-finance）REST 客户端。

接入同花顺官方 A 股数据服务 https://fuyao.aicubes.cn（X-api-key 鉴权），
实现与 Tushare / Indevs / a-stock-data 相同的接口语义，供 CompositeDataSource
作为优先数据源使用。

上游 REST 契约唯一来源：Financial-API 仓库 ``docs/api/``。关键约束：

- 端点均为 GET；响应信封 ``{code, message, request_id, data}``，``code == 0`` 才算成功；
- 历史 K 线每次仅接受单个 thscode，时间窗口 ≤ 10 年；指数 K 线需显式 ``interval=1d``；
- 行情快照不含中文名，用估值快照（含 name）或 tickers/search 补齐；
- 限流（code=4001）与服务端异常（5xxx）按指数退避重试，最多 3 次；
- 空值（null）表示未披露，不自动补零。

环境变量：

- ``HITHINK_FINANCE_API_KEY``：统一 API Key（配置后才启用本数据源）；
- ``HITHINK_FINANCE_API_URL``：服务地址（可选，默认线上地址）。
"""

import logging
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://fuyao.aicubes.cn"
_TZ_SH = ZoneInfo("Asia/Shanghai")

# 契约：限流(4001)与服务端异常(5xxx)可在有界次数内退避重试；1xxx/2xxx 属调用方可修复错误，不重试
_RETRYABLE_CODES = {4001, 5001, 5002, 5003}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.5

_MIN_INTERVAL = 0.25  # 官方服务礼貌限速：约 240 次/分钟
_BATCH_SIZE = 100  # 估值快照契约上限：单次最多 100 个 thscode
_THSCODE_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")

_EXCHANGE_ALIASES = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}

_THSCODE_COLUMNS = ("ts_code", "ticker", "name", "exchange", "asset_type")


def _ms_to_date(ms: int) -> str:
    """毫秒 Unix 时间戳转上海时区日期字符串 YYYYMMDD"""
    return datetime.fromtimestamp(ms / 1000, tz=_TZ_SH).strftime("%Y%m%d")


def _date_to_ms(date_str: str) -> int | None:
    """YYYYMMDD 转 Asia/Shanghai 当日零点毫秒时间戳；解析失败返回 None"""
    try:
        dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=_TZ_SH)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def _normalize_thscode(ts_code: str) -> str:
    """校验并规范化 thscode（600519.SH）；非法输入返回空串"""
    ts_code = (ts_code or "").strip().upper()
    m = _THSCODE_RE.match(ts_code)
    return f"{m.group(1)}.{m.group(2)}" if m else ""


def _derive_market(thscode: str) -> str:
    """按代码规则推断板块名（与 a_stock_data 客户端口径一致，补充北交所）"""
    code = thscode.split(".")[0]
    suffix = thscode.split(".")[-1]
    if suffix == "BJ":
        return "北交所"
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith("3"):
        return "创业板"
    if code.startswith("6") or code.startswith("0"):
        return "主板"
    return "其他"


def _ticker_items_to_records(items: list[dict]) -> list[dict]:
    """TickerItem 列表转 tushare stock_list 兼容记录（ts_code/name/industry/market）"""
    records = []
    for it in items:
        thscode = it.get("thscode", "")
        records.append(
            {
                "ts_code": thscode,
                "name": it.get("name", ""),
                "industry": "",  # 上游目录不含行业，留空交由其他源补齐
                "market": _derive_market(thscode),
            }
        )
    return records


class HithinkFinanceClient:
    """同花顺金融数据服务客户端，实现与 Tushare/Indevs/AStockData 相同的接口。

    未配置 ``HITHINK_FINANCE_API_KEY`` 时所有取数方法返回 None/[]，
    由 CompositeDataSource 自动回退下一数据源，不抛异常中断调用链。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("HITHINK_FINANCE_API_KEY", "") or ""
        self._base_url = (base_url or os.environ.get("HITHINK_FINANCE_API_URL", "") or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._last_request_time = 0.0

    @property
    def is_configured(self) -> bool:
        """是否已配置 API Key"""
        return bool(self._api_key)

    @property
    def base_url(self) -> str:
        """服务基地址（测试注入用）"""
        return self._base_url

    def _rate_limit(self) -> None:
        """简单限流：相邻请求至少间隔 _MIN_INTERVAL 秒"""
        elapsed = time.time() - self._last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: dict) -> dict | None:
        """GET 请求并校验响应信封；成功返回 data 字段，失败返回 None。

        按契约仅对限流（4001）/ 服务端（5xxx）/ 网络错误做有界退避重试；
        其余业务错误记录 request_id 后直接返回 None，由上层回退其他数据源。
        """
        if not self.is_configured:
            logger.debug("[hithink] 未配置 HITHINK_FINANCE_API_KEY，跳过请求 %s", path)
            return None
        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {"X-api-key": self._api_key}
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._rate_limit()
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self._timeout)
                body = resp.json()
            except (requests.RequestException, ValueError) as e:
                last_error = e
                logger.warning("[hithink] %s 网络/解析失败(第%s次): %s", path, attempt, e)
                time.sleep(_BACKOFF_SECONDS * attempt)
                continue
            code = body.get("code")
            data = body.get("data")
            if code == 0 and data is not None:
                return data
            if code in _RETRYABLE_CODES:
                last_error = RuntimeError(f"code={code} message={body.get('message')}")
                logger.warning(
                    "[hithink] %s 可重试错误 code=%s(第%s次) request_id=%s",
                    path,
                    code,
                    attempt,
                    body.get("request_id"),
                )
                time.sleep(_BACKOFF_SECONDS * attempt)
                continue
            # 不可重试的业务错误：保留 request_id 方便向上游排查
            logger.warning(
                "[hithink] %s 业务失败 code=%s message=%s request_id=%s",
                path,
                code,
                body.get("message"),
                body.get("request_id"),
            )
            return None
        logger.warning("[hithink] %s 重试 %s 次仍失败: %s", path, _MAX_ATTEMPTS, last_error)
        return None

    def _chunks(self, codes: list[str], size: int = _BATCH_SIZE) -> list[list[str]]:
        """把 thscode 列表切成批量请求块（估值快照单次 ≤100 个）"""
        return [codes[i : i + size] for i in range(0, len(codes), size)]

    # ------------------------------------------------------------------
    # 基础能力
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """检查数据源可达性（检索茅台，最小代价探测鉴权与连通性）"""
        try:
            data = self._get("/api/meta/tickers/search", {"q": "600519", "limit": 1})
            items = (data or {}).get("item") or []
            return bool(items)
        except Exception as e:  # noqa: BLE001 — 健康检查兜底，不让异常打断调用链
            logger.warning("[hithink] health_check 失败: %s", e)
            return False

    def search_ticker(self, query: str, limit: int = 10, asset_type: str = "a-share") -> list[dict]:
        """标的检索消歧，返回 TickerItem 列表（thscode/ticker/name/exchange/asset_type）"""
        data = self._get("/api/meta/tickers/search", {"q": query, "limit": min(limit, 50), "asset_type": asset_type})
        return (data or {}).get("item") or []

    # ------------------------------------------------------------------
    # 日线行情
    # ------------------------------------------------------------------

    def _fetch_bars(self, path: str, params: dict) -> list[dict]:
        """拉取 K 线 item 列表并按日期升序整理"""
        data = self._get(path, params)
        items = (data or {}).get("item") or []
        return sorted(items, key=lambda x: x.get("date_ms", 0))

    @staticmethod
    def _bars_to_dataframe(items: list[dict], ts_code: str) -> pd.DataFrame:
        """PriceBarItem 列表转 tushare daily 兼容 DataFrame（vol=股、amount=元，透传量纲）"""
        rows = [
            {
                "ts_code": ts_code,
                "trade_date": _ms_to_date(bar["date_ms"]),
                "open": float(bar["open_price"]),
                "high": float(bar["high_price"]),
                "low": float(bar["low_price"]),
                "close": float(bar["close_price"]),
                "vol": float(bar["volume"]),
                "amount": float(bar["turnover"]),
            }
            for bar in items
        ]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        # pct_chg 用窗口内前收盘计算；首行依赖多拉的回看段，见 get_daily
        df["pct_chg"] = df["close"].pct_change() * 100
        df.loc[df.index[0], "pct_chg"] = 0.0
        return df

    def _daily_by_window(
        self, path: str, ts_code: str, start_date: str | None, end_date: str | None
    ) -> pd.DataFrame | None:
        """按窗口拉日线：多拉 20 个日历日回看段保证首行 pct_chg 真实，再裁剪回目标窗口"""
        end_date = end_date or datetime_now_shanghai().strftime("%Y%m%d")
        end_ms = _date_to_ms(end_date)
        if end_ms is None:
            return None
        if start_date:
            start_ms = _date_to_ms(start_date)
            if start_ms is None:
                return None
        else:
            # 未给起点时默认取最近约 250 个交易日（≈ 370 日历日），与 a-stock-data 的 days 口径对齐
            start_ms = end_ms - int(timedelta(days=370).total_seconds() * 1000)
            start_date = _ms_to_date(start_ms)
        # 回看段：多拉 20 个日历日，让窗口首行的 pct_chg 有真实的前收盘可算
        lookback_ms = int(timedelta(days=20).total_seconds() * 1000)
        bars = self._fetch_bars(
            path,
            {
                "thscode": ts_code,
                "interval": "1d",
                "start": start_ms - lookback_ms,
                "end": end_ms,
                "adjust": "none",  # 对齐 tushare pro.daily 不复权语义
            },
        )
        if not bars:
            return None
        df = self._bars_to_dataframe(bars, ts_code)
        if df.empty:
            return None
        df = df[df["trade_date"] >= start_date].reset_index(drop=True)
        return df if not df.empty else None

    # ------------------------------------------------------------------
    # DataSource 接口语义
    # ------------------------------------------------------------------

    def get_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅），不复权，对齐 tushare pro.daily"""
        code = _normalize_thscode(ts_code)
        if not code:
            return None
        try:
            return self._daily_by_window("/api/a-share/prices/historical", code, start_date, end_date)
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_daily 失败 %s: %s", ts_code, e)
            return None

    def get_index_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取指数日线行情（同花顺指数端点，无复权概念）"""
        code = _normalize_thscode(ts_code)
        if not code:
            return None
        try:
            return self._daily_by_window("/api/a-share-index/prices/historical", code, start_date, end_date)
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_index_daily 失败 %s: %s", ts_code, e)
            return None

    def _valuations_map(self, codes: list[str]) -> dict[str, dict]:
        """批量估值快照 → {thscode: {name, pe_ttm, pb_mrq, ...}}"""
        merged: dict[str, dict] = {}
        for chunk in self._chunks(codes):
            data = self._get("/api/a-share/valuations/snapshot", {"thscodes": ",".join(chunk)})
            for item in (data or {}).get("item") or []:
                merged[item.get("thscode", "")] = item
        return merged

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（快照行情 + 估值快照合并出 name/PE/PB）"""
        codes = [c for c in (_normalize_thscode(x) for x in ts_codes) if c]
        if not codes:
            return None
        quotes: dict[str, dict] = {}
        for chunk in self._chunks(codes):
            data = self._get("/api/a-share/prices/snapshot", {"thscodes": ",".join(chunk)})
            for item in (data or {}).get("item") or []:
                quotes[item.get("thscode", "")] = item
        if not quotes:
            return None
        valuations = self._valuations_map(list(quotes.keys()))
        rows = []
        for thscode, q in quotes.items():
            val = valuations.get(thscode, {})
            rows.append(
                {
                    "ts_code": thscode,
                    "name": val.get("name", ""),
                    "price": q.get("last_price", 0),
                    "open": q.get("open_price", 0),
                    "high": q.get("high_price", 0),
                    "low": q.get("low_price", 0),
                    "last_close": q.get("prev_price", 0),
                    "change_pct": q.get("price_change_ratio_pct", 0),
                    "vol": q.get("volume", 0),
                    "amount": q.get("turnover", 0),
                    "pe_ttm": val.get("pe_ttm", 0) or 0,
                    "pb": val.get("pb_mrq", 0) or 0,
                    "total_mv": 0,  # 上游暂无总市值字段，置 0 待补
                    "circ_mv": 0,
                    "turnover_rate": 0,
                }
            )
        return pd.DataFrame(rows)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """资金流向 — 同花顺公开能力暂不提供，返回 None 交由回退链处理"""
        return None

    def get_daily_basic(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取个股每日基础指标（估值快照口径：PE-TTM / PB-MRQ，仅当日）"""
        code = _normalize_thscode(ts_code)
        if not code:
            return None
        try:
            val = self._valuations_map([code]).get(code)
            if not val:
                return None
            return pd.DataFrame(
                [
                    {
                        "ts_code": code,
                        "trade_date": datetime_now_shanghai().strftime("%Y%m%d"),
                        "turnover_rate": 0,  # 上游暂无换手率，置 0 待补
                        "pe": val.get("pe_mrq", 0) or 0,
                        "pe_ttm": val.get("pe_ttm", 0) or 0,
                        "pb": val.get("pb_mrq", 0) or 0,
                        "ps_ttm": val.get("ps_ttm", 0) or 0,
                        "pcf_ttm": val.get("pcf_ttm", 0) or 0,
                        "total_mv": 0,
                        "circ_mv": 0,
                    }
                ]
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_daily_basic 失败 %s: %s", ts_code, e)
            return None

    def get_stk_factor(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """技术因子 — 上游不提供，返回 None"""
        return None

    def get_stock_basic(
        self,
        ts_code: str | None = None,
        name: str | None = None,
    ) -> pd.DataFrame | None:
        """获取股票基础信息（标的目录口径：ts_code/name/market；行业/上市日期上游暂缺）"""
        try:
            if ts_code:
                code = _normalize_thscode(ts_code)
                if not code:
                    return None
                items = self.search_ticker(code)
                hit = next((it for it in items if it.get("thscode", "").upper() == code), None)
                if hit is None:
                    return None
                return pd.DataFrame(
                    [
                        {
                            "ts_code": hit.get("thscode", code),
                            "name": hit.get("name", ""),
                            "industry": "",
                            "market": _derive_market(hit.get("thscode", code)),
                            "list_date": "",
                        }
                    ]
                )
            if name:
                items = self.search_ticker(name)
                rows = [
                    {
                        "ts_code": it.get("thscode", ""),
                        "name": it.get("name", ""),
                        "industry": "",
                        "market": _derive_market(it.get("thscode", "")),
                        "list_date": "",
                    }
                    for it in items
                    if it.get("thscode")
                ]
                return pd.DataFrame(rows) if rows else None
            # 全量查询走分页代码表
            records = self.list_all_a_share()
            return pd.DataFrame(records) if records else None
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_stock_basic 失败: %s", e)
            return None

    def list_all_a_share(self, exchanges: tuple[str, ...] = ("SH", "SZ", "BJ"), page_size: int = 1000) -> list[dict]:
        """分页拉全量 A 股代码表（终止条件：短页或空页；硬上限 20000 条防死循环）"""
        records: list[dict] = []
        offset = 0
        while offset < 20000:
            data = self._get(
                "/api/meta/tickers/list",
                {
                    "exchange": ",".join(exchanges),
                    "asset_type": "a-share",
                    "limit": page_size,
                    "offset": offset,
                },
            )
            items = (data or {}).get("item") or []
            records.extend(_ticker_items_to_records(items))
            if len(items) < page_size:
                break
            offset += page_size
        return records

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所；支持 SSE/SZSE/BSE 与 SH/SZ/BJ 两种写法）"""
        if exchange:
            ex = _EXCHANGE_ALIASES.get(exchange.upper(), exchange.upper())
            exchanges: tuple[str, ...] = (ex,)
        else:
            exchanges = ("SH", "SZ", "BJ")
        try:
            return self.list_all_a_share(exchanges=exchanges)
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_stock_list 失败: %s", e)
            return []

    def get_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame | None:
        """获取交易日历。

        注意：上游固定返回「今日往前一年」的交易日序列，无法提供未来日期；
        若请求窗口超出可用范围，只返回交集内的部分。
        """
        try:
            data = self._get("/api/a-share/calendar/trading-days", {})
            items = (data or {}).get("item") or []
            rows = []
            for it in items:
                cal_date = it.get("date") or _ms_to_date(it.get("date_ms", 0))
                if start_date and cal_date < start_date:
                    continue
                if end_date and cal_date > end_date:
                    continue
                rows.append({"exchange": exchange, "cal_date": cal_date, "is_open": 1})
            return pd.DataFrame(rows) if rows else None
        except Exception as e:  # noqa: BLE001
            logger.warning("[hithink] get_trade_cal 失败: %s", e)
            return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（升序），字段与 SQLite 缓存列对齐"""
        df = self.get_daily(ts_code, start_date, end_date)
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        if not start_date and days > 0:
            records = records[-days:]
        result = []
        for rec in records:
            result.append(
                {
                    "ts_code": rec.get("ts_code", ts_code),
                    "trade_date": rec.get("trade_date", ""),
                    "open": float(rec.get("open", 0)),
                    "high": float(rec.get("high", 0)),
                    "low": float(rec.get("low", 0)),
                    "close": float(rec.get("close", 0)),
                    "vol": float(rec.get("vol", 0)),
                    "amount": float(rec.get("amount", 0)),
                    "pct_chg": float(rec.get("pct_chg", 0)),
                }
            )
        return result


def datetime_now_shanghai() -> datetime:
    """当前上海时区时间（独立小函数便于测试打桩）"""
    return datetime.now(_TZ_SH)


# 测试
if __name__ == "__main__":
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO)

    client = HithinkFinanceClient()
    print("=" * 50)
    print("同花顺金融数据服务连通性测试")
    print("=" * 50)
    if not client.is_configured:
        print("未配置 HITHINK_FINANCE_API_KEY，请在 .env 中填写")
        sys.exit(1)

    print("\n=== 贵州茅台 (600519.SH) 日线 ===")
    df = client.get_daily("600519.SH", "20250701", "20250801")
    if df is not None and len(df) > 0:
        print(df[["trade_date", "open", "high", "low", "close", "pct_chg"]].head(10).to_string(index=False))
    else:
        print("无数据")

    print("\n=== 实时行情快照 ===")
    rt = client.get_realtime_quote(["600519.SH", "000001.SZ"])
    if rt is not None and len(rt) > 0:
        print(rt[["ts_code", "name", "price", "change_pct"]].to_string(index=False))
    else:
        print("无数据")

    print("\n=== 标的基础信息 ===")
    sb = client.get_stock_basic("600487.SH")
    if sb is not None and len(sb) > 0:
        print(sb.to_string(index=False))
    else:
        print("无数据")
