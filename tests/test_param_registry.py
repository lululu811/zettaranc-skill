"""Tests for param_registry — 参数注册表结构性验证。"""
import pytest

from modules.self_optimizer.param_registry import (
    get_registry,
    get_defaults,
    get_param_info,
    list_optimizable,
    get_param_count,
    get_strategy_names,
    ParamSpec,
    StrategyParamGroup,
)


def test_registry_has_expected_strategies():
    """至少要有 10+ 个策略组（当前 12 个）。"""
    assert len(get_registry()) >= 10


def test_registry_has_30plus_params():
    """至少要有 30 个可优化参数（当前 32 个）。"""
    assert get_param_count() >= 30


def test_all_strategies_have_params():
    """每个策略组至少 1 个参数。"""
    for name, group in get_registry().items():
        assert len(group.params) >= 1, f"{name} 必须有参数"


def test_get_defaults_returns_correct_shape():
    """get_defaults() 返回每策略的参数名→默认值。"""
    defaults = get_defaults()
    for sname in get_strategy_names():
        assert sname in defaults, f"{sname} 在 defaults 中丢失"
        assert len(defaults[sname]) == len(get_registry()[sname].params)


def test_get_param_info_found():
    """查已知参数返回 ParamSpec。"""
    info = get_param_info("b1", "j_threshold")
    assert info is not None
    assert info.default == -10
    assert info.min == -30
    assert info.max == 0
    assert info.step == 2


def test_get_param_info_not_found():
    """查未知参数返回 None。"""
    assert get_param_info("not_a_strategy", "x") is None
    assert get_param_info("b1", "not_a_param") is None


def test_optimizable_list_format():
    """list_optimizable() 返回 (策略, 参数名, 描述) 元组列表。"""
    items = list_optimizable()
    assert len(items) == get_param_count()
    for strategy, pname, desc in items:
        assert isinstance(strategy, str)
        assert isinstance(pname, str)
        assert isinstance(desc, str)
        assert len(desc) > 5  # 描述不能太短


def test_param_spec_is_frozen():
    """ParamSpec 是不可变的。"""
    spec = ParamSpec(
        name="test", default=10, min=0, max=100, step=1,
        category="entry", description="test", impact="test",
    )
    with pytest.raises(Exception):
        spec.default = 20  # frozen dataclass 应该报错


def test_all_params_have_valid_category():
    """所有参数的 category 必须是合法值。"""
    valid = {"entry", "exit", "risk", "scoring", "pattern"}
    for group in get_registry().values():
        for pspec in group.params.values():
            assert pspec.category in valid, f"{group.strategy_name}.{pspec.name} 的 category={pspec.category} 不合法"


def test_all_params_have_impact():
    """所有参数必须有 impact 描述。"""
    for group in get_registry().values():
        for pspec in group.params.values():
            assert len(pspec.impact) > 10, f"{group.strategy_name}.{pspec.name} 缺少有效的 impact 描述"


def test_param_ranges_are_valid():
    """min < default < max。"""
    for group in get_registry().values():
        for pspec in group.params.values():
            assert pspec.min < pspec.max, f"{group.strategy_name}.{pspec.name} min >= max"
            assert pspec.min <= pspec.default <= pspec.max, (
                f"{group.strategy_name}.{pspec.name} default={pspec.default} 不在 [{pspec.min}, {pspec.max}]"
            )


def test_defaults_consistency():
    """defaults 里的值和 registry 里的默认值一致。"""
    defaults = get_defaults()
    for sname, group in get_registry().items():
        for pname, pspec in group.params.items():
            assert defaults[sname][pname] == pspec.default, (
                f"{sname}.{pname}: defaults={defaults[sname][pname]} != spec={pspec.default}"
            )


def test_registry_is_immutable():
    """get_registry() 返回的是副本，修改不影响内部。"""
    reg = get_registry()
    original_count = len(reg)
    reg["hacked"] = StrategyParamGroup(  # type: ignore[assignment]
        strategy_name="hacked", display_name="hacked", description="",
    )
    assert len(get_registry()) == original_count


def test_no_duplicate_param_names():
    """同一策略内不能有重名参数。"""
    for name, group in get_registry().items():
        pnames = list(group.params.keys())
        assert len(pnames) == len(set(pnames)), f"{name} 有重名参数: {pnames}"
