"""
zt verify v1.0 CLI 适配层

薄壳：解析参数 + 调 pipeline + 写报告
"""

from __future__ import annotations

import argparse
import logging

from .pipeline import VerifyResult, verify_v10_pipeline
from .report import write_report
from modules.core.paths import REPORTS_DIR
from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)


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
    parser = argparse.ArgumentParser(
        prog="zt verify v1.0",
        description="少妇战法 v1.0 验收一键命令",
    )
    parser.add_argument(
        "--limit",
        type=_bounded_int(10, 500),
        default=50,
        help="股票数（默认 50，范围 [10, 500]）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=250,
        help="回测天数（默认 250，范围 [120, 1000]）",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="启用 Walk-forward 验证",
    )
    parser.add_argument(
        "--wf-train",
        type=int,
        default=120,
        help="WF IS 窗口天数（默认 120）",
    )
    parser.add_argument(
        "--wf-test",
        type=int,
        default=60,
        help="WF OOS 窗口天数（默认 60）",
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


def _validate_args(args: argparse.Namespace) -> None:
    if not 10 <= args.limit <= 500:
        raise ZettarancError(ErrorCode.INVALID_PARAM, f"--limit 必须在 [10, 500]，当前 {args.limit}")
    if not 120 <= args.days <= 1000:
        raise ZettarancError(ErrorCode.INVALID_PARAM, f"--days 必须在 [120, 1000]，当前 {args.days}")
    if args.wf_train < 60 or args.wf_train > 500:
        raise ZettarancError(ErrorCode.INVALID_PARAM, f"--wf-train 必须在 [60, 500]，当前 {args.wf_train}")
    if args.wf_test < 30 or args.wf_test > 200:
        raise ZettarancError(ErrorCode.INVALID_PARAM, f"--wf-test 必须在 [30, 200]，当前 {args.wf_test}")


def _resolve_ts_codes(args: argparse.Namespace) -> list[str]:
    """解析股票列表（指定 / 默认从 stock_basic 取）"""
    if args.ts_codes:
        return [c.strip() for c in args.ts_codes.split(",") if c.strip()]
    # 默认从 stock_basic 取前 N 只（lazy import 避免循环）
    from modules.database import get_all_stock_codes

    all_codes = get_all_stock_codes(limit=args.limit)
    return all_codes


def run_verify_v10(
    ts_codes: list[str] | None = None,
    days: int = 250,
    walk_forward: bool = False,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
    write_markdown: bool = True,
    output_dir: str | None = None,
) -> VerifyResult:
    """CLI 入口函数（也可被 Python API 直接调用）"""
    result = verify_v10_pipeline(
        ts_codes=ts_codes or [],
        days=days,
        config=config,
        walk_forward=walk_forward,
        wf_train_days=wf_train_days,
        wf_test_days=wf_test_days,
    )
    if write_markdown or output_dir:
        write_report(result, output_dir=output_dir, write_markdown=write_markdown)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _validate_args(args)
    except ValueError as e:
        print(f"参数错误：{e}")
        return 2

    ts_codes = _resolve_ts_codes(args)
    result = run_verify_v10(
        ts_codes=ts_codes,
        days=args.days,
        walk_forward=args.walk_forward,
        wf_train_days=args.wf_train,
        wf_test_days=args.wf_test,
        write_markdown=not args.no_markdown,
        output_dir=args.output,
    )

    if args.json:
        from .report import render_json

        print(render_json(result))
    else:
        passed = sum(1 for g in result.gates.values() if g.passed)
        total = len(result.gates)
        print(f"\n少妇战法 v1.0 验收：{passed}/{total} 通过")
        print(f"报告：{args.output}/verify_v10_<timestamp>.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
