"""
zt verify v1.0 CLI 适配层

薄壳：解析参数 + 调 pipeline + 写报告
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .pipeline import VerifyResult, verify_v10_pipeline
from .report import write_report
from modules.core.paths import REPORTS_DIR
from modules.core.errors import ErrorCode, ZettarancError
from modules.loop_engine import LoopConfig

logger = logging.getLogger(__name__)

# 参数默认值与取值范围的唯一来源。
# 顶层 CLI（modules/cli_commands/backtest.py）与本 module 的 argparse 适配层
# 都从这里取，避免同一个默认值写两遍后各自漂移。
DEFAULT_LIMIT = 50
DEFAULT_DAYS = 250
DEFAULT_WF_TRAIN = 120
DEFAULT_WF_TEST = 60

LIMIT_RANGE = (10, 500)
DAYS_RANGE = (120, 1000)
WF_TRAIN_RANGE = (60, 500)
WF_TEST_RANGE = (30, 200)


def _bounded_int(min_v: int, max_v: int):
    """argparse 类型：限制整数范围，超出则抛 ArgumentTypeError（argparse 内部转 SystemExit）"""

    def _check(value: str) -> int:
        try:
            ivalue = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc))
        if not min_v <= ivalue <= max_v:
            raise argparse.ArgumentTypeError(f"必须在 [{min_v}, {max_v}]，当前 {ivalue}")
        return ivalue

    return _check


def build_parser() -> argparse.ArgumentParser:
    """构造 zettaranc verify 命令的 argparse 解析器（全部子命令与参数）。"""
    parser = argparse.ArgumentParser(
        prog="zt verify v1.0",
        description="少妇战法 v1.0 验收一键命令",
    )
    parser.add_argument(
        "--limit",
        type=_bounded_int(*LIMIT_RANGE),
        default=DEFAULT_LIMIT,
        help=f"股票数（默认 {DEFAULT_LIMIT}，范围 {list(LIMIT_RANGE)}）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"回测天数（默认 {DEFAULT_DAYS}，范围 {list(DAYS_RANGE)}）",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="启用 Walk-forward 验证",
    )
    parser.add_argument(
        "--wf-train",
        type=int,
        default=DEFAULT_WF_TRAIN,
        help=f"WF IS 窗口天数（默认 {DEFAULT_WF_TRAIN}）",
    )
    parser.add_argument(
        "--wf-test",
        type=int,
        default=DEFAULT_WF_TEST,
        help=f"WF OOS 窗口天数（默认 {DEFAULT_WF_TEST}）",
    )
    parser.add_argument(
        "--ts-codes",
        type=str,
        default=None,
        help="指定股票列表（逗号分隔），默认从 stock_basic 选前 N 只",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="只输出 JSON 到 stdout",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="不写 Markdown 报告文件",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPORTS_DIR),
        help=f"报告输出目录（默认 {REPORTS_DIR}）",
    )
    return parser


def _validate_params(
    limit: int = DEFAULT_LIMIT,
    days: int = DEFAULT_DAYS,
    wf_train_days: int = DEFAULT_WF_TRAIN,
    wf_test_days: int = DEFAULT_WF_TEST,
) -> None:
    """校验 v1.0 验收参数；非法抛 ZettarancError(INVALID_PARAM)。

    范围与各 *_RANGE 常量一致。以前同一组范围在 argparse 的 _bounded_int
    与 _validate_args 里各写一遍，改一处漏一处就会让两个入口行为分叉。
    """
    checks = (
        (limit, LIMIT_RANGE, "--limit"),
        (days, DAYS_RANGE, "--days"),
        (wf_train_days, WF_TRAIN_RANGE, "--wf-train"),
        (wf_test_days, WF_TEST_RANGE, "--wf-test"),
    )
    for value, (lo, hi), name in checks:
        if not lo <= value <= hi:
            raise ZettarancError(ErrorCode.INVALID_PARAM, f"{name} 必须在 [{lo}, {hi}]，当前 {value}")


def _split_ts_codes(ts_codes_arg: str | None) -> list[str]:
    """把逗号分隔的股票代码串拆成列表（空串返回空列表）。"""
    if not ts_codes_arg:
        return []
    return [c.strip() for c in ts_codes_arg.split(",") if c.strip()]


def run_verify_v10(
    ts_codes: list[str] | None = None,
    days: int = 250,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: LoopConfig | None = None,
    write_markdown: bool = True,
    output_dir: Path | str | None = None,
    use_portfolio_engine: bool = True,
) -> VerifyResult:
    """CLI 入口函数（也可被 Python API 直接调用）

    ``use_portfolio_engine`` 默认 True —— 验收走**真组合**（共享资金池 +
    交易费率 + 闸门），与自优化器 ``V10VerifyScorer`` 的默认一致。此前 CLI
    走的是逐股独立回测 + 等权合并曲线（无费率、无仓位约束），于是
    **优化器优化的目标与验收报告的数字不是同一个引擎算出来的**。
    """
    result = verify_v10_pipeline(
        ts_codes=ts_codes or [],
        days=days,
        config=config,
        walk_forward=walk_forward,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        use_portfolio_engine=use_portfolio_engine,
    )
    if write_markdown or output_dir:
        write_report(result, output_dir=output_dir, write_markdown=write_markdown)
    return result


def run_verify_v10_command(
    *,
    ts_codes_arg: str | None = None,
    limit: int = DEFAULT_LIMIT,
    days: int = DEFAULT_DAYS,
    walk_forward: bool = False,
    wf_train_days: int = DEFAULT_WF_TRAIN,
    wf_test_days: int = DEFAULT_WF_TEST,
    write_markdown: bool = True,
    output_dir: Path | str | None = None,
    as_json: bool = False,
) -> int:
    """执行 v1.0 验收并输出结果；返回进程退出码（0 成功，2 参数非法）。

    **zt verify 的唯一执行入口**：argparse 适配层（本 module 的 ``main``）与
    顶层 CLI（``modules/cli_commands/backtest.py::cmd_verify_v10``）都调它。

    这样参数校验、报告输出目录、退出码只有一处定义。此前顶层 CLI 把已经
    解析好的参数重新拼成 argv 交给第二个 argparse，既漏转发 ``--output``，
    又让退出码在两层之间丢失。
    """
    try:
        _validate_params(
            limit=limit,
            days=days,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
        )
    except ZettarancError as e:
        print(f"参数错误：{e}")
        return 2

    ts_codes = _split_ts_codes(ts_codes_arg)
    if not ts_codes:
        from modules.database import get_all_stock_codes

        ts_codes = get_all_stock_codes(limit=limit)

    result = run_verify_v10(
        ts_codes=ts_codes,
        days=days,
        walk_forward=walk_forward,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
        write_markdown=write_markdown,
        output_dir=output_dir,
        use_portfolio_engine=True,
    )

    if as_json:
        from .report import render_json

        print(render_json(result))
    else:
        passed = sum(1 for g in result.gates.values() if g.passed)
        total = len(result.gates)
        print(f"\n少妇战法 v1.0 验收：{passed}/{total} 通过")
        print(f"报告：{output_dir or REPORTS_DIR}/verify_v10_<timestamp>.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：解析命令行参数并执行验收。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_verify_v10_command(
        ts_codes_arg=args.ts_codes,
        limit=args.limit,
        days=args.days,
        walk_forward=args.walk_forward,
        wf_train_days=args.wf_train,
        wf_test_days=args.wf_test,
        write_markdown=not args.no_markdown,
        output_dir=args.output,
        as_json=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
