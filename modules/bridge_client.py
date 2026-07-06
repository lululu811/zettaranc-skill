"""
Tushare Data Bridge 客户端
封装 bridge HTTP API，提供降级网关：bridge 不通时回退到本地 SQLite
"""

import os
import json
import urllib.request
import urllib.error
from typing import Any, Optional
from dataclasses import dataclass


# Bridge 默认配置（可通过环境变量覆盖）
_BRIDGE_HOST = os.getenv("TUSHARE_BRIDGE_HOST", "127.0.0.1")
_BRIDGE_PORT = int(os.getenv("TUSHARE_BRIDGE_PORT", "8765"))
_BRIDGE_TIMEOUT = int(os.getenv("TUSHARE_BRIDGE_TIMEOUT", "10"))
_BRIDGE_ENABLED = os.getenv("TUSHARE_BRIDGE_ENABLED", "auto").lower()


@dataclass(frozen=True)
class BridgeConfig:
    """Bridge 连接配置"""

    host: str = _BRIDGE_HOST
    port: int = _BRIDGE_PORT
    timeout: int = _BRIDGE_TIMEOUT
    enabled: str = _BRIDGE_ENABLED  # "auto" | "always" | "never"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


# 全局配置实例（可通过环境变量覆盖后重新初始化）
_bridge_config = BridgeConfig()


def get_bridge_config() -> BridgeConfig:
    """获取当前 bridge 配置"""
    return _bridge_config


def set_bridge_config(**kwargs) -> None:
    """动态更新 bridge 配置（用于测试）"""
    global _bridge_config
    current = _bridge_config
    _bridge_config = BridgeConfig(
        host=kwargs.get("host", current.host),
        port=kwargs.get("port", current.port),
        timeout=kwargs.get("timeout", current.timeout),
        enabled=kwargs.get("enabled", current.enabled),
    )


# ========== 低层 HTTP 调用 ==========


def _http_get(path: str, params: dict[str, str] | None = None, config: BridgeConfig | None = None) -> dict:
    """发送 GET 请求到 bridge"""
    cfg = config or get_bridge_config()
    url = f"{cfg.base_url}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{query}"

    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")

    with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(path: str, body: dict, config: BridgeConfig | None = None) -> dict:
    """发送 POST 请求到 bridge"""
    cfg = config or get_bridge_config()
    url = f"{cfg.base_url}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ========== 健康检查 ==========


def is_bridge_available(config: BridgeConfig | None = None) -> bool:
    """
    检查 bridge HTTP API 是否可用

    Args:
        config: 可选的实例级配置；为空时使用全局配置。
    """
    cfg = config or get_bridge_config()
    if cfg.enabled == "never":
        return False
    if cfg.enabled == "always":
        # 即使 health 失败也认为可用（可能只是 health 端点问题）
        return True

    try:
        resp = _http_get("/health", config=cfg)
        return resp.get("status") == "ok"
    except Exception:
        return False


# ========== 数据查询接口 ==========


def get_bridge_daily(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 60,
    config: BridgeConfig | None = None,
) -> list[dict]:
    """
    从 bridge 获取日线数据

    Args:
        ts_code: 股票代码
        start_date: 起始日期 YYYYMMDD（可选）
        end_date: 结束日期 YYYYMMDD（可选）
        days: 如果没有 start_date，则取最近 N 天
        config: 可选的实例级配置；为空时使用全局配置。

    Returns:
        list[dict] 日线数据，按 trade_date 升序排列
        空列表表示无数据或 bridge 不可用
    """
    if not is_bridge_available(config):
        return []

    # 构造查询参数
    params: dict[str, str] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        resp = _http_get(f"/daily/{ts_code}", params, config=config)
        data = resp.get("data", [])

        # 按日期升序排列（bridge 默认 DESC）
        data.sort(key=lambda x: x.get("trade_date", ""))

        # 如果指定了 days 但没有 start_date，截取最近 N 天
        if not start_date and days > 0:
            data = data[-days:]

        return data
    except Exception:
        return []


def get_bridge_stock_list(exchange: str | None = None, config: BridgeConfig | None = None) -> list[dict]:
    """
    从 bridge 获取股票列表

    Args:
        exchange: 交易所筛选（可选）
        config: 可选的实例级配置；为空时使用全局配置。

    Returns:
        list[dict] 股票基本信息
    """
    if not is_bridge_available(config):
        return []

    params: dict[str, str] = {}
    if exchange:
        params["exchange"] = exchange

    try:
        resp = _http_get("/stocks", params, config=config)
        return resp.get("stocks", [])
    except Exception:
        return []


