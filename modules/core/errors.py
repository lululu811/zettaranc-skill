#!/usr/bin/env python3
"""
统一错误码与异常基类（v3.10.4）

设计约束：
- 继承 ValueError，向后兼容现有 `except ValueError` / `pytest.raises(ValueError)` 调用点
- 消息统一格式：[ERROR_CODE] 人类可读描述
- 最小骨架：当前仅试点 tushare_client / datasource / cli 顶层，其余模块后续版本接入
"""

from enum import Enum


class ErrorCode(str, Enum):
    """统一错误码"""

    CONFIG_MISSING = "CONFIG_MISSING"  # 配置缺失（Token / API 地址未配置）
    DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"  # 数据源调用失败
    RATE_LIMIT = "RATE_LIMIT"  # 触发限流
    DB_ERROR = "DB_ERROR"  # 数据库读写失败
    INVALID_PARAM = "INVALID_PARAM"  # 参数非法

    # indevs_client (v3.10.4)
    INDEVS_NO_DATA = "INDEVS_NO_DATA"  # Indevs 返回数据为空 / 数据源未配置

    # llm_providers (v3.10.4)
    LLM_TIMEOUT = "LLM_TIMEOUT"  # LLM 请求超时
    LLM_API_ERROR = "LLM_API_ERROR"  # LLM API 返回非 2xx / 解析失败
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"  # LLM 返回结构异常

    # screener (v3.10.4)
    SCREENER_NO_DATA = "SCREENER_NO_DATA"  # 选股数据不足（klines 为空 / 股票池为空）
    SCREENER_INVALID_CRITERIA = "SCREENER_INVALID_CRITERIA"  # 未注册的 criteria

    # simulator (v3.10.4)
    SIMULATOR_INVALID_PRICE = "SIMULATOR_INVALID_PRICE"  # 模拟器价格非法（<= 0）
    SIMULATOR_NO_KLINES = "SIMULATOR_NO_KLINES"  # 模拟器无 K 线数据

    # backtest (v3.10.4)
    BACKTEST_INVALID_CONFIG = "BACKTEST_INVALID_CONFIG"  # 回测配置非法
    BACKTEST_EMPTY_KLINES = "BACKTEST_EMPTY_KLINES"  # 回测 K 线数据为空


class ZettarancError(ValueError):
    """项目统一异常基类

    继承 ValueError 以兼容存量 `except ValueError` 代码；
    str(exc) 输出统一格式：[ERROR_CODE] message
    """

    def __init__(self, code: ErrorCode, message: str, *, cause: Exception | None = None):
        self.code = code
        self.message = message
        self.cause = cause
        super().__init__(f"[{self.code.value}] {self.message}")

    def to_dict(self) -> dict[str, str | None]:
        """结构化输出，供 CLI --json / Web API 使用"""
        return {
            "error_code": self.code.value,
            "message": self.message,
            "cause": repr(self.cause) if self.cause else None,
        }


if __name__ == "__main__":
    err = ZettarancError(ErrorCode.CONFIG_MISSING, "未设置 TUSHARE_TOKEN")
    print(str(err))
    print(err.to_dict())
