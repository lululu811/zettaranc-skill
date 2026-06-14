"""Tests for ParamMutator — 参数变异引擎。"""
import pytest

from modules.self_optimizer.mutator import ParamMutator, MutationRecord
from modules.self_optimizer.param_registry import get_defaults, get_registry


# ==================== Fixtures ====================

@pytest.fixture
def mutator():
    """带固定种子的变异器，结果可复现。"""
    return ParamMutator(seed=42)


@pytest.fixture
def default_params():
    """Registry 出厂默认值。"""
    return get_defaults()


# ==================== 基础行为 ====================

def test_mutate_one_returns_new_params_and_record(mutator, default_params):
    """单次变异返回 (新参数集, 记录)。"""
    new_params, record = mutator.mutate_one(default_params)
    assert isinstance(new_params, dict)
    assert isinstance(record, MutationRecord)
    assert record.param_name != ""
    assert record.strategy != ""


def test_mutate_one_changes_exactly_one_param(mutator, default_params):
    """一次变异只改一个参数。"""
    new_params, record = mutator.mutate_one(default_params)
    # 统计变化的参数数
    changes = 0
    for sname in default_params:
        for pname in default_params[sname]:
            if new_params.get(sname, {}).get(pname) != default_params[sname][pname]:
                changes += 1
    assert changes == 1


def test_mutate_one_param_in_range(mutator, default_params):
    """变异后的参数值必须在 registry 定义的 [min, max] 内。"""
    for _ in range(50):  # 跑 50 轮验证边界安全
        params, rec = mutator.mutate_one(default_params, strategy="random")
        spec = __import__("modules.self_optimizer.param_registry", fromlist=[""]).get_param_info(
            rec.strategy, rec.param_name
        )
        if spec:
            val = params[rec.strategy][rec.param_name]
            assert spec.min <= val <= spec.max, (
                f"{rec.strategy}.{rec.param_name}={val} 不在 [{spec.min}, {spec.max}]"
            )


def test_mutate_one_with_strategy_filter(mutator, default_params):
    """指定 strategy_filter 后只在该策略内变异。"""
    for _ in range(20):
        params, rec = mutator.mutate_one(default_params, strategy_filter="b1")
        assert rec.strategy == "b1"


def test_mutate_one_wired_only_default(mutator, default_params):
    """默认 wired_only=True，只从 wired 参数中选。"""
    all_wired = True
    for _ in range(50):
        _, rec = mutator.mutate_one(default_params)
        spec = __import__("modules.self_optimizer.param_registry", fromlist=[""]).get_param_info(
            rec.strategy, rec.param_name
        )
        if spec and not spec.wired:
            all_wired = False
            break
    assert all_wired, "mutate_one 默认应该只选 wired=True 的参数"


def test_pick_param_falls_back_to_unwired_when_none_wired(mutator, default_params):
    """当所有 wired 参数被用完时（mutate_n 场景），应正常返回 None。"""
    params, rec = mutator.mutate_one(
        default_params,
        strategy_filter="stop_loss", param_filter="trailing_stop_activation",
    )
    assert rec.strategy == "stop_loss"
    assert rec.param_name == "trailing_stop_activation"


def test_mutate_one_with_param_filter(mutator, default_params):
    """指定 param_filter 后只变异该参数。"""
    params, rec = mutator.mutate_one(
        default_params, strategy_filter="b1", param_filter="j_threshold"
    )
    assert rec.strategy == "b1"
    assert rec.param_name == "j_threshold"


# ==================== 多重变异 ====================

def test_mutate_n_returns_n_records(mutator, default_params):
    """mutate_n(2) 返回 2 条记录。"""
    params, records = mutator.mutate_n(default_params, n=3)
    assert len(records) == 3


def test_mutate_n_params_are_distinct(mutator, default_params):
    """mutate_n 不重复变异同一个参数。"""
    params, records = mutator.mutate_n(default_params, n=5)
    # 如果 n 小于总参数数，应该全是不同的
    keys = [(r.strategy, r.param_name) for r in records]
    assert len(keys) == len(set(keys)), f"有重复: {keys}"


def test_mutate_n_does_not_exceed_available_params(mutator, default_params):
    """n 超过可用参数数时不会崩溃。"""
    # 总共有 32 个参数，n=50 应该安全地变异全部
    params, records = mutator.mutate_n(default_params, n=50)
    assert len(records) <= 33  # 最多就是总参数数


# ==================== 历史记录 ====================

