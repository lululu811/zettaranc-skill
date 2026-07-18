#!/usr/bin/env python3
"""
统一错误码与异常基类（v3.10.4 最小版）

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
