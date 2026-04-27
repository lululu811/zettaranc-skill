"""
Tushare 中转 API 客户端封装
用于 Zettaranc Agent 获取实时股票数据

使用方法:
    from tushare_client import TushareClient
    client = TushareClient()
    df = client.get_daily('000001.SZ', start_date='20260101')
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    import tushare as ts
    from dotenv import load_dotenv
except ImportError:
    print("请先安装依赖: pip install tushare python-dotenv")

# 加载项目内的 .env
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# 中转 API 配置
TUSHARE_API_URL = "http://tsy.xiaodefa.cn"
VERIFY_TOKEN_URL = "http://tsy.xiaodefa.cn/dataapi/sdk-event"


class TushareClient:
    """Tushare 中转 API 客户端"""

    def __init__(self, token: Optional[str] = None):
        """
        初始化 Tushare 客户端

        Args:
            token: Tushare API Token，优先从环境变量 TUSHARE_TOKEN 读取
        """
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        if not self.token:
            raise ValueError("未设置 TUSHARE_TOKEN，请检查 .env 文件")

        # 初始化 Tushare
        ts.set_token(self.token)
        self.pro = ts.pro_api()
        self.pro._DataApi__http_url = TUSHARE_API_URL

        # 实时行情需要额外设置
        from tushare.stock import cons as ct
        ct.verify_token_url = VERIFY_TOKEN_URL

        # 限流控制
        self.min_request_interval = 60 / 120  # 120次/分钟
        self.last_request_time = 0

        logger.info(f"Tushare 客户端初始化完成，API 地址: {TUSHARE_API_URL}")

    def _rate_limit(self):
        """限流控制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def get_daily(self, ts_code: str, start_date: str, end_date: str,
                  fields: Optional[str] = None) -> Optional[Any]:
        """
        获取日线行情

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD
            fields: 返回字段，默认全部

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=fields
            )
            logger.info(f"获取日线数据成功: {ts_code}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取日线数据失败: {e}")
            return None

    def get_realtime_quote(self, ts_codes: List[str]) -> Optional[Any]:
        """
        获取 A股实时行情

        Args:
            ts_codes: 股票代码列表，如 ['600000.SH', '000001.SZ']

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            ts_code_str = ','.join(ts_codes)
            df = ts.realtime_quote(ts_code=ts_code_str)
            logger.info(f"获取实时行情成功: {ts_code_str}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> Optional[Any]:
        """
        获取个股资金流向

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.moneyflow(
                ts_code=ts_code,
                trade_date=trade_date
            )
            logger.info(f"获取资金流向成功: {ts_code}, {trade_date}")
            return df
        except Exception as e:
            logger.error(f"获取资金流向失败: {e}")
            return None

    def get_stock_basic(self, ts_code: Optional[str] = None,
                        name: Optional[str] = None) -> Optional[Any]:
        """
        获取股票基本信息

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            name: 股票名称

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.stock_basic(
                ts_code=ts_code,
                name=name,
                list_status='L'
            )
            logger.info(f"获取股票基本信息成功: {ts_code or name}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取股票基本信息失败: {e}")
            return None

    def get_float_market(self, ts_code: str) -> Optional[float]:
        """
        获取流通市值（亿元）

        Args:
            ts_code: 股票代码，如 '600519.SH'

        Returns:
            流通市值（亿元），获取失败返回 None
        """
        self._rate_limit()
        try:
            df = self.pro.stock_basic(
                ts_code=ts_code,
                fields='ts_code,float_market,total_market'
            )
            if df is not None and len(df) > 0:
                return float(df.iloc[0]['float_market'])
            return None
        except Exception as e:
            logger.error(f"获取流通市值失败: {e}")
            return None

    def get_financial_data(self, ts_code: str, start_date: str,
                            end_date: str) -> Optional[Any]:
        """
        获取财务报表（利润表、资产负债表、现金流量表）

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            start_date: 开始日期，格式 YYYYMMDD
            end_date: 结束日期，格式 YYYYMMDD

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.fina_indicator(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            logger.info(f"获取财务数据成功: {ts_code}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取财务数据失败: {e}")
            return None

    def get_limit_list(self, trade_date: str) -> Optional[Any]:
        """
        获取涨停股列表

        Args:
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.limit_list_d(trade_date=trade_date)
            logger.info(f"获取涨停列表成功: {trade_date}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取涨停列表失败: {e}")
            return None

    def get_top_list(self, trade_date: str) -> Optional[Any]:
        """
        获取龙虎榜数据

        Args:
            trade_date: 交易日期，格式 YYYYMMDD

        Returns:
            DataFrame 或 None
        """
        self._rate_limit()
        try:
            df = self.pro.top_list(trade_date=trade_date)
            logger.info(f"获取龙虎榜成功: {trade_date}, {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取龙虎榜失败: {e}")
            return None

    def check_connection(self) -> bool:
        """
        检查 API 连通性

        Returns:
            True 表示连接成功
        """
        try:
            # 尝试获取平安银行的日线数据
            df = self.get_daily('000001.SZ', start_date='20260401', end_date='20260410')
            return df is not None and len(df) > 0
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False


# 测试代码
if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    print("=" * 50)
    print("Tushare API 连通性测试")
    print("=" * 50)

    try:
        client = TushareClient()
        print("\n[PASS] 客户端初始化成功")

        if client.check_connection():
            print("[PASS] API 连通性测试通过")
        else:
            print("[FAIL] API 连通性测试失败")

        # 测试实时行情
        print("\n测试实时行情...")
        df_rt = client.get_realtime_quote(['600000.SH', '000001.SZ', '000002.SZ'])
        if df_rt is not None:
            print(f"[PASS] 实时行情获取成功，共 {len(df_rt)} 条")
            print(df_rt.head())

    except ValueError as e:
        print(f"\n[FAIL] 配置错误: {e}")
        print("请确保 .env 文件中已设置 TUSHARE_TOKEN")
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
