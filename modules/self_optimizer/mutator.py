"""
ParamMutator — 参数变异引擎

从 param_registry 选参数、在合法范围内变异、记录每一次变化。
核心逻辑在 mutate_one()，不依赖外部状态，输入 params 输出 params。

变异策略：
  - step: 从当前值沿随机方向走一步（步长 = step），碰边界回弹
  - random: 在合法范围内完全随机采样
  - jitter: 在步长范围内做微小随机 (±step * 0.5)

用法：
  from modules.self_optimizer.mutator import ParamMutator

  mutator = ParamMutator()
  new_params, record = mutator.mutate_one(current_params, strategy="step")
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from modules.self_optimizer.param_registry import (
    ParamSpec,
    get_defaults,
    get_param_info,
    get_registry,
    list_optimizable,
)

MutationStrategy = Literal["step", "random", "jitter"]


@dataclass
class MutationRecord:
    """单次变异的完整记录。"""

    strategy: str                     # 哪个策略（如 "b1"）
    param_name: str                   # 哪个参数（如 "j_threshold"）
    old_value: float | int            # 变异前
    new_value: float | int            # 变异后
    delta_pct: float                  # 变化百分比
    mutation_type: MutationStrategy   # 变异策略
    description: str                  # 人类可读的描述

    @property
    def delta(self) -> float | int:
        return self.new_value - self.old_value


class ParamMutator:
    """参数变异器。

    Args:
        seed: 随机种子（为确定性调试用）
        default_params: 初始默认参数（从 registry 加载）
    """

    def __init__(
        self,
        seed: int | None = None,
        default_params: dict[str, dict[str, float | int]] | None = None,
    ):
        self._rng = random.Random(seed)
        self._defaults = default_params or get_defaults()
        # 完整的历史记录（跨所有 mutate 调用）
        self.history: list[MutationRecord] = []

    # ----------------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------------

    def mutate_one(
        self,
        current_params: dict[str, dict[str, float | int]],
        strategy: MutationStrategy = "step",
        strategy_filter: str | None = None,
        param_filter: str | None = None,
    ) -> tuple[dict[str, dict[str, float | int]], MutationRecord]:
        """单次变异：从当前参数集随机选一个参数，按策略变异。

        Args:
            current_params: 当前完整参数集（{策略名: {参数名: 值}}）
            strategy: 变异策略（step / random / jitter）
            strategy_filter: 限定的策略名，如 "b1"
            param_filter: 限定的参数名，如 "j_threshold"

        Returns:
            (new_params, MutationRecord)
            new_params 是 current_params 的深拷贝 + 一个参数变异
        """
        candidate = self._pick_param(strategy_filter, param_filter)
        if candidate is None:
            return current_params, MutationRecord(
                strategy="", param_name="", old_value=0, new_value=0,
                delta_pct=0.0, mutation_type=strategy,
                description="无可用参数（可能 registry 为空）",
            )
        strategy_name, param_name, spec = candidate
        old_val = current_params.get(strategy_name, {}).get(param_name, spec.default)

        if strategy == "step":
            new_val = self._step_mutate(old_val, spec)
        elif strategy == "random":
            new_val = self._random_mutate(spec)
        elif strategy == "jitter":
            new_val = self._jitter_mutate(old_val, spec)
        else:
            raise ValueError(f"未知变异策略: {strategy}")

        new_val = self._clamp(new_val, spec, align_to_step=(strategy == "random"))

        # 如果没变（概率很小），走 random 兜底
        if new_val == old_val:
            new_val = self._random_mutate(spec)

        # 构建新参数集
        new_params = {
            sname: dict(params) for sname, params in current_params.items()
        }
        if strategy_name not in new_params:
            new_params[strategy_name] = {}
        new_params[strategy_name][param_name] = new_val

        # 构建记录
        pct = ((new_val - old_val) / old_val * 100) if old_val != 0 else 0.0
        record = MutationRecord(
            strategy=strategy_name,
            param_name=param_name,
            old_value=old_val,
            new_value=new_val,
            delta_pct=round(pct, 2),
            mutation_type=strategy,
            description=(
                f"{strategy_name}.{param_name}: {old_val} → {new_val} "
                f"({pct:+.1f}%) [{spec.description}]"
            ),
        )
        self.history.append(record)
        return new_params, record

    def mutate_n(
        self,
        current_params: dict[str, dict[str, float | int]],
        n: int = 1,
        strategy: MutationStrategy = "step",
        strategy_filter: str | None = None,
    ) -> tuple[dict[str, dict[str, float | int]], list[MutationRecord]]:
        """连续变异 N 个不同的参数。

        每次选一个不同的参数（不重复），链式变异。
        """
        params = current_params
        records: list[MutationRecord] = []
        # 收集可用的参数
        all_params = [
            (s, p, spec)
            for s, p, spec in self._iter_params()
            if strategy_filter is None or s == strategy_filter
        ]
        if not all_params:
            return params, records
        # 随机选 n 个不重复的
        chosen = self._rng.sample(all_params, min(n, len(all_params)))
        for s, p, spec in chosen:
            # 构造一个临时的 filter 来 mutate 特定参数
            params, rec = self.mutate_one(
                params, strategy=strategy,
                strategy_filter=s, param_filter=p,
            )
            records.append(rec)
        return params, records

    def reset_to_defaults(self) -> dict[str, dict[str, float | int]]:
        """回到出厂默认值。"""
        return {
            sname: dict(params) for sname, params in self._defaults.items()
        }

    @property
    def mutation_count(self) -> int:
        return len(self.history)

    def clear_history(self) -> None:
        self.history.clear()

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------

    def _pick_param(
        self,
        strategy_filter: str | set[str] | None = None,
        param_filter: str | None = None,
        wired_only: bool = True,
    ) -> tuple[str, str, ParamSpec] | None:
        """随机选一个参数。默认只选 wired=True 的已接入参数。"""
        candidates = list(self._iter_params())

        exact_target = isinstance(strategy_filter, str) and param_filter is not None

        if wired_only and not exact_target:
            wired_candidates = [(s, p, spec) for s, p, spec in candidates if spec.wired]
            if wired_candidates:
                candidates = wired_candidates

        if isinstance(strategy_filter, set):
            candidates = [(s, p, spec) for s, p, spec in candidates if s in strategy_filter]
        elif strategy_filter is not None:
            candidates = [(s, p, spec) for s, p, spec in candidates if s == strategy_filter]

        if param_filter is not None:
            candidates = [(s, p, spec) for s, p, spec in candidates if p == param_filter]

        if not candidates:
            return None
        return self._rng.choice(candidates)

    def _iter_params(self):
        """遍历 registry 所有 (策略名, 参数名, ParamSpec)。"""
        for strategy, group in get_registry().items():
            for pname, pspec in group.params.items():
                yield strategy, pname, pspec

    def _step_mutate(self, old_val: float | int, spec) -> float | int:
        """沿随机方向走一步，碰边界回弹。

        不做 step 对齐（step 策略的 old_val 已经在格点上），
        只确保不越界。
        """
        direction = 1 if self._rng.random() < 0.5 else -1
        new_val = old_val + direction * spec.step
        # 回弹：如果超出边界，反向走一步
        if new_val < spec.min:
            new_val = spec.min + spec.step  # 从下限向上弹
        elif new_val > spec.max:
            new_val = spec.max - spec.step  # 从上限向下弹
        return self._to_type(new_val, spec)

    def _random_mutate(self, spec) -> float | int:
        """在范围内均匀随机采样。"""
        if isinstance(spec.step, int):
            steps = (spec.max - spec.min) // spec.step
            step_idx = self._rng.randint(0, max(1, steps))
            val = spec.min + step_idx * spec.step
        else:
            # 浮点数：均匀采样后对齐到 step 的倍数
            steps = max(1, round((spec.max - spec.min) / spec.step))
            step_idx = self._rng.randint(0, steps)
            val = spec.min + step_idx * spec.step
        return self._to_type(min(spec.max, max(spec.min, val)), spec)

    def _jitter_mutate(self, old_val: float | int, spec) -> float | int:
        """在附近做小抖动。"""
        jitter = spec.step * (0.5 + self._rng.random() * 0.5)  # 0.5~1.0 倍步长
        direction = 1 if self._rng.random() < 0.5 else -1
        new_val = old_val + direction * jitter
        return self._to_type(new_val, spec)

    def _clamp(self, val: float | int, spec, align_to_step: bool = False) -> float | int:
        val = max(spec.min, min(spec.max, val))
        if align_to_step:
            if isinstance(spec.step, int):
                val = round((val - spec.min) / spec.step) * spec.step + spec.min
            else:
                steps = round((val - spec.min) / spec.step)
                val = spec.min + steps * spec.step
        return self._to_type(val, spec)

    @staticmethod
    def _to_type(val: float, spec) -> float | int:
        """按 spec 的类型保持 int/float。"""
        if isinstance(spec.default, int) and isinstance(spec.step, int):
            return int(round(val))
        return round(val, 4)


def demo() -> None:
    """演示：跑 10 轮变异看看效果。"""
    mutator = ParamMutator(seed=42)
    params = get_defaults()

    print("=== 10 轮步进变异 ===")
    for i in range(10):
        new_params, record = mutator.mutate_one(params, strategy="step")
        params = new_params
        print(f"  [{i + 1}] {record.description}")

    print("\n=== 5 轮双参数变异 ===")
    for i in range(5):
        new_params, records = mutator.mutate_n(params, n=2, strategy="random")
        params = new_params
        for r in records:
            print(f"  [{i + 1}] {r.description}")

    print(f"\n总变异次数: {mutator.mutation_count}")
    params = mutator.reset_to_defaults()
    print(f"重置后参数数量: {sum(len(p) for p in params.values())}")


if __name__ == "__main__":
    demo()
