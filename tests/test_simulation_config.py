"""CLI 与 API 的模拟器配置必须完全一致。

历史上两个入口各写一份装配代码，默认值已经漂移：评分 70/60、仓位上限
0.20/0.15、动态滑点 False/True、成本模型词汇不同（simple/advanced vs
zero/realistic）、共振分单位差 100 倍（CLI 的 0-1 与 API 的 0-100÷100）。

这些测试锁住"同一组默认输入 → 同一个 SimulationConfig"。
"""

from __future__ import annotations

import dataclasses

import pytest


def _require_api_deps() -> None:
    """API 侧依赖缺失时跳过该测试（fastapi/pydantic 是可选依赖）。"""
    pytest.importorskip("pydantic", reason="pydantic 是 API 可选依赖，未安装则跳过")
    pytest.importorskip("api.models.simulator", reason="api 包依赖缺失则跳过")


def _cli_default_args():
    """从**真实 parser** 取 CLI 的默认参数——避免测试里再抄一份默认值。"""
    from modules.cli import build_parser

    return build_parser().parse_args(["simulate", "600519.SH"])


class TestCliApiConfigParity:
    @pytest.fixture(autouse=True)
    def _skip_without_api(self):
        _require_api_deps()

    def test_default_configs_are_identical(self):
        from api.models.simulator import SimulationRequest
        from api.services.simulator_service import _request_to_config
        from modules.cli_commands.simulate import _build_config_from_args

        cli_cfg = _build_config_from_args(_cli_default_args())
        api_cfg = _request_to_config(SimulationRequest())

        assert dataclasses.fields(cli_cfg) == dataclasses.fields(api_cfg)
        for f in dataclasses.fields(cli_cfg):
            assert getattr(cli_cfg, f.name) == getattr(api_cfg, f.name), f"{f.name} 在 CLI 与 API 之间不一致"

    def test_resonance_score_unit_is_fraction(self):
        """共振分是 0-1 分数口径——同一个 0.35 在两边必须同义。"""
        from api.models.simulator import SimulationRequest
        from api.services.simulator_service import _request_to_config
        from modules.cli_commands.simulate import _build_config_from_args

        cli_cfg = _build_config_from_args(_cli_default_args())
        api_cfg = _request_to_config(SimulationRequest())

        assert cli_cfg.min_resonance_score == pytest.approx(0.35)
        assert api_cfg.min_resonance_score == pytest.approx(0.35)
        # SimulationConfig 自身的口径也是 0-1
        from modules.simulator import SimulationConfig

        assert SimulationConfig().min_resonance_score == pytest.approx(0.35)

    def test_cost_model_vocabulary(self):
        """成本模型词汇统一：zero / simple / realistic（advanced 为历史别名）。"""
        from modules.simulator.config import build_cost_model

        zero = build_cost_model("zero")
        assert zero.commission_rate == 0
        assert zero.stamp_duty_rate == 0

        simple = build_cost_model("simple")
        assert simple.commission_rate == pytest.approx(0.0003)
        assert simple.stamp_duty_rate == 0
        assert simple.apply_stamp_duty_on_sell is False

        realistic = build_cost_model("realistic")
        assert realistic.commission_rate == pytest.approx(0.00025)
        assert realistic.min_commission == pytest.approx(5.0)
        assert realistic.stamp_duty_rate == pytest.approx(0.0005)

        # 历史别名
        assert build_cost_model("advanced") == realistic

    def test_canonical_defaults_match_config_class(self):
        """规范默认值必须与 SimulationConfig / constants 一致。"""
        from modules.constants import BACKTEST_DEFAULT_MAX_POSITION_PCT
        from modules.simulator import SimulationConfig
        from modules.simulator.config import SIMULATION_DEFAULTS

        base = SimulationConfig()
        assert SIMULATION_DEFAULTS["position_score_threshold"] == base.position_score_threshold
        assert SIMULATION_DEFAULTS["max_position_pct"] == BACKTEST_DEFAULT_MAX_POSITION_PCT
        assert SIMULATION_DEFAULTS["min_resonance_score"] == base.min_resonance_score
        assert SIMULATION_DEFAULTS["use_dynamic_slippage"] == base.use_dynamic_slippage
        assert SIMULATION_DEFAULTS["benchmark_code"] == base.benchmark_code
