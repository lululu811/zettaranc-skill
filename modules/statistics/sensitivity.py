#!/usr/bin/env python3
"""
参数敏感性分析模块

检验策略是否过度拟合历史数据：
- 参数稍微改变，策略表现是否剧烈波动？
- 是否存在"参数悬崖"（某个参数值附近表现急剧变化）？
- 稳健的参数范围是什么？

核心思想：
- 如果参数敏感性高 → 过度拟合，实盘风险大
- 如果参数敏感性低 → 策略稳健，可以使用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable

from ..constants import (
    BACKTEST_DEFAULT_STOP_LOSS_PCT,
    BACKTEST_HIGH_VOL_STOP_LOSS_PCT,
    BACKTEST_LARGE_STOP_LOSS_PCT,
    BACKTEST_MID_STOP_LOSS_PCT,
    BACKTEST_TIGHT_STOP_LOSS_PCT,
)


@dataclass
class SensitivityResult:
    """参数敏感性分析结果"""

    param_name: str  # 参数名称
    base_value: Any  # 基准值
    base_score: float  # 基准得分（如夏普比率）

    # 扫描结果
    scan_values: list[Any] = field(default_factory=list)  # 扫描的参数值
    scan_scores: list[float] = field(default_factory=list)  # 对应的得分

    # 敏感性指标
    sensitivity_score: float = 0.0  # 敏感性得分（0-1，越低越稳健）
    robust_range: tuple[Any, Any] = (None, None)  # 稳健范围
    has_cliff: bool = False  # 是否存在参数悬崖

    def is_robust(self) -> bool:
        """判断参数是否稳健"""
        return self.sensitivity_score < 0.3 and not self.has_cliff


@dataclass
class ParameterSensitivityReport:
    """完整的参数敏感性报告"""

    strategy_name: str
    results: list[SensitivityResult] = field(default_factory=list)

    overall_sensitivity: float = 0.0  # 综合敏感性得分
    is_robust: bool = False  # 整体是否稳健
    robust_params: list[str] = field(default_factory=list)  # 稳健的参数列表
    sensitive_params: list[str] = field(default_factory=list)  # 敏感的参数列表

    def add_result(self, result: SensitivityResult) -> None:
        """添加单个参数的分析结果"""
        self.results.append(result)
        self._recalculate()

    def _recalculate(self):
        """重新计算综合指标"""
        if not self.results:
            return

        # 综合敏感性 = 各参数敏感性的加权平均
        scores = [r.sensitivity_score for r in self.results]
        self.overall_sensitivity = sum(scores) / len(scores)

        # 分类
        self.robust_params = [r.param_name for r in self.results if r.is_robust()]
        self.sensitive_params = [r.param_name for r in self.results if not r.is_robust()]

        # 整体稳健性：所有参数都稳健
        self.is_robust = all(r.is_robust() for r in self.results)

    def generate_summary(self) -> str:
        """生成总结报告"""
        lines = [
            f"{'=' * 70}",
            f"参数敏感性报告: {self.strategy_name}",
            f"{'=' * 70}",
            "",
            f"综合敏感性得分: {self.overall_sensitivity:.2f} (0=稳健, 1=敏感)",
            f"整体评价: {'✅ 稳健' if self.is_robust else '❌ 敏感'}",
            "",
        ]

        if self.robust_params:
            lines.append(f"✅ 稳健参数 ({len(self.robust_params)}个):")
            for name in self.robust_params:
                result = next(r for r in self.results if r.param_name == name)
                lines.append(
                    f"  - {name}: {result.base_value} "
                    f"(得分 {result.base_score:.2f}, "
                    f"稳健范围 {result.robust_range[0]}-{result.robust_range[1]})"
                )
            lines.append("")

        if self.sensitive_params:
            lines.append(f"❌ 敏感参数 ({len(self.sensitive_params)}个):")
            for name in self.sensitive_params:
                result = next(r for r in self.results if r.param_name == name)
                lines.append(
                    f"  - {name}: {result.base_value} "
                    f"(得分 {result.base_score:.2f}, "
                    f"敏感性 {result.sensitivity_score:.2f})"
                )
                if result.has_cliff:
                    lines.append("    ⚠️  存在参数悬崖！")
            lines.append("")

        lines.append(f"{'=' * 70}")
        return "\n".join(lines)


def analyze_parameter_sensitivity(
    strategy_name: str,
    param_name: str,
    base_value: Any,
    scan_range: list[Any],
    evaluate_fn: Callable[[Any], float],
) -> SensitivityResult:
    """
    分析单个参数的敏感性

    Args:
        strategy_name: 策略名称
        param_name: 参数名称
        base_value: 基准值
        scan_range: 扫描的参数值列表
        evaluate_fn: 评估函数，接受参数值，返回得分（如夏普比率）

    Returns:
        SensitivityResult: 敏感性分析结果

    Example:
        >>> def eval_sharpe(j_threshold):
        ...     config = LoopConfig(j_threshold=j_threshold)
        ...     result = backtest_shaofu_single("600519.SH", config=config)
        ...     return result.sharpe_ratio
        >>>
        >>> result = analyze_parameter_sensitivity(
        ...     "少妇战法", "j_threshold", 12,
        ...     scan_range=[5, 8, 10, 12, 15, 18, 20],
        ...     evaluate_fn=eval_sharpe
        ... )
    """
    # 1. 计算基准得分
    base_score = evaluate_fn(base_value)

    # 2. 扫描所有参数值
    scan_scores = []
    for val in scan_range:
        score = evaluate_fn(val)
        scan_scores.append(score)

    # 3. 计算敏感性得分
    # 敏感性 = 得分波动的标准差 / 基准得分
    if base_score > 0 and scan_scores:
        mean_score = sum(scan_scores) / len(scan_scores)
        variance = sum((s - mean_score) ** 2 for s in scan_scores) / len(scan_scores)
        std_score = variance**0.5
        sensitivity_score = std_score / abs(base_score) if base_score != 0 else 0.0
        # 归一化到 0-1
        sensitivity_score = min(sensitivity_score, 1.0)
    else:
        sensitivity_score = 1.0

    # 4. 检测参数悬崖
    # 悬崖定义：相邻参数值得分差异超过 50%
    has_cliff = False
    if len(scan_scores) >= 2:
        for i in range(len(scan_scores) - 1):
            s1, s2 = scan_scores[i], scan_scores[i + 1]
            if s1 > 0 and abs(s2 - s1) / abs(s1) > 0.5:
                has_cliff = True
                break

    # 5. 计算稳健范围
    # 稳健范围：得分在基准得分 ±30% 内的参数值
    if base_score > 0:
        threshold_low = base_score * 0.7
        threshold_high = base_score * 1.3
        robust_values = [val for val, score in zip(scan_range, scan_scores) if threshold_low <= score <= threshold_high]
        robust_range = (min(robust_values), max(robust_values)) if robust_values else (base_value, base_value)
    else:
        robust_range = (base_value, base_value)

    return SensitivityResult(
        param_name=param_name,
        base_value=base_value,
        base_score=base_score,
        scan_values=scan_range,
        scan_scores=scan_scores,
        sensitivity_score=sensitivity_score,
        robust_range=robust_range,
        has_cliff=has_cliff,
    )


def analyze_all_parameters(
    strategy_name: str,
    base_config: Any,
    ts_code: str,
    days: int = 500,
) -> ParameterSensitivityReport:
    """
    分析所有关键参数的敏感性

    Args:
        strategy_name: 策略名称
        base_config: 基准配置（LoopConfig）
        ts_code: 股票代码
        days: 回测天数

    Returns:
        ParameterSensitivityReport: 完整报告
    """
    from modules.loop_engine import LoopConfig
    from modules.backtest import backtest_shaofu_single

    report = ParameterSensitivityReport(strategy_name=strategy_name)

    # 定义要分析的参数
    params_to_analyze = [
        ("j_threshold", [5, 8, 10, 12, 15, 18, 20]),
        (
            "stop_loss_pct",
            [
                BACKTEST_LARGE_STOP_LOSS_PCT,
                BACKTEST_MID_STOP_LOSS_PCT,
                BACKTEST_HIGH_VOL_STOP_LOSS_PCT,
                BACKTEST_DEFAULT_STOP_LOSS_PCT,
                BACKTEST_TIGHT_STOP_LOSS_PCT,
            ],
        ),
        ("bbi_break_days", [1, 2, 3, 4]),
        ("vol_shrink_threshold", [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]),
    ]

    for param_name, scan_range in params_to_analyze:

        def evaluate_fn(param_value, _param_name=param_name) -> float:
            """对单个参数值跑回测，返回综合得分（夏普比率）。闭包参数通过默认参数传递。"""
            # 创建新配置
            config_dict = {
                "j_threshold": base_config.j_threshold,
                "stop_loss_pct": base_config.stop_loss_pct,
                "bbi_break_days": base_config.bbi_break_days,
                "vol_shrink_threshold": base_config.vol_shrink_threshold,
            }
            config_dict[_param_name] = param_value
            config = LoopConfig(**config_dict)

            # 运行回测
            result = backtest_shaofu_single(ts_code, days=days, config=config)

            # 返回综合得分（夏普比率）
            return result.sharpe_ratio if result.trades else 0.0

        # 分析单个参数
        base_value = getattr(base_config, param_name)
        result = analyze_parameter_sensitivity(
            strategy_name=strategy_name,
            param_name=param_name,
            base_value=base_value,
            scan_range=scan_range,  # type: ignore[arg-type]
            evaluate_fn=evaluate_fn,
        )

        report.add_result(result)

    return report
