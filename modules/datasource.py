"""
统一数据源抽象层

定义 DataSource Protocol，并封装 Tushare、Bridge、SQLite、Indevs 以及自动回退的 Composite 数据源。
"""

import logging
import os
import sqlite3
from typing import Protocol, runtime_checkable

import pandas as pd
import requests

from .bridge_client import (
    BridgeConfig,
    get_all_stocks_bridge_first,
    get_daily_klines,
    is_bridge_available,
    set_bridge_config,
)
from .core.kline import KLINE_COLUMNS, read_kline_rows, read_kline_rows_batch, resolve_kline_limit
from .database import get_connection, save_klines
from .hithink_client import HithinkFinanceClient
from .indevs_client import IndevsClient
from .tushare_client import TushareClient
from .a_stock_data_client import AStockDataClient
from modules.core.errors import ErrorCode, ZettarancError
from modules.datasource_resolution import resolve_provider

logger = logging.getLogger(__name__)

# get_kline_dicts 的固定返回列（与 SELECT 顺序一致，用于元组转 dict）
# K 线列定义与读取 SQL 的唯一来源：modules.core.kline
_KLINE_COLUMNS = KLINE_COLUMNS


@runtime_checkable
class DataSource(Protocol):
    """统一数据源协议，所有数据源实现必须满足此接口。"""

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        ...

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        ...

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        ...

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        ...

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        ...

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        ...

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        ...

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        ...

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        ...

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        ...

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        ...

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        ...


class TushareDataSource:
    """Tushare Pro API 数据源封装。"""

    def __init__(self, token: str | None = None) -> None:
        self._client = TushareClient(token)

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        return "tushare"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        return self._client.check_connection()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return self._client.get_daily(ts_code, start_date, end_date)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return self._client.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return self._client.get_realtime_quote(ts_codes)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return self._client.get_moneyflow(ts_code, trade_date)

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        if self._client._pro is None:
            return None
        try:
            return self._client._pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except (requests.RequestException, ValueError, KeyError) as e:
            # 窄化：仅捕获 HTTP / 数据解析异常，返回 None 让上层回退
            logger.warning("[datasource] TushareDataSource.get_daily_basic 失败 %s: %s", ts_code, e)
            return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        if self._client._pro is None:
            return None
        try:
            return self._client._pro.stk_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except (requests.RequestException, ValueError, KeyError) as e:
            # 窄化：仅捕获 HTTP / 数据解析异常，返回 None 让上层回退
            logger.warning("[datasource] TushareDataSource.get_stk_factor 失败 %s: %s", ts_code, e)
            return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return self._client.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return self._client.get_trade_cal(exchange, start_date, end_date)

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
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
        """获取 K 线 dict 列表（含缓存与回退）"""
        df = self.get_daily(ts_code, start_date, end_date)
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        records.sort(key=lambda x: x.get("trade_date", ""))
        if not start_date and days > 0:
            records = records[-days:]
        return records


class IndevsDataSource:
    """Indevs Tushare Replay API 数据源封装。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._client = IndevsClient(api_key, base_url)

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        return "indevs"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        return self._client.health_check()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return self._client.get_daily(ts_code, start_date, end_date)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return self._client.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return self._client.get_realtime_quote(ts_codes)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return self._client.get_moneyflow(ts_code, trade_date)

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        return self._client.get_daily_basic(ts_code, start_date, end_date)

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        return self._client.get_stk_factor(ts_code, start_date, end_date)

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return self._client.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return self._client.get_trade_cal(exchange, start_date, end_date)

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        return self._client.get_stock_list(exchange)

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        return self._client.get_kline_dicts(ts_code, days, start_date, end_date)


class AStockDataDataSource:
    """A-Stock-Data 免费数据源封装（无需 API Key）。

    数据源映射：
      - 实时行情 -> 腾讯财经
      - 日K线    -> 百度股市通
      - 股票基础信息 -> 东财 push2
      - 资金流向  -> 东财 push2
      - 每日基础指标 -> 腾讯财经
    """

    def __init__(self) -> None:
        self._client = AStockDataClient()

    @property
    def name(self) -> str:
        """数据源标识名"""
        return "a-stock-data"

    def health_check(self) -> bool:
        """检查数据源连通性"""
        return self._client.health_check()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return self._client.get_daily(ts_code, start_date, end_date)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return self._client.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照"""
        return self._client.get_realtime_quote(ts_codes)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向"""
        return self._client.get_moneyflow(ts_code, trade_date)

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标"""
        return self._client.get_daily_basic(ts_code, start_date, end_date)

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（a-stock-data 不支持，返回 None）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息"""
        return self._client.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（a-stock-data 不支持，返回 None）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（a-stock-data 不提供全量列表）"""
        return []

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表"""
        return self._client.get_kline_dicts(ts_code, days, start_date, end_date)


class BridgeDataSource:
    """Tushare Data Bridge HTTP API 数据源封装。

    支持传入实例级 ``BridgeConfig``，不会修改全局 bridge 配置。
    若未传 config，则使用当前全局配置。
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        return "bridge"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        return is_bridge_available(self._config)

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        return get_all_stocks_bridge_first(exchange, config=self._config)

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        return get_daily_klines(ts_code, days=days, start_date=start_date, end_date=end_date, config=self._config)