def query_bridge_local(
    table_name: str,
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    通过 bridge 查询本地数据库表

    Args:
        table_name: 表名
        columns: 列名列表
        where: WHERE 条件
        order_by: ORDER BY
        limit: LIMIT

    Returns:
        list[dict] 查询结果
    """
    if not is_bridge_available():
        return []

    body: dict[str, Any] = {"table_name": table_name}
    if columns:
        body["columns"] = columns
    if where:
        body["where"] = where
    if order_by:
        body["order_by"] = order_by
    if limit:
        body["limit"] = limit

    try:
        resp = _http_post("/query/local", body)
        return resp.get("data", [])
    except Exception:
        return []


def query_bridge_sql(sql: str) -> list[dict]:
    """
    通过 bridge 执行原始 SQL

    Args:
        sql: SQL 查询语句

    Returns:
        list[dict] 查询结果
    """
    if not is_bridge_available():
        return []

    try:
        resp = _http_post("/query/sql", {"sql": sql})
        return resp.get("data", [])
    except Exception:
        return []


# ========== 降级网关：优先 bridge，失败回退本地 ==========


def get_daily_klines(
    ts_code: str,
    days: int = 60,
    start_date: str | None = None,
    end_date: str | None = None,
    config: BridgeConfig | None = None,
) -> list[dict]:
    """
    获取日线 K 线（统一入口）

    策略：
    1. 如果 bridge 可用，优先从 bridge 获取
    2. 如果 bridge 返回空或失败，回退到本地 SQLite
    3. 如果 bridge 被禁用（enabled=never），直接走本地

    Args:
        config: 可选的实例级配置；为空时使用全局配置。

    Returns:
        list[dict] 日线数据，按 trade_date 升序
    """
    # 尝试 bridge
    bridge_data = get_bridge_daily(ts_code, start_date, end_date, days, config=config)
    if bridge_data:
        return bridge_data

    # 降级到本地 SQLite
    return _get_local_daily(ts_code, days, start_date, end_date)


def get_all_stocks_bridge_first(
    exchange: str | None = None,
    config: BridgeConfig | None = None,
) -> list[dict]:
    """
    获取所有股票列表（统一入口）

    策略同 get_daily_klines：bridge 优先，失败回退本地

    Args:
        config: 可选的实例级配置；为空时使用全局配置。
    """
    bridge_data = get_bridge_stock_list(exchange, config=config)
    if bridge_data:
        return bridge_data

    return _get_local_stock_list(exchange)


# ========== 本地回退实现 ==========


def _get_local_daily(
    ts_code: str,
    days: int = 60,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """从本地 SQLite 获取日线数据"""
    from .database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    params: list = [ts_code]
    sql = """
        SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
        FROM daily_kline
        WHERE ts_code = ?
    """

    if start_date:
        sql += " AND trade_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND trade_date <= ?"
        params.append(end_date)

    sql += " ORDER BY trade_date DESC"
    if not start_date and days > 0:
        sql += " LIMIT ?"
        params.append(days)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    # 转为升序
    return [dict(row) for row in reversed(rows)]


def _get_local_stock_list(exchange: str | None = None) -> list[dict]:
    """从本地 SQLite 获取股票列表"""
    from .database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    sql = "SELECT ts_code, name, industry, market FROM stock_basic"
    params: list = []

    if exchange:
        sql += " WHERE exchange = ?"
        params.append(exchange)

    sql += " ORDER BY ts_code"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ========== 命令行测试 ==========

if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "health":
        print(f"Bridge at {_bridge_config.base_url}: {'available' if is_bridge_available() else 'unavailable'}")
    elif len(sys.argv) > 2 and sys.argv[1] == "daily":
        data = get_daily_klines(sys.argv[2], days=5)
        print(f"Got {len(data)} rows for {sys.argv[2]}")
        for row in data[-3:]:
            print(f"  {row['trade_date']}: close={row['close']}, vol={row['vol']}")
    else:
        print("Usage: python -m modules.bridge_client health")
        print("       python -m modules.bridge_client daily <ts_code>")
