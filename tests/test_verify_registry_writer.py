"""多因子结果 → param_registry 测试"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.verify.registry_writer import (
    RegistryWriteReport,
    load_config_from_registry,
    write_optimization_to_registry,
)


def test_registry_writer_dataclass_importable():
    assert RegistryWriteReport is not None


def test_load_config_returns_none_when_missing():
    """registry 没有 shaofu_v1 条目时返回 None"""
    with patch(
        "modules.verify.registry_writer._registry_get",
        return_value=None,
    ):
        config = load_config_from_registry("shaofu_v1")
        assert config is None


def test_write_v3_3_3_results_format():
    """v3.3.3 多因子优化结果格式能被正确解析"""
    fake_v3_3_3 = {
        "phase1_best": {
            "params": {
                "j_threshold": 5,
                "stop_loss_pct": -0.05,
                "vol_shrink_threshold": 0.8,
            }
        },
        "phase2_best": {
            "SIDEWAYS": {"j_threshold": 12, "stop_loss_pct": -0.03},
            "BULL": {"j_threshold": 12, "stop_loss_pct": -0.05},
            "BEAR": {"j_threshold": 3, "stop_loss_pct": -0.02},
        },
    }
    report = write_optimization_to_registry(fake_v3_3_3, strategy_name="shaofu_v1")
    assert isinstance(report, RegistryWriteReport)
    assert report.written >= 1
    assert report.skipped == 0
