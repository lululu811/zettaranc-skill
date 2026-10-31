#!/usr/bin/env python3
"""
统一错误码与异常基类（v3.10.4）

设计约束：
- 继承 ValueError，向后兼容现有 `except ValueError` / `pytest.raises(ValueError)` 调用点
- 消息统一格式：[ERROR_CODE] 人类可读描述
- 最小骨架：当前仅试点 tushare_client / datasource / cli 顶层，其余模块后续版本接入
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """统一错误码"""

    CONFIG_MISSING = "CONFIG_MISSING"  # 配置缺失（Token / API 地址未配置）
    DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"  # 数据源调用失败
    RATE_LIMIT = "RATE_LIMIT"  # 触发限流
    DB_ERROR = "DB_ERROR"  # 数据库读写失败
    INVALID_PARAM = "INVALID_PARAM"  # 参数非法
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 未分类的内部错误（兜底，避免退化成无语义字符串）

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

    # M4: 全局 except Exception 收敛新增 (v4.0.3)
    COMMENTARY_FAILED = "COMMENTARY_FAILED"  # 评论生成失败
    TRADE_REVIEW_FAILED = "TRADE_REVIEW_FAILED"  # 交易复盘失败
    CONFIG_PARSE_FAILED = "CONFIG_PARSE_FAILED"  # 配置解析失败
    CLI_COMMAND_FAILED = "CLI_COMMAND_FAILED"  # CLI 命令执行失败
    INTENT_CHAT_FAILED = "INTENT_CHAT_FAILED"  # 意图聊天失败
    NOTIFIER_FAILED = "NOTIFIER_FAILED"  # 通知发送失败
    MONITOR_FAILED = "MONITOR_FAILED"  # 监控任务失败
    PORTFOLIO_DIAGNOSIS_FAILED = "PORTFOLIO_DIAGNOSIS_FAILED"  # 组合诊断失败
    SETUP_WIZARD_FAILED = "SETUP_WIZARD_FAILED"  # 向导初始化失败
    HARNESS_UPDATE_FAILED = "HARNESS_UPDATE_FAILED"  # harness 更新失败
    WATCHLIST_FAILED = "WATCHLIST_FAILED"  # 自选股处理失败
    CLI_TOPLEVEL_FAILED = "CLI_TOPLEVEL_FAILED"  # CLI 顶层入口失败
    INDEVS_REQUEST_FAILED = "INDEVS_REQUEST_FAILED"  # indevs 请求失败
    KNOWLEDGE_RETRIEVER_FAILED = "KNOWLEDGE_RETRIEVER_FAILED"  # 知识检索失败
    BRIDGE_CLIENT_FAILED = "BRIDGE_CLIENT_FAILED"  # bridge_client 操作失败
    IMPROVEMENT_LOGGER_FAILED = "IMPROVEMENT_LOGGER_FAILED"  # 改进日志失败
    BACKTEST_SIX_STEP_FAILED = "BACKTEST_SIX_STEP_FAILED"  # 六步回测失败
    TRADE_PARSER_FAILED = "TRADE_PARSER_FAILED"  # 成交解析失败
    SCREENER_CRITERIA_FAILED = "SCREENER_CRITERIA_FAILED"  # 选股 criteria 失败
    SCREENER_SCORING_FAILED = "SCREENER_SCORING_FAILED"  # 选股 scoring 失败
    SCREENER_ENGINE_FAILED = "SCREENER_ENGINE_FAILED"  # 选股 engine 失败
    KIRIN_DETECTOR_FAILED = "KIRIN_DETECTOR_FAILED"  # 麒麟检测失败
    DATA_LAYER_FAILED = "DATA_LAYER_FAILED"  # 数据层失败
    VERIFY_PIPELINE_FAILED = "VERIFY_PIPELINE_FAILED"  # verify pipeline 失败
    VERIFY_PORTFOLIO_WF_FAILED = "VERIFY_PORTFOLIO_WF_FAILED"  # 组合 walk forward 失败
    VERIFY_POOL_FAILED = "VERIFY_POOL_FAILED"  # verify pool 失败
    VERIFY_SCORER_FAILED = "VERIFY_SCORER_FAILED"  # verify scorer 失败
    VERIFY_WALK_FORWARD_FAILED = "VERIFY_WALK_FORWARD_FAILED"  # verify walk forward 失败
    SELL_SIGNALS_FAILED = "SELL_SIGNALS_FAILED"  # 卖出信号失败
    BACKTEST_SCORER_FAILED = "BACKTEST_SCORER_FAILED"  # 回测评分失败
    PARAM_REGISTRY_FAILED = "PARAM_REGISTRY_FAILED"  # 参数注册失败
    REFLEX_BLACKLIST_FAILED = "REFLEX_BLACKLIST_FAILED"  # 反射黑名单失败
    MARKET_CONTEXT_FAILED = "MARKET_CONTEXT_FAILED"  # 市场上下文失败
    SIGNAL_FILTER_FAILED = "SIGNAL_FILTER_FAILED"  # 信号过滤失败
    SIMULATOR_RUN_FAILED = "SIMULATOR_RUN_FAILED"  # 模拟器运行失败


class ZettarancError(ValueError):
    """项目统一异常基类

    继承 ValueError 以兼容存量 `except ValueError` 代码；
    str(exc) 输出统一格式：[ERROR_CODE] message
    """

    def __init__(self, code: ErrorCode, message: str, *, cause: Exception | None = None) -> None:
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
