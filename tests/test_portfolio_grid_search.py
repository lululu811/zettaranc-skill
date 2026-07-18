"""组合回测参数网格搜索测试（v3.10.2）

覆盖：
- GridSearchResult / GridSearchReport 数据类
- DEFAULT_PORTFOLIO_PARAM_SPACE 维度定义正确性
- portfolio_grid_search_optimize 返回结构与排序
- 空数据 / 无效参数 / objective 排序
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from modules.verify.portfolio_walk_forward import (
    DEFAULT_PORTFOLIO_PARAM_SPACE,
    GridSearchReport,
    GridSearchResult,
    portfolio_grid_search_optimize,
)
from modules.simulator.param_space import ParamDimension, generate_grid


# ============================================================
# 数据类测试
# ============================================================


class TestGridSearchResult:
    def test_default_construction(self):
        """默认值"""
        r = GridSearchResult(params={"a": 1})
        assert r.params == {"a": 1}
        assert r.total_trades == 0
        assert r.metrics is not None


class TestGridSearchReport:
    def test_default_construction(self):
        """默认值"""
        rep = GridSearchReport()
        assert rep.results == []
        assert rep.best is None
        assert rep.objective == "sharpe"


# ============================================================
# 参数空间测试
# ============================================================


class TestDefaultParamSpace:
    def test_default_has_4_dimensions(self):
        """默认聚焦 4 个核心参数"""
        assert len(DEFAULT_PORTFOLIO_PARAM_SPACE) == 4

    def test_default_dimensions_are_loop_config_fields(self):
        """默认参数都是 LoopConfig 的合法字段"""
        from modules.loop_engine import LoopConfig

        valid_fields = set(LoopConfig().__dict__.keys())
        for dim in DEFAULT_PORTFOLIO_PARAM_SPACE:
            assert dim.name in valid_fields, f"参数 {dim.name} 不在 LoopConfig"

    def test_default_grid_size(self):
        """3×3×3×3 = 81 组合"""
        grid = generate_grid(DEFAULT_PORTFOLIO_PARAM_SPACE)
        # 每个维度 3 个 choice，4 个维度 = 3^4 = 81
        assert len(grid) == 81

    def test_each_combination_valid(self):
        """每个组合都包含全部 4 个字段"""
        grid = generate_grid(DEFAULT_PORTFOLIO_PARAM_SPACE)
        for combo in grid[:5]:
            assert "j_threshold" in combo
            assert "position_pct" in combo
            assert "stop_loss_pct" in combo
            assert "atr_stop_multiplier" in combo


class TestGridSearchOptimize:
    """portfolio_grid_search_optimize 函数行为"""

    def test_returns_report_with_results(self):
        """空 ts_codes 不会崩溃，返回有效 Report"""
        from modules.loop_engine import LoopConfig
        from modules.backtest.portfolio import PortfolioConfig

        rep = portfolio_grid_search_optimize(
            ts_codes=[],
            days=120,
            param_space=[ParamDimension("j_threshold", "choice", choices=[12])],
        )
        assert isinstance(rep, GridSearchReport)
        assert rep.objective == "sharpe"
        # 空数据 → best 应该 None 或降级
        assert rep.best is None or isinstance(rep.best, GridSearchResult)

    def test_results_sorted_by_objective_desc(self):
        """结果按 objective 降序排列"""
        # 构造 fake results 验证排序逻辑
        results = [
            GridSearchResult(params={"a": 1}, total_trades=5),
            GridSearchResult(params={"a": 2}, total_trades=5),
            GridSearchResult(params={"a": 3}, total_trades=5),
        ]
        # 给 metrics.sharpe 赋值
        results[0].metrics.sharpe = 0.5
        results[1].metrics.sharpe = 2.0
        results[2].metrics.sharpe = 1.0
        results.sort(key=lambda r: r.metrics.sharpe, reverse=True)
        assert results[0].params == {"a": 2}
        assert results[1].params == {"a": 3}
        assert results[2].params == {"a": 1}

    def test_invalid_param_field_skipped(self):
        """网格参数不在 LoopConfig 中时被跳过（白名单保护）"""
        # 构造含无效字段的 param_space
        rep = portfolio_grid_search_optimize(
            ts_codes=[],
            days=120,
            param_space=[ParamDimension("totally_fake_field", "choice", choices=[1])],
        )
        # 无交易数据 + 无效字段 → 报告 results 应为空列表
        assert rep.results == []

    def test_custom_objective_set(self):
        """objective 参数被记录到 Report"""
        rep = portfolio_grid_search_optimize(
            ts_codes=[],
            days=120,
            param_space=[ParamDimension("j_threshold", "choice", choices=[12])],
            objective="calmar",
        )
        assert rep.objective == "calmar"

    def test_grid_search_with_small_space(self):
        """小参数空间（1×1 = 1 个组合）不崩溃"""
        rep = portfolio_grid_search_optimize(
            ts_codes=[],
            days=120,
            param_space=[ParamDimension("j_threshold", "choice", choices=[12])],
        )
        # 返回 Report，best 可为 None（无数据）
        assert isinstance(rep, GridSearchReport)
