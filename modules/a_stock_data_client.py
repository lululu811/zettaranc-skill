"""
A-Stock-Data 免费数据源客户端

集成 https://github.com/simonlin1212/a-stock-data 的免费 A 股数据接口，
作为 tushare 的免费替代方案。无需 API Key，直接调用公开 HTTP 接口。

数据源映射：
  - 实时行情 -> 腾讯财经 tencent_quote()
  - 日K线    -> 百度股市通 baidu_kline_with_ma()
  - 股票基础信息 -> 东财 push2 eastmoney_stock_info()
  - 资金流向  -> 东财 push2 eastmoney_fund_flow_minute() / stock_fund_flow_120d()
  - 龙虎榜   -> 东财 datacenter dragon_tiger_board()
  - 涨停池   -> 东财 push2ex em_zt_pool()
  - 北向资金  -> 同花顺 hsgt_realtime()

所有东财接口通过 _em_get() 统一限流防封。
"""

from __future__ import annotations

import logging
import random
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _ts_code_to_6digit(ts_code: str) -> str:
    """将 tushare 格式的代码 (000001.SZ) 转为 6 位代码 (000001)"""
    if not ts_code:
        return ""
    return ts_code.split(".")[0]


def _6digit_to_ts_code(code: str) -> str:
    """将 6 位代码 (000001) 转为 tushare 格式 (000001.SZ)"""
    if not code:
        return ""
    code = code.strip()
    if "." in code:
        return code
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def _get_market_code(code: str) -> int:
    """6 位代码 -> 东财市场代码 (1=SH, 0=SZ/BJ)"""
    if code.startswith(("6", "9")):
        return 1
    return 0


def _get_prefix(code: str) -> str:
    """6 位代码 -> 市场前缀 (sh/sz/bj)"""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    else:
        return "sz"


