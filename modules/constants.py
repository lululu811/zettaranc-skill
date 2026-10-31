"""
Zettaranc 项目级魔法字面量集中常量。

将散落在 modules/ 各处的可命名配置值（默认值 / 阈值 / 权重）统一在此处，
提高可读性、避免维护时改一处忘一处。仅放"配置语义"型常量；纯数学/统计阈值
（如显著性 α=0.05）仍放在使用点附近。

L5+L6 质量清扫（2026-07-18）：
- BACKTEST_*: 回测默认仓位 / 止损档位 / 移动止损 等
- MARKET_REGIME_WEIGHT_*: 大盘状态评估权重
- STATISTICS_SIGNIFICANCE_ALPHA: 统计检验 α
- POOL_DEFAULT_TOP_RETURN_PCT: 候选池涨幅分位数
- INTENT_DEFAULT_SCORE_THRESHOLD: 意图路由最小分数阈值
- SCREENER_*: 选股器阈值
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 回测默认参数（仓位 / 止损档位 / 移动止损）
# ---------------------------------------------------------------------------

# 单票最大仓位占比（默认 20%）
BACKTEST_DEFAULT_MAX_POSITION_PCT = 0.20

# 牛市加大仓位比例
BACKTEST_BULL_POSITION_PCT = 0.30

# 震荡市适中仓位比例
BACKTEST_RANGE_POSITION_PCT = 0.20

# 熊市最低仓位比例
BACKTEST_BEAR_POSITION_PCT = 0.15

# 高波动策略仓位上限
BACKTEST_HIGH_VOLUME_POSITION_PCT = 0.30

# 极高仓位上限（组合网格搜索 maximum）
BACKTEST_VERY_HIGH_POSITION_PCT = 0.40

# 极保守仓位上限
BACKTEST_LOW_VOLUME_POSITION_PCT = 0.10

# 默认移动止损比例（负值；如 -0.05 表示从高点回落 5% 即止损）
BACKTEST_DEFAULT_TRAILING_STOP_PCT = -0.05

# 缺省止损档位（-0.05 = 5%）
BACKTEST_DEFAULT_STOP_LOSS_PCT = -0.05

# 宽止损档位（-0.10 = 10%）
BACKTEST_LARGE_STOP_LOSS_PCT = -0.10

# 偏宽止损档位（-0.08 = 8%）
BACKTEST_MID_STOP_LOSS_PCT = -0.08

# 偏紧止损档位（-0.07 = 7%）
BACKTEST_HIGH_VOL_STOP_LOSS_PCT = -0.07

# 紧止损档位（-0.03 = 3%）
BACKTEST_TIGHT_STOP_LOSS_PCT = -0.03


# ---------------------------------------------------------------------------
# 大盘状态评估权重（权重和 = 0.7，另 0.3 留给其他维度）
# ---------------------------------------------------------------------------

MARKET_REGIME_WEIGHT_MA_ALIGNMENT = 0.30
MARKET_REGIME_WEIGHT_TREND_SLOPE = 0.20
MARKET_REGIME_WEIGHT_WHITE_YELLOW = 0.20


# ---------------------------------------------------------------------------
# 统计显著性阈值
# ---------------------------------------------------------------------------

# 标准 0.05 显著性水平（夏普检验 / Monte Carlo 置换检验共用）
STATISTICS_SIGNIFICANCE_ALPHA = 0.05


# ---------------------------------------------------------------------------
# 候选池筛选默认值
# ---------------------------------------------------------------------------

# 候选池涨幅分位数默认值（取前 30%）
POOL_DEFAULT_TOP_RETURN_PCT = 0.30


# ---------------------------------------------------------------------------
# 意图路由最小分数阈值
# ---------------------------------------------------------------------------

# 意图路由器低于该分数视为不匹配
INTENT_DEFAULT_SCORE_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# 数据同步：速率限制器
# ---------------------------------------------------------------------------

# API 调用速率限制器缓冲秒数（窗口溢出后 +0.05s 等待）
RATE_LIMITER_WINDOW_BUFFER_S = 0.05


# ---------------------------------------------------------------------------
# 模拟器默认参数（位移量/风险约束）
# ---------------------------------------------------------------------------

# 单笔最大风险预算（占账户资金 10%）
SIMULATOR_MAX_RISK_PER_TRADE_PCT = 0.10

# 执行约束默认滑点（5bps）
SIMULATOR_DEFAULT_SLIPPAGE = 0.05

# A 股主板单日涨跌幅限制
SIMULATOR_MAIN_BOARD_PRICE_LIMIT_PCT = 0.10

# A 股 ST/*ST 单日涨跌幅限制
SIMULATOR_ST_PRICE_LIMIT_PCT = 0.05

# A 股创业板 / 科创板 单日涨跌幅限制
SIMULATOR_GEM_STAR_PRICE_LIMIT_PCT = 0.20


# ---------------------------------------------------------------------------
# 市场状态判定阈值（唯一来源）
# ---------------------------------------------------------------------------
# 此前同一组数字散在三处：core/market_context.py 的默认参数、simulator/market_context.py
# 里手抄的两份判定、以及 dynamic_config.MarketTimingWeights。改一处忘另一处就会
# 让"市场状态"在不同模块给出不同结论。

MARKET_REGIME_STRONG_TREND = 65.0
MARKET_REGIME_WEAK_TREND = 40.0
MARKET_REGIME_STRONG_BREADTH = 0.1
MARKET_REGIME_WEAK_BREADTH = -0.15
MARKET_REGIME_STRONG_MONEYFLOW = 55.0
MARKET_REGIME_WEAK_MONEYFLOW = 40.0


# ---------------------------------------------------------------------------
# 搜索空间粒度（参数优化器步长）
# ---------------------------------------------------------------------------

PARAM_STEP_FINE = 0.05
PARAM_STEP_COARSE = 0.10
PARAM_WEIGHT_STEP = 0.05