class HithinkFinanceDataSource:
    """同花顺金融数据服务（hithink-finance）官方数据源封装。

    配置 ``HITHINK_FINANCE_API_KEY`` 后启用；auto 模式下作为最优先数据源。
    数据映射：
      - 日K线（个股/指数） -> /api/a-share[-index]/prices/historical
      - 实时行情           -> /api/a-share/prices/snapshot + valuations/snapshot 合并
      - 股票基础信息       -> /api/meta/tickers/search|list
      - 交易日历           -> /api/a-share/calendar/trading-days
      - 资金流向 / 技术因子 -> 上游不提供，返回 None 由调用方回退其他数据源
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._client = HithinkFinanceClient(api_key, base_url)

    @property
    def name(self) -> str:
        """数据源标识名"""
        return "hithink"

    @property
    def is_configured(self) -> bool:
        """是否已配置 API Key"""
        return self._client.is_configured

    def health_check(self) -> bool:
        """检查数据源连通性"""
        return self._client.health_check()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return self._client.get_daily(ts_code, start_date, end_date)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return self._client.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照"""
        return self._client.get_realtime_quote(ts_codes)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（hithink 不提供，返回 None）"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标"""
        return self._client.get_daily_basic(ts_code, start_date, end_date)

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（hithink 不提供，返回 None）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息"""
        return self._client.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历"""
        return self._client.get_trade_cal(exchange, start_date, end_date)

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表"""
        return self._client.get_stock_list(exchange)

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表"""
        return self._client.get_kline_dicts(ts_code, days, start_date, end_date)


class SqliteDataSource:
    """本地 SQLite 数据源封装。"""

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        return "sqlite"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        try:
            with get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except (sqlite3.Error, OSError) as e:
            # 窄化：仅捕获 DB / OS 异常，健康检查返回 False 让上层选择其他源
            logger.warning("[datasource] SqliteDataSource.health_check 失败: %s", e)
            return False

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        with get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT ts_code, name, industry, market FROM stock_basic"
            params: list = []
            if exchange:
                sql += " WHERE exchange = ?"
                params.append(exchange)
            sql += " ORDER BY ts_code"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        with get_connection() as conn:
            # sqlite3.Row 构造开销大，批量逐股调用场景下用裸元组 + zip 转 dict 更快
            conn.row_factory = None
            return read_kline_rows(
                ts_code,
                conn=conn,
                limit=resolve_kline_limit(days, start_date),
                start_date=start_date,
                end_date=end_date,
            )

    def get_kline_dicts_batch(
        self,
        ts_codes: list[str],
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, list[dict]]:
        """批量获取多只股票的 K 线：共享一个连接逐股查询，省去逐股开关连接的开销。

        每只股票的 SQL 与 get_kline_dicts 完全一致（行为不变），只是复用连接。
        返回 {ts_code: [K 线 dict 升序]}，无数据的股票对应空列表。
        """
        result: dict[str, list[dict]] = {code: [] for code in ts_codes}
        if not ts_codes:
            return result
        with get_connection() as conn:
            # sqlite3.Row 构造开销大，批量场景下用裸元组 + zip 转 dict 更快
            conn.row_factory = None
            # 单条 IN 查询替代 N+1 次逐股 SELECT，语义与原逐股查询一致：
            #   每只股票按 trade_date DESC 取最近 days 条（无 start_date 时），
            #   含日期区间过滤；Python 端按 ts_code 分组 + 截断 + 反转为升序。
            return read_kline_rows_batch(
                ts_codes,
                conn=conn,
                days=days,
                start_date=start_date,
                end_date=end_date,
            )


