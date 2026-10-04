"""CLI screen 子命令实现。"""

from __future__ import annotations

import logging

from ._helpers import json_output
from .strategy_alias import STRATEGY_ALIAS

logger = logging.getLogger(__name__)


def cmd_screen(args) -> None:
    """筛选股票（调 screener.screen_stocks）

    Rust 路径：screen_stocks 暂未封装为 PyO3 binding（v4.0.1），所以 Rust 优先
    计算的单项评分函数（`compute_atr_py` 等）暂未在 CLI 暴露；当 `screen_stocks_py`
    PyO3 binding 落地后（v4.1+），这里可直接 bridge。
    当前行为：保持 Python `screen_stocks` 路径不动（无需回退检查）。
    """
    from modules.screener import screen_stocks

    criteria = STRATEGY_ALIAS.get(args.strategy, args.strategy)

    # 预留 Rust hook：未来 v4.1+ 可在此处
    # `from modules.backtest._rust_bridge import compute_func`
    # `rust_screen = compute_func("screen_stocks_py")`
    # 若 rust_screen 不为 None 即可走 Rust。

    # 运行时参数覆盖：--param KEY=VALUE（可重复），键名取自 param_registry
    raw_params = getattr(args, "param", None) or []
    overrides: dict[str, float] = {}
    for item in raw_params:
        if "=" not in item:
            print(f"忽略无效参数（需 KEY=VALUE 形式）: {item}")
            continue
        key, _, value = item.partition("=")
        try:
            overrides[key.strip()] = float(value)
        except ValueError:
            print(f"忽略无效参数值（需数字）: {item}")

    # 参数组名与 criteria 同名（simple_perfect_1/2/3 各自成组）
    param_group = criteria

    def _run():
        return screen_stocks(
            criteria=criteria,
            max_stocks=args.limit if args.limit > 0 else 0,
            use_parallel=not args.no_parallel,
        )

    if overrides:
        try:
            from modules.self_optimizer.param_registry import get_registry, using_params

            group = get_registry().get(param_group)
            if group:
                clean = {k: v for k, v in overrides.items() if k in group.params}
                with using_params({param_group: clean}):
                    results = _run()
            else:
                results = _run()
        except (ImportError, TypeError, ValueError) as e:
            logger.warning("[screen] 参数覆盖失败，按默认值运行: %s", e)
            results = _run()
    else:
        results = _run()

    # limit=扫描数量；--top=返回条数（0=全部命中）
    top = getattr(args, "top", 0) or 0
    output_limit = top if top > 0 else len(results)

    # ── JSON 输出 ──
    if args.json:
        json_result = {
            "criteria": criteria,
            "count": len(results[:output_limit]),
            "stocks": [
                {
                    "ts_code": r.ts_code,
                    "name": r.name,
                    "score": r.score,
                    "rating": r.rating,
                    "reasons": getattr(r, "reasons", []) or [],
                    "warnings": getattr(r, "warnings", []) or [],
                }
                for r in results[:output_limit]
            ],
        }
        json_output(json_result)
        return

    # ── 人类可读输出（保持原样） ──
    print(f"\n{'=' * 60}")
    print(f"股票筛选 (criteria={criteria}, 上限={args.limit or '全市场'})")
    print(f"{'=' * 60}")
    print(f"\n扫描完成，命中: {len(results)} 只\n")

    for r in results[:output_limit]:
        print(f"  {r.ts_code:<12} {r.name:<8} score={r.score:.1f}  {r.rating}")
        reasons = getattr(r, "reasons", []) or []
        warnings = getattr(r, "warnings", []) or []
        if reasons:
            print(f"    reasons: {','.join(reasons[:3])}")
        if warnings:
            print(f"    warnings: {','.join(warnings[:3])}")