def test_history_tracks_mutations(mutator, default_params):
    """history 随每次 mutate 增长。"""
    assert mutator.mutation_count == 0
    mutator.mutate_one(default_params)
    assert mutator.mutation_count == 1
    mutator.mutate_one(default_params)
    assert mutator.mutation_count == 2


def test_clear_history(mutator, default_params):
    """clear_history 重置计数器。"""
    mutator.mutate_one(default_params)
    mutator.mutate_one(default_params)
    mutator.clear_history()
    assert mutator.mutation_count == 0


# ==================== 变异策略 ====================

def test_strategy_step_changes_by_exact_step(mutator, default_params):
    """step 变异的变化量正好是 ±step（考虑浮点精度）。"""
    for _ in range(30):
        params, rec = mutator.mutate_one(default_params, strategy="step")
        spec = __import__("modules.self_optimizer.param_registry", fromlist=[""]).get_param_info(
            rec.strategy, rec.param_name
        )
        if spec:
            delta = round(abs(rec.new_value - rec.old_value), 6)
            assert delta == pytest.approx(spec.step) or delta == 0, (
                f"{rec.strategy}.{rec.param_name}: delta={delta} != step={spec.step}"
            )


def test_strategy_random_does_not_equal_old_often(mutator, default_params):
    """random 策略几乎不可能抽到原值（32 参数各有 3-10 档）。"""
    diff_count = 0
    for _ in range(50):
        params, rec = mutator.mutate_one(default_params, strategy="random")
        if rec.new_value != rec.old_value:
            diff_count += 1
    assert diff_count >= 45, "random 策略太多次抽到原值"


def test_strategy_jitter_changes_by_less_than_2x_step(mutator, default_params):
    """jitter 的变化量不超过 2 倍步长。"""
    for _ in range(30):
        params, rec = mutator.mutate_one(default_params, strategy="jitter")
        spec = __import__("modules.self_optimizer.param_registry", fromlist=[""]).get_param_info(
            rec.strategy, rec.param_name
        )
        if spec:
            delta = abs(rec.new_value - rec.old_value)
            assert delta <= spec.step * 2.0, (
                f"{rec.strategy}.{rec.param_name}: delta={delta} > 2*step={spec.step * 2}"
            )


# ==================== 重置 ====================

def test_reset_to_defaults(mutator, default_params):
    """reset_to_defaults 回到 registry 默认值。"""
    # 先变异
    params, _ = mutator.mutate_n(default_params, n=5)
    assert params != default_params
    # 再重置
    reset = mutator.reset_to_defaults()
    assert reset == default_params


def test_reset_is_deep_copy(mutator, default_params):
    """reset_to_defaults 返回新的 dict，修改不影响内部。"""
    reset = mutator.reset_to_defaults()
    reset["b1"]["j_threshold"] = 999
    # 不影响 defaults
    assert mutator._defaults["b1"]["j_threshold"] == -10


# ==================== 确定性 ====================

def test_deterministic_seed():
    """相同 seed 产生相同的变异序列。"""
    m1 = ParamMutator(seed=123)
    m2 = ParamMutator(seed=123)
    params = get_defaults()
    for _ in range(5):
        p1, r1 = m1.mutate_one(params)
        p2, r2 = m2.mutate_one(params)
        params = p1
        assert r1.strategy == r2.strategy
        assert r1.param_name == r2.param_name
        assert r1.new_value == r2.new_value


# ==================== 边界情况 ====================

def test_mutate_with_empty_params(mutator):
    """空参数集仍能变异（从 registry 拿默认值当 old_val）。"""
    params, record = mutator.mutate_one({})
    # 应该产生了一个参数变异
    assert record.param_name != ""
    assert record.strategy != ""
    # 新参数集包含至少一个策略
    assert len(params) >= 1
    assert record.param_name in params.get(record.strategy, {})


def test_mutate_with_unknown_filter(mutator, default_params):
    """不存在的 strategy_filter 返回原参数。"""
    params, record = mutator.mutate_one(default_params, strategy_filter="not_a_strategy")
    assert params == default_params
    assert record.param_name == ""


def test_record_delta_property():
    """MutationRecord.delta 计算正确。"""
    r = MutationRecord(
        strategy="b1", param_name="j_threshold",
        old_value=30, new_value=28, delta_pct=-6.67,
        mutation_type="step", description="test",
    )
    assert r.delta == -2


def test_mutation_count_property(mutator, default_params):
    """mutation_count 与 history 长度一致。"""
    assert mutator.mutation_count == 0
    mutator.mutate_one(default_params)
    assert mutator.mutation_count == 1
    assert mutator.mutation_count == len(mutator.history)