class CompositeDataSource:
    """组合数据源：按配置优先级自动回退。

    默认优先级（preferred="auto"），按环境变量 token 感知：
      - 配置了 HITHINK_FINANCE_API_KEY -> hithink（同花顺官方）最优先
      - 否则配置了 INDEVS_API_KEY -> indevs
      - 否则 JNB 模式（DATA_MODE=jnb）配置了 TUSHARE_TOKEN -> tushare 优先
      - 然后 a-stock-data（免费）-> bridge -> SQLite 依次兜底

    说明：websearch 模式下 TushareClient._pro=None（无数据后端），即使配置了
    TUSHARE_TOKEN 也不路由 tushare，直接走 a-stock-data——这正是父版本行为，
    避免「有 token 老用户」被路由到不可用的 tushare 后崩溃或静默 0 行。
    hithink 同理自带 is_configured 探测：未配置 Key 时不进入优先链，
    其取数方法返回 None 时由回退链自动落到下一源。

    即：配置了同花顺 Key 的用户默认走官方数据；零配置新用户默认 a-stock-data
    （腾讯/百度/东财等免费公开接口，无需 API Key）；已配置其他 token 的老用户
    行为不变，不会被静默切换。
    """

    VALID_PREFERRED = ("auto", "hithink", "tushare", "indevs", "bridge", "sqlite", "a-stock-data")

    def __init__(self, preferred: str = "auto") -> None:
        if preferred not in self.VALID_PREFERRED:
            raise ZettarancError(
                ErrorCode.INVALID_PARAM,
                f"不支持的数据源: {preferred}，仅支持 {' / '.join(self.VALID_PREFERRED)}",
            )
        self._preferred = preferred
        self._bridge = BridgeDataSource()
        self._sqlite = SqliteDataSource()
        self._tushare: TushareDataSource | None = None
        self._indevs: IndevsDataSource | None = None
        self._a_stock_data: AStockDataDataSource | None = None
        self._hithink: HithinkFinanceDataSource | None = None

    @property
    def _tushare_source(self) -> TushareDataSource:
        if self._tushare is None:
            self._tushare = TushareDataSource()
        return self._tushare

    @property
    def _indevs_source(self) -> IndevsDataSource:
        if self._indevs is None:
            self._indevs = IndevsDataSource()
        return self._indevs

    @property
    def _a_stock_data_source(self) -> AStockDataDataSource:
        if self._a_stock_data is None:
            self._a_stock_data = AStockDataDataSource()
        return self._a_stock_data

    @property
    def _hithink_source(self) -> HithinkFinanceDataSource:
        if self._hithink is None:
            self._hithink = HithinkFinanceDataSource()
        return self._hithink

    def _preferred_token_source(self) -> DataSource | None:
        """按统一决议返回 auto 模式的优先数据源。

        决议规则集中在 :mod:`modules.datasource_resolution` —— 读路径（这里）与
        写路径（``DataSyncer``）共用同一份判断，不会再各自漂移。

        零配置返回 None（由调用方回退 a-stock-data）。
        """
        resolution = resolve_provider()
        if resolution.provider == "hithink":
            return self._hithink_source
        if resolution.provider == "indevs":
            return self._indevs_source
        if resolution.provider == "tushare":
            try:
                return self._tushare_source
            except ZettarancError as e:
                # JNB 配置不完整（缺 TUSHARE_API_URL 等）：回退免费源而非崩溃
                logger.warning("[datasource] tushare 配置不完整(%s)，回退 a-stock-data", e)
                return None
        return None

    def _auto_sources(self) -> list[DataSource]:
        """auto 模式的完整优先级链：优先源（如有）-> a-stock-data -> bridge -> sqlite。"""
        sources: list[DataSource] = []
        preferred = self._preferred_token_source()
        if preferred is not None:
            sources.append(preferred)
        sources.extend([self._a_stock_data_source, self._bridge, self._sqlite])
        return sources

    def _sources_for_preferred(self) -> list[DataSource]:
        """按 self._preferred 返回有序数据源列表；auto 复用 _auto_sources（token 感知）。"""
        p = self._preferred
        if p == "auto":
            return self._auto_sources()
        if p == "hithink":
            return [self._hithink_source, self._a_stock_data_source, self._indevs_source, self._bridge, self._sqlite]
        if p == "a-stock-data":
            return [self._a_stock_data_source, self._indevs_source, self._bridge, self._sqlite]
        if p == "bridge":
            return [self._bridge]
        if p == "sqlite":
            return [self._sqlite]
        if p == "tushare":
            return [self._tushare_source]
        if p == "indevs":
            return [self._indevs_source]
        return []

    def _auto_call(self, method: str, *args):
        """auto 模式按优先级链调用单项接口：先优先源（如有），失败后依次回退。

        与 _auto_sources 共用同一条链（a-stock-data -> bridge -> sqlite 兜底），
        返回首个非 None 结果；均失败时返回 None。
        """
        for source in self._auto_sources():
            try:
                result = getattr(source, method)(*args)
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
                AttributeError,
            ) as e:
                # 窄化：仅捕获 HTTP / DB / 数据解析 / 项目异常，回退到下一源
                logger.warning(
                    "[datasource] CompositeDataSource._auto_call(%s) 源 %s 失败: %s",
                    method,
                    getattr(source, "name", source.__class__.__name__),
                    e,
                )
                continue
            if result is not None:
                return result
        return None

    @property
    def name(self) -> str:
        """数据源标识名（tushare / bridge / sqlite / indevs / composite 之一）"""
        return f"composite({self._preferred})"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        if self._preferred == "bridge":
            return self._bridge.health_check()
        if self._preferred == "sqlite":
            return self._sqlite.health_check()
        if self._preferred == "tushare":
            return self._tushare_source.health_check()
        if self._preferred == "indevs":
            return self._indevs_source.health_check()
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.health_check()
        if self._preferred == "hithink":
            return self._hithink_source.health_check()
        # auto: 按 token 感知优先级链依次探测（hithink/indevs/tushare -> a-stock-data -> bridge -> sqlite），
        # 任一源探测异常（如 tushare 配置不完整）时记录并继续下一源，保持 bool 返回契约
        for source in self._auto_sources():
            try:
                if source.health_check():
                    return True
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
                AttributeError,
            ) as e:
                logger.warning(
                    "[datasource] CompositeDataSource.health_check 源 %s 失败: %s",
                    getattr(source, "name", source.__class__.__name__),
                    e,
                )
                continue
        return False

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        if self._preferred == "hithink":
            return self._hithink_source.get_daily(ts_code, start_date, end_date)
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_daily(ts_code, start_date, end_date)
        if self._preferred == "auto":
            # auto 模式：优先源（indevs/tushare，token 感知）-> a-stock-data 兜底
            return self._auto_call("get_daily", ts_code, start_date, end_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_daily(ts_code, start_date, end_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_daily(ts_code, start_date, end_date)
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        if self._preferred == "hithink":
            return self._hithink_source.get_index_daily(ts_code, start_date, end_date)
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_index_daily(ts_code, start_date, end_date)
        if self._preferred == "auto":
            return self._auto_call("get_index_daily", ts_code, start_date, end_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_index_daily(ts_code, start_date, end_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_index_daily(ts_code, start_date, end_date)
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        if self._preferred == "hithink":
            return self._hithink_source.get_realtime_quote(ts_codes)
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_realtime_quote(ts_codes)
        if self._preferred == "auto":
            return self._auto_call("get_realtime_quote", ts_codes)
        if self._preferred == "tushare":
            return self._tushare_source.get_realtime_quote(ts_codes)
        if self._preferred == "indevs":
            return self._indevs_source.get_realtime_quote(ts_codes)
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        if self._preferred == "hithink":
            return None  # hithink 不提供资金流向
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_moneyflow(ts_code, trade_date)
        if self._preferred == "auto":
            return self._auto_call("get_moneyflow", ts_code, trade_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_moneyflow(ts_code, trade_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_moneyflow(ts_code, trade_date)
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        if self._preferred == "hithink":
            return self._hithink_source.get_daily_basic(ts_code, start_date, end_date)
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_daily_basic(ts_code, start_date, end_date)
        if self._preferred == "auto":
            return self._auto_call("get_daily_basic", ts_code, start_date, end_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_daily_basic(ts_code, start_date, end_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_daily_basic(ts_code, start_date, end_date)
        return None

    def get_stk_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股技术因子（动量 / 量价等）"""
        if self._preferred == "hithink":
            return None  # hithink 不提供技术因子
        if self._preferred == "a-stock-data":
            return None  # a-stock-data 不支持
        if self._preferred == "auto":
            # a-stock-data 不支持该接口，_auto_call 回退后仍返回 None
            return self._auto_call("get_stk_factor", ts_code, start_date, end_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_stk_factor(ts_code, start_date, end_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_stk_factor(ts_code, start_date, end_date)
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        if self._preferred == "hithink":
            return self._hithink_source.get_stock_basic(ts_code, name)
        if self._preferred == "a-stock-data":
            return self._a_stock_data_source.get_stock_basic(ts_code, name)
        if self._preferred == "auto":
            return self._auto_call("get_stock_basic", ts_code, name)
        if self._preferred == "tushare":
            return self._tushare_source.get_stock_basic(ts_code, name)
        if self._preferred == "indevs":
            return self._indevs_source.get_stock_basic(ts_code, name)
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        if self._preferred == "hithink":
            return self._hithink_source.get_trade_cal(exchange, start_date, end_date)
        if self._preferred == "a-stock-data":
            return None  # a-stock-data 不支持
        if self._preferred == "auto":
            # a-stock-data 不支持该接口，_auto_call 回退后仍返回 None
            return self._auto_call("get_trade_cal", exchange, start_date, end_date)
        if self._preferred == "tushare":
            return self._tushare_source.get_trade_cal(exchange, start_date, end_date)
        if self._preferred == "indevs":
            return self._indevs_source.get_trade_cal(exchange, start_date, end_date)
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        sources: list[DataSource] = self._sources_for_preferred()

        for source in sources:
            try:
                data = source.get_stock_list(exchange)
                if data:
                    return data
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
            ) as e:
                # 窄化：仅捕获 HTTP / DB / 数据解析 / 项目异常，回退到下一源
                logger.warning(
                    "[datasource] CompositeDataSource.get_stock_list 源 %s 失败: %s",
                    getattr(source, "name", source.__class__.__name__),
                    e,
                )
                continue
        return []

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线数据，优先从 DB 读取，DB 没有时调 API 并缓存"""
        # 1. 先查 DB（与 SqliteDataSource 走同一条 SQL——此前这里是逐字副本）
        with get_connection() as conn:
            # sqlite3.Row 构造开销大，批量逐股调用场景下用裸元组 + zip 转 dict 更快
            conn.row_factory = None
            # 与 TushareDataSource / SqliteDataSource 对齐：只要未指定 start_date，
            # 就按 days 截断最近 N 天（即使指定了 end_date），避免拉取全历史
            records = read_kline_rows(
                ts_code,
                conn=conn,
                limit=resolve_kline_limit(days, start_date),
                start_date=start_date,
                end_date=end_date,
            )

        if records:
            # DB 有数据，直接返回（helper 已按 trade_date 升序返回）
            return records

        # 2. DB 没有数据，调 API
        sources: list[DataSource] = self._sources_for_preferred()

        for source in sources:
            try:
                data = source.get_kline_dicts(ts_code, days=days, start_date=start_date, end_date=end_date)
                if data:
                    # 3. 写入 DB 缓存
                    save_klines(data)
                    return data
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
            ) as e:
                # 窄化：仅捕获 HTTP / DB / 数据解析 / 项目异常，回退到下一源
                logger.warning(
                    "[datasource] CompositeDataSource.get_kline_dicts 源 %s 失败 %s: %s",
                    getattr(source, "name", source.__class__.__name__),
                    ts_code,
                    e,
                )
                continue
        return []

    def get_kline_dicts_batch(
        self,
        ts_codes: list[str],
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, list[dict]]:
        """批量获取多只股票的 K 线：DB 共享连接批量查询优先，缺失的股票逐只回退外部源。

        返回 {ts_code: [K 线 dict 升序]}，无数据的股票对应空列表。
        """
        result = self._sqlite.get_kline_dicts_batch(ts_codes, days=days, start_date=start_date, end_date=end_date)
        # DB 缺失的股票走单股回退路径（含 save_klines 缓存写回）
        for code in ts_codes:
            if not result.get(code):
                result[code] = self.get_kline_dicts(code, days=days, start_date=start_date, end_date=end_date)
        return result


# ---------------------------------------------------------------------------
# dict ↔ DailyData 转换工具
# ---------------------------------------------------------------------------


def dict_to_daily(klines: list[dict] | list) -> list:
    """将 dict 格式 K 线列表转换为 ``DailyData`` 列表。

    若输入已是 ``DailyData`` 列表则直接返回副本。
    同时映射基础字段与派生形态字段（is_rise / is_beidou 等），
    供 strategies / screener / portfolio_diagnosis 等模块统一使用。
    """
    from .indicators import DailyData

    if not klines:
        return []
    if isinstance(klines[0], DailyData):
        return list(klines)

    result = []
    for i, row in enumerate(klines):
        prev_close = float(klines[i - 1]["close"]) if i > 0 else float(row["close"])
        close = float(row["close"])
        vol = float(row["vol"])
        prev_vol = float(klines[i - 1]["vol"]) if i > 0 else vol
        result.append(
            DailyData(
                ts_code=str(row["ts_code"]),
                trade_date=str(row["trade_date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=close,
                vol=vol,
                amount=float(row.get("amount", close * vol)),
                pct_chg=float(row.get("pct_chg", 0.0)),
                prev_close=prev_close,
                is_rise=row.get("is_rise", close > prev_close),
                is_beidou=row.get("is_beidou", vol >= prev_vol * 2 if prev_vol > 0 else False),
                is_suoliang=row.get("is_suoliang", vol <= prev_vol * 0.5 if prev_vol > 0 else False),
                is_jiayin=row.get("is_jiayin", close < float(row["open"]) and close > prev_close),
                is_yinxian=row.get("is_yinxian", close < prev_close),
                is_fangliang_yinxian=row.get(
                    "is_fangliang_yinxian",
                    close < prev_close and vol > prev_vol * 1.5 if prev_vol > 0 else False,
                ),
            )
        )
    return result


def daily_to_dict(klines: list) -> list[dict]:
    """将 ``DailyData`` 列表转为符合战法检测需要的 dict 格式列表。

    自动计算派生字段：prev_close / prev_vol / is_rise / is_beidou /
    is_suoliang / is_jiayin / is_yinxian / is_fangliang_yinxian。
    """
    result = []
    for i, k in enumerate(klines):
        prev_close = klines[i - 1].close if i > 0 else k.close
        prev_vol = klines[i - 1].vol if i > 0 else k.vol

        result.append(
            {
                "ts_code": k.ts_code,
                "trade_date": k.trade_date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "vol": k.vol,
                "amount": k.amount,
                "pct_chg": k.pct_chg,
                "prev_close": prev_close,
                "prev_vol": prev_vol,
                "is_rise": k.close > prev_close,
                "is_beidou": k.vol >= prev_vol * 2 if prev_vol > 0 else False,
                "is_suoliang": k.vol <= prev_vol * 0.5 if prev_vol > 0 else False,
                "is_jiayin": k.close < k.open and k.close > prev_close,
                "is_yinxian": k.close < prev_close,
                "is_fangliang_yinxian": k.close < prev_close and k.vol > prev_vol * 1.5 if prev_vol > 0 else False,
            }
        )
    return result


def get_datasource(preferred: str = "auto") -> DataSource:
    """数据源工厂函数。

    preferred="auto" 时默认使用 CompositeDataSource，优先级（token 感知）：
    hithink（配置 HITHINK_FINANCE_API_KEY，同花顺官方）-> indevs（配置 INDEVS_API_KEY）
    -> tushare（配置 TUSHARE_TOKEN）-> a-stock-data（免费）-> bridge -> sqlite
    """
    if preferred == "tushare":
        return TushareDataSource()
    if preferred == "bridge":
        return BridgeDataSource()
    if preferred == "sqlite":
        return SqliteDataSource()
    if preferred == "indevs":
        return IndevsDataSource()
    if preferred == "a-stock-data":
        return AStockDataDataSource()
    if preferred == "hithink":
        return HithinkFinanceDataSource()
    return CompositeDataSource("auto")
