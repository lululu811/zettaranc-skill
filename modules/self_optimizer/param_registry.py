"""
Param Registry — 可进化参数清单

定义整个系统中可以被 self-optimizer 变异、回测、择优的数值参数。
每个参数记录：默认值、范围、步长、所属策略、业务含义。

设计原则：
  1. 只包含 **有业务意义、可独立调优** 的参数（不是把 every number 列出来）
  2. 范围要有意义 — 不会产生荒谬的策略行为
  3. 步长确保细粒度足够但搜索空间可控
  4. 每个参数标注对策略的 **预期影响方向**

使用方式：
  from modules.self_optimizer.param_registry import get_defaults, get_param_info

  # 拿到全部默认值
  defaults = get_defaults()
  b1_j = defaults["b1"]["j_threshold"]          # 30

  # 查某个参数的信息
  info = get_param_info("b1", "j_threshold")
  info.min, info.max, info.step                 # 10, 50, 2
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Literal
from collections.abc import Iterator


# ──────────────────────────────────────────────
# 类型定义
# ──────────────────────────────────────────────


@dataclass(frozen=True)
class ParamSpec:
    """单个参数的定义。"""
    name: str                                    # 参数名（代码中用）
    default: float | int                         # 出厂默认值
    min: float | int                             # 下限
    max: float | int                             # 上限
    step: float | int                            # 搜索步长
    category: Literal["entry", "exit", "risk", "scoring", "pattern"]
    description: str                             # 业务含义
    impact: str                                  # 增大/减小对策略的影响方向
    wired: bool = False                          # True=已被策略代码接入（可变异生效）


@dataclass(frozen=True)
class StrategyParamGroup:
    """一个策略的全部可调参数。"""
    strategy_name: str
    display_name: str
    description: str
    params: dict[str, ParamSpec] = field(default_factory=dict)


# ──────────────────────────────────────────────
# 参数注册表（核心）
# ──────────────────────────────────────────────

_REGISTRY: dict[str, StrategyParamGroup] = {}


def _reg(
    strategy: str,
    display: str,
    description: str,
    params: list[ParamSpec],
) -> None:
    _REGISTRY[strategy] = StrategyParamGroup(
        strategy_name=strategy,
        display_name=display,
        description=description,
        params={p.name: p for p in params},
    )


# ==================== 买入策略参数 ====================

_reg(
    "b1", "B1 买点",
    "KDJ 超卖买点：J 值低 + 缩量 + 黄线在上的经典入场信号",
    [
        ParamSpec(
            name="j_threshold",
            default=-10, min=-30, max=0, step=2,
            category="entry",
            description="B1 买入的 J 值上限（J < threshold 触发，代码实际值 -10）",
            impact="降低（更负） → 信号更少但超卖更充分；升高 → 更多信号但精度下降",
            wired=True,
        ),
        ParamSpec(
            name="rsi6_ceiling",
            default=25, min=10, max=50, step=2,
            category="entry",
            description="B1 MDC 加分：RSI6 上限（RSI6 < ceiling 获取加分）",
            impact="增大 → 更多票获超卖加分；减小 → 加分条件更严",
            wired=True,
        ),
        ParamSpec(
            name="adx_floor",
            default=40, min=20, max=60, step=2,
            category="entry",
            description="B1 MDC 加分：ADX 下限（ADX > floor 获取动能竭尽加分）",
            impact="降低 → 更多票获 ADX 加分；升高 → 加分条件更严",
            wired=True,
        ),
        ParamSpec(
            name="green_brick_limit",
            default=4, min=2, max=8, step=1,
            category="risk",
            description="B1 绿砖拒入阈值（连续阴线 >= limit 不进场）",
            impact="增大 → 允许更多连续下跌后入场；减小 → 更保守",
            wired=True,
        ),
    ],
)

_reg(
    "sb1", "超级 B1",
    "N 型结构 + 放量 + 缩量 + J 值为负的强趋势买点",
    [
        ParamSpec(
            name="j_negative_threshold",
            default=-5, min=-30, max=10, step=2,
            category="entry",
            description="超级 B1 的 J 值上限（J <= threshold 触发，代码硬编码 -5）",
            impact="降低（更负） → 条件更严，信号更少但反弹确定性更高",
            wired=True,
        ),
        ParamSpec(
            name="n_type_gap_max",
            default=10, min=3, max=20, step=1,
            category="pattern",
            description="N 型结构的最大间隔天数（B1 到当前的天数范围）",
            impact="增大 → 识别更多 N 型但结构可能松散；减小 → 结构更紧凑",
        ),
    ],
)

_reg(
    "b2", "B2 确认买点",
    "B1 后的趋势确认买点：涨幅 + 放量 + J 值未过热",
    [
        ParamSpec(
            name="min_pct",
            default=4.0, min=2.0, max=10.0, step=0.5,
            category="entry",
            description="B2 确认的最低涨幅（%）",
            impact="增大 → 确认更严格，减少假突破；减小 → 更多早期入场机会",
            wired=True,
        ),
        ParamSpec(
            name="volume_ratio_min",
            default=1.2, min=0.8, max=3.0, step=0.2,
            category="entry",
            description="B2 放量确认的最低量比",
            impact="增大 → 排除无量反弹；减小 → 允许温和放量",
        ),
        ParamSpec(
            name="j_ceiling",
            default=55, min=30, max=80, step=2,
            category="entry",
            description="B2 确认的 J 值上限（避免在过热区追入）",
            impact="增大 → 允许更高 J 值入场；减小 → 更保守",
        ),
    ],
)


# ==================== 卖出/离场参数 ====================

_reg(
    "stop_loss", "止损规则",
    "保护性止损参数",
    [
        ParamSpec(
            name="stop_loss_pct",
            default=7.0, min=2.0, max=15.0, step=0.5,
            category="risk",
            description="固定止损百分比（匹配代码硬编码 7%）",
            impact="增大 → 扛波动能力强但单笔亏损大；减小 → 易被震出",
            wired=True,
        ),
        ParamSpec(
            name="trailing_stop_activation",
            default=8.0, min=3.0, max=20.0, step=1.0,
            category="exit",
            description="移动止盈激活阈值（浮盈超过此百分比后启动跟随止损）",
            impact="增大 → 需要更多浮盈才激活，可能回吐利润；减小 → 过早激活限制上涨",
        ),
        ParamSpec(
            name="trailing_stop_distance",
            default=4.0, min=1.0, max=10.0, step=0.5,
            category="exit",
            description="移动止盈的回撤距离（激活后从最高点回落此百分比触发卖出）",
            impact="增大 → 扛回撤能力强但利润回吐多；减小 → 锁定利润早但可能卖飞",
        ),
    ],
)

_reg(
    "s1_exit", "S1 出货信号",
    "主力出货识别：放量 + 长上影 + 高换手",
    [
        ParamSpec(
            name="volume_surge_ratio",
            default=1.5, min=1.2, max=3.0, step=0.2,
            category="pattern",
            description="S1 出货日的放量倍数阈值（量比 >= threshold）",
            impact="减小 → 更容易触发 S1 预警；增大 → 只在巨量时才触发",
        ),
        ParamSpec(
            name="upper_shadow_body_ratio",
            default=2.0, min=1.5, max=5.0, step=0.5,
            category="pattern",
            description="长上影判定：上影线长度 / 实体长度的倍数阈值",
            impact="增大 → 需要更长的上影线才判定为出货；减小 → 更容易识别上影线",
        ),
    ],
)


# ==================== 资金管理参数 ====================

_reg(
    "position", "仓位管理",
    "单笔交易仓位和组合控制",
    [
        ParamSpec(
            name="single_position_pct",
            default=30.0, min=5.0, max=100.0, step=5.0,
            category="risk",
            description="单笔信号最大仓位（占可用资金百分比）",
            impact="增大 → 收益弹性大但风险集中；减小 → 更分散更安全",
            wired=True,
        ),
        ParamSpec(
            name="max_concurrent_positions",
            default=3, min=1, max=10, step=1,
            category="risk",
            description="最大同时持仓数",
            impact="增大 → 更分散，捕捉更多机会；减小 → 更集中，便于管理",
        ),
        ParamSpec(
            name="consecutive_loss_cooloff",
            default=3, min=1, max=6, step=1,
            category="risk",
            description="连续亏损 N 次后自动减半仓位",
            impact="增大 → 容忍更多连续亏损；减小 → 更早启动风控",
        ),
    ],
)


# ==================== 评分体系参数 ====================

_reg(
    "sandglass", "沙漏评分 V9",
    "图形审美选股评分：五大因子加权求和",
    [
        ParamSpec(
            name="weight_volume_shrink",
            default=0.20, min=0.05, max=0.40, step=0.05,
            category="scoring",
            description="缩量/收敛因子权重（近期量能收缩程度）",
            impact="增大 → 更看重缩量收敛形态",
        ),
        ParamSpec(
            name="weight_pivot_proximity",
            default=0.20, min=0.05, max=0.40, step=0.05,
            category="scoring",
            description="枢轴邻近因子权重（价格离支撑位距离）",
            impact="增大 → 更看重低位支撑",
        ),
        ParamSpec(
            name="weight_volume_slope",
            default=0.20, min=0.05, max=0.40, step=0.05,
            category="scoring",
            description="量能斜率因子权重（成交量趋势）",
            impact="增大 → 更看重温和缩量趋势",
        ),
        ParamSpec(
            name="weight_ma_structure",
            default=0.20, min=0.05, max=0.40, step=0.05,
            category="scoring",
            description="均线结构因子权重（多头排列 + 均线收敛）",
            impact="增大 → 更看重均线形态",
        ),
        ParamSpec(
            name="weight_event_risk",
            default=0.20, min=0.05, max=0.40, step=0.05,
            category="scoring",
            description="事件风险因子权重（跳空/连跌/异常放量扣分力度）",
            impact="增大 → 对异常事件更敏感",
        ),
        ParamSpec(
            name="perfect_threshold",
            default=80, min=60, max=95, step=5,
            category="scoring",
            description="完美图形的总分门槛（>= threshold 判定为 is_perfect）",
            impact="增大 → 完美图形标准更严；减小 → 更容易达标",
        ),
    ],
)

_reg(
    "centipede", "蜈蚣图识别",
    "堆量不涨、影线交替的无序形态识别",
    [
        ParamSpec(
            name="centipede_threshold",
            default=60, min=40, max=80, step=5,
            category="scoring",
            description="蜈蚣图判定总分门槛（>= threshold 判定为蜈蚣图）",
            impact="增大 → 只识别最严重的蜈蚣图；减小 → 更容易标记为蜈蚣图",
        ),
        ParamSpec(
            name="lookback_days",
            default=20, min=10, max=60, step=5,
            category="pattern",
            description="蜈蚣图计算的回溯天数",
            impact="增大 → 更长期的视角；减小 → 更敏感的短期判断",
        ),
    ],
)


# ==================== 指标计算参数 ====================

_reg(
    "macd", "MACD 指标",
    "MACD 计算参数",
    [
        ParamSpec(
            name="fast_period",
            default=12, min=5, max=30, step=1,
            category="pattern",
            description="MACD 快线周期（EMA12 默认）",
            impact="减小 → 更快响应价格变化；增大 → 更平滑但信号滞后",
        ),
        ParamSpec(
            name="slow_period",
            default=26, min=15, max=50, step=1,
            category="pattern",
            description="MACD 慢线周期（EMA26 默认）",
            impact="减小 → 更敏感；增大 → 更平滑",
        ),
        ParamSpec(
            name="signal_period",
            default=9, min=5, max=20, step=1,
            category="pattern",
            description="MACD 信号线周期（DEA9 默认）",
            impact="减小 → 金叉/死叉信号更频繁；增大 → 信号更可靠但更少",
        ),
    ],
)

_reg(
    "kdj", "KDJ 指标",
    "KDJ 计算参数",
    [
        ParamSpec(
            name="kdj_period",
            default=9, min=5, max=30, step=1,
            category="pattern",
            description="KDJ 计算周期（RSV9 默认）",
            impact="减小 → KDJ 更敏感，容易到超买超卖区；增大 → 更平滑",
        ),
    ],
)

_reg(
    "dmi", "DMI 指标",
    "DMI 趋势强度参数",
    [
        ParamSpec(
            name="dmi_period",
            default=14, min=7, max=30, step=1,
            category="pattern",
            description="DMI 计算周期",
            impact="减小 → 更敏感的趋势判断；增大 → 更平滑",
        ),
        ParamSpec(
            name="adx_threshold",
            default=25, min=15, max=40, step=2,
            category="pattern",
            description="ADX 强趋势门槛（ADX >= threshold 判定趋势行情）",
            impact="增大 → 只在高 ADX 时认趋势；减小 → 更早认趋势",
        ),
    ],
)


# ==================== 牛绳理论参数 ====================

_reg(
    "bull_rope", "牛绳理论",
    "白线/黄线关系判断趋势强度",
    [
        ParamSpec(
            name="gap_important_pct",
            default=3.0, min=1.0, max=10.0, step=0.5,
            category="pattern",
            description="牛绳缺口重要度阈值（白线与黄线偏离 % 以上视为重要缺口）",
            impact="增大 → 只有大缺口才被认为是重要信号；减小 → 小缺口也被重视",
        ),
        ParamSpec(
            name="bull_rope_ma_period",
            default=20, min=10, max=60, step=5,
            category="pattern",
            description="牛绳白线的均线周期（默认 MA20 为白线）",
            impact="减小 → 白线更贴近价格；增大 → 白线更平滑",
        ),
    ],
)


# ──────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────


def get_registry() -> dict[str, StrategyParamGroup]:
    """返回完整的参数注册表（只读）。"""
    return dict(_REGISTRY)


def get_defaults() -> dict[str, dict[str, float | int]]:
    """返回纯默认值字典，直接用于策略调用。"""
    return {
        name: {p.name: p.default for p in group.params.values()}
        for name, group in _REGISTRY.items()
    }


def get_param_info(strategy: str, param: str) -> ParamSpec | None:
    """查询某个参数的完整定义。"""
    group = _REGISTRY.get(strategy)
    if group is None:
        return None
    return group.params.get(param)


def list_optimizable() -> list[tuple[str, str, str]]:
    """列出所有可优化参数，用于 CLI 展示和随机选择。"""
    result: list[tuple[str, str, str]] = []
    for strategy, group in _REGISTRY.items():
        for pname, pspec in group.params.items():
            result.append((strategy, pname, pspec.description))
    return result


def get_param_count() -> int:
    """返回可优化参数总数。"""
    return sum(len(g.params) for g in _REGISTRY.values())


def get_strategy_names() -> list[str]:
    """返回所有已注册的策略名称。"""
    return list(_REGISTRY.keys())


_ACTIVE_OVERRIDES: dict[str, dict[str, Any]] = {}


def get_active_param(strategy: str, name: str, default: Any = None) -> Any:
    """策略函数读取参数：优先取 override，否则返回 default。

    用法（在 detect_b1 等函数中）：
        j_threshold = get_active_param("b1", "j_threshold", -10)
    """
    return _ACTIVE_OVERRIDES.get(strategy, {}).get(name, default)


def set_active_params(params: dict[str, dict[str, Any]]) -> None:
    """设置活跃的 override 参数集（由 Scorer 在跑回测前调用）。"""
    global _ACTIVE_OVERRIDES
    _ACTIVE_OVERRIDES = params


@contextlib.contextmanager
def using_params(params: dict[str, dict[str, Any]]) -> Iterator[None]:
    """上下文管理器：临时覆盖参数，退出时自动恢复。

    用法：
        with using_params({"b1": {"j_threshold": -15}}):
            score = run_backtest("000001.SZ")
    """
    old = dict(_ACTIVE_OVERRIDES)
    set_active_params(params)
    try:
        yield
    finally:
        set_active_params(old)
