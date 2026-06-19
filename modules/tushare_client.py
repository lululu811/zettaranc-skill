"""
Tushare 中转 API 客户端
支持 Tushare SDK 方式调用中转 API

中转服务文档: http://tsy.xiaodefa.cn/docs.html
"""

import os
import time
import logging
from typing import Optional

try:
    import requests  # noqa: F401  可用性检查
    import pandas as pd
    import tushare as ts
except ImportError:
    print("请先安装依赖: pip install requests pandas python-dotenv tushare")

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载，override=True）

logger = logging.getLogger(__name__)

TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "")
VERIFY_TOKEN_URL = os.environ.get("TUSHARE_VERIFY_TOKEN_URL", "")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")


class TushareClient:
    """Tushare 中转 SDK 客户端

    使用官方 Tushare SDK 配置中转 URL，支持：
    - get_daily: 个股日线
    - get_index_daily: 指数日线（如沪深300）
    - get_realtime_quote: 实时行情
    - get_moneyflow: 资金流向
    - get_stock_basic: 股票基本信息
    - get_limit_list: 涨跌停列表
    - get_top_list: 龙虎榜
    - get_financial_data: 财务指标
    - get_trade_cal: 交易日历
    """

    def __init__(self, token: str | None = None):
        self.token = token or TUSHARE_TOKEN
        data_mode = os.getenv("DATA_MODE", "websearch")

        # 仅在 JNB 模式下强制检查 API 配置
        if data_mode == "jnb":
            if not self.token:
                raise ValueError(
                    "JNB 模式下未设置 TUSHARE_TOKEN，请在 .env 中配置。\n或者将 DATA_MODE 改为 websearch。"
                )
            if not TUSHARE_API_URL:
                raise ValueError(
                    "JNB 模式下未设置 TUSHARE_API_URL，请在 .env 中配置中转 API 地址。\n"
                    "示例：TUSHARE_API_URL=https://tt.xiaodefa.cn"
                )

            # 初始化 Tushare SDK
            ts.set_token(self.token)
            self._pro = ts.pro_api()
            self._pro._DataApi__http_url = TUSHARE_API_URL
        else:
            self._pro = None

        try:
            from tushare.stock import cons as ct

            ct.verify_token_url = VERIFY_TOKEN_URL
        except Exception:
            pass

        self.min_request_interval = 0.55
        self.last_request_time = 0.0

    def _rate_limit(self, api_name: str = ""):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _call_api_with_retry(self, api_name: str, func, *args, **kwargs):
        """带退避算法和限流控制的 API 调用封装"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._rate_limit(api_name)
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"[{api_name}] 最终调用失败: {e}")
                    return None
                sleep_time = 2**attempt
                logger.warning(
                    f"[{api_name}] API 调用异常: {e}, 等待 {sleep_time} 秒后重试 ({attempt + 1}/{max_retries})"
                )
                time.sleep(sleep_time)

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取日线行情（个股，前复权）"""
        return self._call_api_with_retry(
            "get_daily",
            ts.pro_bar,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            adj="qfq",
            api=self._pro,
        )

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线（如沪深300）"""
        return self._call_api_with_retry(
            "get_index_daily", self._pro.index_daily, ts_code=ts_code, start_date=start_date, end_date=end_date
        )

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取 A 股实时行情"""
        ts_code_str = ",".join(ts_codes)
        return self._call_api_with_retry("get_realtime_quote", ts.realtime_quote, ts_code=ts_code_str)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向"""
        return self._call_api_with_retry("get_moneyflow", self._pro.moneyflow, ts_code=ts_code, trade_date=trade_date)

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基本信息"""
        params = {"list_status": "L"}
        if ts_code:
            params["ts_code"] = ts_code
        if name:
            params["name"] = name
        return self._call_api_with_retry("get_stock_basic", self._pro.stock_basic, **params)

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停列表"""
        return self._call_api_with_retry("get_limit_list", self._pro.limit_list_d, trade_date=trade_date)

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据"""
        return self._call_api_with_retry("get_top_list", self._pro.top_list, trade_date=trade_date)

    def get_financial_data(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取财务指标"""
        return self._call_api_with_retry(
            "get_financial_data", self._pro.fina_indicator, ts_code=ts_code, start_date=start_date, end_date=end_date
        )

    def get_trade_cal(self, exchange: str = "SSE", start_date: str = "", end_date: str = "") -> pd.DataFrame | None:
        """获取交易日历"""
        params = {"exchange": exchange}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._call_api_with_retry("get_trade_cal", self._pro.trade_cal, **params)

    def check_connection(self) -> bool:
        """检查 API 连通性"""
        df = self.get_daily("000001.SZ", "20250508", "20250515")
        return df is not None and len(df) > 0


# 测试
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO)

    client = TushareClient()
    print("=" * 50)
    print("Tushare 中转 API 连通性测试")
    print("=" * 50)

    if client.check_connection():
        print("[PASS] 连通性测试通过")
    else:
        print("[FAIL] 连通性测试失败")

    print("\n=== 平安银行 (000001.SZ) 日线 ===")
    df = client.get_daily("000001.SZ", "20250508", "20250515")
    if df is not None and len(df) > 0:
        print(df[["trade_date", "open", "high", "low", "close", "pct_chg"]].to_string(index=False))
    else:
        print("无数据")

    print("\n=== 沪深300 (000300.SH) 指数日线 ===")
    df2 = client.get_index_daily("000300.SH", "20250508", "20250515")
    if df2 is not None and len(df2) > 0:
        print(df2[["trade_date", "open", "high", "low", "close", "pct_chg"]].to_string(index=False))
    else:
        print("无数据")

    print("\n=== 实时行情 ===")
    df3 = client.get_realtime_quote(["000300.SH", "000001.SZ"])
    if df3 is not None and len(df3) > 0:
        print(df3[["TS_CODE", "NAME", "PRICE", "HIGH", "LOW", "VOLUME"]].to_string(index=False))
    else:
        print("无数据")