# ---------------------------------------------------------------------------
# 东财防封：全局节流 + 会话复用
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": _UA})
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _em_adapter = HTTPAdapter(max_retries=Retry(
        total=3, connect=3, backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
    _EM_SESSION.mount("https://", _em_adapter)
    _EM_SESSION.mount("http://", _em_adapter)
except Exception:
    pass
_EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def _em_get(url: str, params: dict | None = None, headers: dict | None = None,
            timeout: int = 15, **kwargs) -> requests.Response:
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。"""
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return _EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def _eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    """东财数据中心统一查询"""
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = _em_get(_DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ---------------------------------------------------------------------------
# 腾讯财经 — 实时行情 (不封IP)
# ---------------------------------------------------------------------------


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    批量拉取腾讯财经实时行情。
    codes: 6 位代码列表 ["688017", "300476"]
    返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
    """
    prefixed = []
    for c in codes:
        c6 = _ts_code_to_6digit(c) if "." in c else c
        prefixed.append(f"{_get_prefix(c6)}{c6}")

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "amplitude_pct": float(vals[43]) if vals[43] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result


# ---------------------------------------------------------------------------
# 百度股市通 — 日K线带 MA
# ---------------------------------------------------------------------------


def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通K线，返回自带 ma5/ma10/ma20 均价"""
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": code, "start_time": start_time, "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    result = d.get("Result")
    # 百度 API 可能返回 dict 或 list（空结果时返回 []）
    if isinstance(result, list):
        return {"keys": [], "rows": []}
    if not isinstance(result, dict):
        return {"keys": [], "rows": []}
    md = result.get("newMarketData", {})
    if not isinstance(md, dict):
        return {"keys": [], "rows": []}
    keys = md.get("keys", [])
    rows = md.get("marketData", "")
    if isinstance(rows, str):
        rows = rows.split(";")
    elif not isinstance(rows, list):
        rows = []
    return {"keys": keys, "rows": rows}


def baidu_kline_to_dataframe(code: str, days: int = 60) -> pd.DataFrame | None:
    """百度K线转 DataFrame，列名对齐 tushare daily 格式"""
    data = baidu_kline_with_ma(code)
    keys = data.get("keys", [])
    rows = data.get("rows", [])
    if not keys or not rows:
        return None

    # 过滤空行
    parsed = []
    for row_str in rows:
        if not row_str.strip():
            continue
        vals = row_str.split(",")
        if len(vals) >= len(keys):
            parsed.append(dict(zip(keys, vals)))

    if not parsed:
        return None

    df = pd.DataFrame(parsed)

    # 列名映射
    col_map = {
        "time": "trade_date",
        "open": "open",
        "close": "close",
        "high": "high",
        "low": "low",
        "volume": "vol",
        "amount": "amount",
    }
    rename_cols = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename_cols)

    # 数值转换
    for col in ["open", "high", "low", "close", "vol", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 计算涨跌幅
    if "close" in df.columns:
        df["pct_chg"] = df["close"].pct_change() * 100
        df["pct_chg"].iloc[0] = 0.0

    # 日期格式化
    if "trade_date" in df.columns:
        df["trade_date"] = df["trade_date"].str.replace("-", "")

    # 限制天数
    if days > 0 and len(df) > days:
        df = df.tail(days).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# 东财个股信息 — 替代 get_stock_basic
# ---------------------------------------------------------------------------


def eastmoney_stock_info(code: str) -> dict:
    """东财个股基本面信息"""
    market_code = _get_market_code(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
        "secid": f"{market_code}.{code}",
    }
    headers = {"User-Agent": _UA}
    r = _em_get(url, params=params, headers=headers, timeout=10)
    d = r.json().get("data", {})
    return {
        "code": d.get("f57", ""),
        "name": d.get("f58", ""),
        "industry": d.get("f127", ""),
        "total_shares": d.get("f84", 0),
        "float_shares": d.get("f85", 0),
        "mcap": d.get("f116", 0),
        "float_mcap": d.get("f117", 0),
        "list_date": str(d.get("f189", "")),
        "price": d.get("f43", 0),
    }


# ---------------------------------------------------------------------------
# 东财资金流向 — 替代 get_moneyflow
# ---------------------------------------------------------------------------


def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """个股资金流向（分钟级，当日盘中），单位：元"""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {
        "User-Agent": _UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    try:
        r = _em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception as e:
        logger.warning("[a-stock-data] push2 资金流请求失败: %s", e)
        return []

    rows = []
    for line in d.get("data", {}).get("klines", []):
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "time": parts[0],
                "main_net": float(parts[1]),
                "small_net": float(parts[2]),
                "mid_net": float(parts[3]),
                "large_net": float(parts[4]),
                "super_net": float(parts[5]),
            })
    return rows


def stock_fund_flow_120d(code: str) -> list[dict]:
    """个股资金流向（120日，日级），单位：元"""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": secid, "klt": 101,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "lmt": "120",
    }
    headers = {
        "User-Agent": _UA,
        "Referer": "https://quote.eastmoney.com/",
    }
    try:
        r = _em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception as e:
        logger.warning("[a-stock-data] push2his 资金流请求失败: %s", e)
        return []

    rows = []
    for line in d.get("data", {}).get("klines", []):
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "date": parts[0],
                "super_net": float(parts[1]),
                "large_net": float(parts[2]),
                "mid_net": float(parts[3]),
                "small_net": float(parts[4]),
                "main_net": float(parts[5]),
            })
    return rows


# ---------------------------------------------------------------------------
# mootdx (通达信 TCP) — K线备用数据源
# ---------------------------------------------------------------------------


def _mootdx_kline(code: str, days: int = 60, frequency: int = 9) -> pd.DataFrame | None:
    """通过 mootdx (通达信 TCP 7709) 获取 K 线数据。
    frequency: 9=日线, 8=1分钟, 0=5分钟, 5=周线, 6=月线
    返回 DataFrame 或 None（mootdx 不可用时）。
    """
    try:
        from mootdx.quotes import Quotes
    except ImportError:
        logger.debug("[a-stock-data] mootdx 未安装，跳过")
        return None

    # 备选服务器列表（按延迟排序）
    _TDX_SERVERS = [
        ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
        ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
        ('123.60.70.228', 7709), ('124.71.9.153', 7709),
    ]

    def _probe(ip, port, timeout=2.0):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            return False

    try:
        client = None
        for ip, port in _TDX_SERVERS:
            if _probe(ip, port):
                client = Quotes.factory(market='std', server=(ip, port))
                break
        if client is None:
            try:
                client = Quotes.factory(market='std', bestip=True)
            except Exception:
                client = Quotes.factory(market='std')

        bars = client.bars(symbol=code, frequency=frequency, offset=days)
        if bars is None or bars.empty:
            return None

        # 列名映射
        df = bars.copy()
        col_map = {"datetime": "trade_date"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # 日期格式化
        if "trade_date" in df.columns:
            df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")[:8]

        # 计算涨跌幅
        if "close" in df.columns and "pct_chg" not in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100
            df["pct_chg"].iloc[0] = 0.0

        return df
    except Exception as e:
        logger.debug("[a-stock-data] mootdx K线获取失败: %s", e)
        return None


# ---------------------------------------------------------------------------
# AStockDataClient — 实现 DataSource Protocol 接口
# ---------------------------------------------------------------------------


class AStockDataClient:
    """A-Stock-Data 免费数据源客户端，实现与 Tushare/Indevs 相同的接口。

    免费替代 tushare，无需 API Key，直接调用公开 HTTP 接口。
    """

    def __init__(self) -> None:
        self._min_interval = 0.5
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """简单限流"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def health_check(self) -> bool:
        """检查数据源可达性（腾讯财经不封IP，作为健康检查基准）"""
        try:
            result = tencent_quote(["000001"])
            return bool(result)
        except Exception:
            return False

    def get_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）。
        数据源优先级：百度股市通 -> mootdx (通达信 TCP)
        """
        code = _ts_code_to_6digit(ts_code)
        if not code:
            return None

        # 1. 尝试百度 K 线
        self._rate_limit()
        try:
            days = 500
            if start_date and end_date:
                try:
                    d1 = datetime.strptime(start_date, "%Y%m%d")
                    d2 = datetime.strptime(end_date, "%Y%m%d")
                    days = max((d2 - d1).days + 30, 60)
                except ValueError:
                    pass
            df = baidu_kline_to_dataframe(code, days=days)
            if df is not None and not df.empty:
                df["ts_code"] = ts_code
                if start_date and "trade_date" in df.columns:
                    df = df[df["trade_date"] >= start_date]
                if end_date and "trade_date" in df.columns:
                    df = df[df["trade_date"] <= end_date]
                if not df.empty:
                    return df
        except Exception as e:
            logger.debug("[a-stock-data] 百度 K 线失败 %s: %s, 尝试 mootdx", ts_code, e)

        # 2. 回退到 mootdx (通达信 TCP)
        self._rate_limit()
        try:
            df = _mootdx_kline(code, days=500)
            if df is not None and not df.empty:
                df["ts_code"] = ts_code
                if start_date and "trade_date" in df.columns:
                    df = df[df["trade_date"] >= start_date]
                if end_date and "trade_date" in df.columns:
                    df = df[df["trade_date"] <= end_date]
                if not df.empty:
                    return df
        except Exception as e:
            logger.warning("[a-stock-data] get_daily 全部失败 %s: %s", ts_code, e)

        return None

    def get_index_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取指数日线行情 — 百度K线也支持指数"""
        code = _ts_code_to_6digit(ts_code)
        if not code:
            return None
        self._rate_limit()
        try:
            df = baidu_kline_to_dataframe(code, days=500)
            if df is None or df.empty:
                return None
            df["ts_code"] = ts_code
            if start_date and "trade_date" in df.columns:
                df = df[df["trade_date"] >= start_date]
            if end_date and "trade_date" in df.columns:
                df = df[df["trade_date"] <= end_date]
            return df if not df.empty else None
        except Exception as e:
            logger.warning("[a-stock-data] get_index_daily 失败 %s: %s", ts_code, e)
            return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照，数据源：腾讯财经"""
        codes_6 = [_ts_code_to_6digit(c) for c in ts_codes]
        self._rate_limit()
        try:
            quotes = tencent_quote(codes_6)
            if not quotes:
                return None
            rows = []
            for code_6, q in quotes.items():
                ts_code = _6digit_to_ts_code(code_6)
                rows.append({
                    "ts_code": ts_code,
                    "name": q.get("name", ""),
                    "price": q.get("price", 0),
                    "open": q.get("open", 0),
                    "high": q.get("high", 0),
                    "low": q.get("low", 0),
                    "last_close": q.get("last_close", 0),
                    "change_pct": q.get("change_pct", 0),
                    "vol": q.get("amount_wan", 0) * 10000,
                    "amount": q.get("amount_wan", 0) * 10000,
                    "pe_ttm": q.get("pe_ttm", 0),
                    "pb": q.get("pb", 0),
                    "total_mv": q.get("mcap_yi", 0) * 1e8,
                    "circ_mv": q.get("float_mcap_yi", 0) * 1e8,
                    "turnover_rate": q.get("turnover_pct", 0),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.warning("[a-stock-data] get_realtime_quote 失败: %s", e)
            return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向，数据源：东财 push2（分钟级）"""
        code = _ts_code_to_6digit(ts_code)
        if not code:
            return None
        self._rate_limit()
        try:
            rows = eastmoney_fund_flow_minute(code)
            if not rows:
                return None
            total_main = sum(r["main_net"] for r in rows)
            total_super = sum(r["super_net"] for r in rows)
            total_large = sum(r["large_net"] for r in rows)
            total_mid = sum(r["mid_net"] for r in rows)
            total_small = sum(r["small_net"] for r in rows)
            df = pd.DataFrame([{
                "ts_code": ts_code,
                "trade_date": trade_date,
                "buy_sm_vol": total_small,
                "buy_med_vol": total_mid,
                "buy_lg_vol": total_large,
                "buy_elg_vol": total_super,
                "sell_sm_vol": 0,
                "sell_med_vol": 0,
                "sell_lg_vol": 0,
                "sell_elg_vol": 0,
                "net_mf_amount": total_main,
            }])
            return df
        except Exception as e:
            logger.warning("[a-stock-data] get_moneyflow 失败 %s: %s", ts_code, e)
            return None

    def get_daily_basic(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取个股每日基础指标，数据源：腾讯财经"""
        code = _ts_code_to_6digit(ts_code)
        if not code:
            return None
        self._rate_limit()
        try:
            quotes = tencent_quote([code])
            q = quotes.get(code)
            if not q:
                return None
            df = pd.DataFrame([{
                "ts_code": ts_code,
                "trade_date": datetime.now().strftime("%Y%m%d"),
                "turnover_rate": q.get("turnover_pct", 0),
                "pe": q.get("pe_static", 0),
                "pe_ttm": q.get("pe_ttm", 0),
                "pb": q.get("pb", 0),
                "total_mv": q.get("mcap_yi", 0) * 1e8,
                "circ_mv": q.get("float_mcap_yi", 0) * 1e8,
            }])
            return df
        except Exception as e:
            logger.warning("[a-stock-data] get_daily_basic 失败 %s: %s", ts_code, e)
            return None

    def get_stk_factor(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """获取个股技术因子 — a-stock-data 不直接提供，返回 None"""
        return None

    def get_stock_basic(
        self,
        ts_code: str | None = None,
        name: str | None = None,
    ) -> pd.DataFrame | None:
        """获取股票基础信息，数据源：东财 push2"""
        if ts_code:
            code = _ts_code_to_6digit(ts_code)
            if not code:
                return None
            self._rate_limit()
            try:
                info = eastmoney_stock_info(code)
                df = pd.DataFrame([{
                    "ts_code": ts_code,
                    "name": info.get("name", ""),
                    "industry": info.get("industry", ""),
                    "market": "主板" if code.startswith("6") else (
                        "创业板" if code.startswith("3") else (
                            "科创板" if code.startswith("688") else "其他"
                        )
                    ),
                    "list_date": info.get("list_date", ""),
                    "total_share": info.get("total_shares", 0),
                    "float_share": info.get("float_shares", 0),
                    "total_mv": info.get("mcap", 0),
                    "float_mv": info.get("float_mcap", 0),
                }])
                return df
            except Exception as e:
                logger.warning("[a-stock-data] get_stock_basic 失败 %s: %s", ts_code, e)
                return None
        logger.info("[a-stock-data] get_stock_basic 全量查询不支持，回退其他数据源")
        return None

    def get_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame | None:
        """获取交易日历 — a-stock-data 不直接提供，返回 None"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表 — a-stock-data 不提供全量列表，返回空"""
        return []

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表，数据源：百度股市通"""
        df = self.get_daily(ts_code, start_date, end_date)
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        records.sort(key=lambda x: x.get("trade_date", ""))
        if not start_date and days > 0:
            records = records[-days:]
        result = []
        for rec in records:
            result.append({
                "ts_code": rec.get("ts_code", ts_code),
                "trade_date": rec.get("trade_date", ""),
                "open": float(rec.get("open", 0)),
                "high": float(rec.get("high", 0)),
                "low": float(rec.get("low", 0)),
                "close": float(rec.get("close", 0)),
                "vol": float(rec.get("vol", 0)),
                "amount": float(rec.get("amount", 0)),
                "pct_chg": float(rec.get("pct_chg", 0)),
            })
        return result