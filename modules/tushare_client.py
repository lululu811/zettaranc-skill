"""
Tushare 中转 API 客户端
支持 Tushare SDK 方式调用中转 API

中转服务文档: http://tsy.xiaodefa.cn/docs.html
"""

import os
import time
import logging
from typing import Optional, List
from pathlib import Path

try:
    import requests
    import pandas as pd
    import tushare as ts
    from dotenv import load_dotenv
except ImportError:
    print("请先安装依赖: pip install requests pandas python-dotenv tushare")

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path, override=True)

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

    def __init__(self, token: Optional[str] = None):
        self.token = token or TUSHARE_TOKEN
        if not self.token:
            raise ValueError("未设置 TUSHARE_TOKEN，请检查 .env 文件")

        ts.set_token(self.token)
        self._pro = ts.pro_api()
        self._pro._DataApi__http_url = TUSHARE_API_URL

        try:
            from tushare.stock import cons as ct
            ct.verify_token_url = VERIFY_TOKEN_URL
        except Exception:
            pass

        self.min_request_interval = 0.55
        self.last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取日线行情（个股）"""
        self._rate_limit()
        try:
            return self._pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"get_daily 失败: {e}")
            return pd.DataFrame()

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取指数日线（如沪深300）"""
        self._rate_limit()
        try:
            return self._pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"get_index_daily 失败: {e}")
            return pd.DataFrame()

    def get_realtime_quote(self, ts_codes: List[str]) -> Optional[pd.DataFrame]:
        """获取 A 股实时行情"""
        self._rate_limit()
        try:
            ts_code_str = ",".join(ts_codes)
            return ts.realtime_quote(ts_code=ts_code_str)
        except Exception as e:
            logger.error(f"get_realtime_quote 失败: {e}")
            return pd.DataFrame()

    def get_moneyflow(self, ts_code: str, trade_date: str) -> Optional[pd.DataFrame]:
        """获取个股资金流向"""
        self._rate_limit()
        try:
            return self._pro.moneyflow(ts_code=ts_code, trade_date=trade_date)
        except Exception as e:
            logger.error(f"get_moneyflow 失败: {e}")
            return pd.DataFrame()

    def get_stock_basic(self, ts_code: Optional[str] = None,
                        name: Optional[str] = None) -> Optional[pd.DataFrame]:
        """获取股票基本信息"""
        self._rate_limit()
        try:
            params = {"list_status": "L"}
            if ts_code:
                params["ts_code"] = ts_code
            if name:
                params["name"] = name
            return self._pro.stock_basic(**params)
        except Exception as e:
            logger.error(f"get_stock_basic 失败: {e}")
            return pd.DataFrame()

    def get_limit_list(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取涨跌停列表"""
        self._rate_limit()
        try:
            return self._pro.limit_list_d(trade_date=trade_date)
        except Exception as e:
            logger.error(f"get_limit_list 失败: {e}")
            return pd.DataFrame()

    def get_top_list(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取龙虎榜数据"""
        self._rate_limit()
        try:
            return self._pro.top_list(trade_date=trade_date)
        except Exception as e:
            logger.error(f"get_top_list 失败: {e}")
            return pd.DataFrame()

    def get_financial_data(self, ts_code: str, start_date: str,
                            end_date: str) -> Optional[pd.DataFrame]:
        """获取财务指标"""
        self._rate_limit()
        try:
            return self._pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"get_financial_data 失败: {e}")
            return pd.DataFrame()

    def get_trade_cal(self, exchange: str = "SSE",
                       start_date: str = "", end_date: str = "") -> Optional[pd.DataFrame]:
        """获取交易日历"""
        self._rate_limit()
        try:
            params = {"exchange": exchange}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            return self._pro.trade_cal(**params)
        except Exception as e:
            logger.error(f"get_trade_cal 失败: {e}")
            return pd.DataFrame()

    def check_connection(self) -> bool:
        """检查 API 连通性"""
        df = self.get_daily("000001.SZ", "20250508", "20250515")
        return df is not None and len(df) > 0


# 测试
if __name__ == "__main__":
    import sys, io
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
        print(df[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].to_string(index=False))
    else:
        print("无数据")

    print("\n=== 沪深300 (000300.SH) 指数日线 ===")
    df2 = client.get_index_daily("000300.SH", "20250508", "20250515")
    if df2 is not None and len(df2) > 0:
        print(df2[['trade_date', 'open', 'high', 'low', 'close', 'pct_chg']].to_string(index=False))
    else:
        print("无数据")

    print("\n=== 实时行情 ===")
    df3 = client.get_realtime_quote(["000300.SH", "000001.SZ"])
    if df3 is not None and len(df3) > 0:
        print(df3[['TS_CODE', 'NAME', 'PRICE', 'HIGH', 'LOW', 'VOLUME']].to_string(index=False))
    else:
        print("无数据")
