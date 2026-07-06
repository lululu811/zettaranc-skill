"""选股系统命令行入口。"""

import argparse
import time

from .engine import _PARALLEL_THRESHOLD, analyze_stock, screen_stocks
from .format import format_stock_score
from .workflow import daily_workflow


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Z哥 选股系统")
    parser.add_argument(
        "action", choices=["score", "screen", "workflow"], help="操作: score=单股评分, screen=选股, workflow=每日工作流"
    )
    parser.add_argument("--ts_code", help="股票代码")
    parser.add_argument(
        "--criteria",
        default="b1",
        choices=[
            "b1",
            "perfect",
            "breakout",
            "oversold",
            "super_b1",
            "changan",
            "b2_breakout",
            "b3_consensus",
            "build_wave",
            "xishou",
            "safe",
            "bull_rope",
            "sandglass_perfect",
            "volume_ratio_super",
        ],
        help="选股条件",
    )
    parser.add_argument("--limit", type=int, default=10, help="返回数量")
    parser.add_argument("--max-stocks", type=int, default=0, help="最大扫描数量(0=全量)")
    parser.add_argument("--workers", type=int, default=0, help="并行进程数，0=自动（CPU核心数）")
    parser.add_argument("--no-parallel", action="store_true", help="禁用多进程并行")

    args = parser.parse_args()

    if args.action == "score":
        if not args.ts_code:
            print("请指定股票代码: --ts_code 000001.SZ")
            return
        score = analyze_stock(args.ts_code)
        print(format_stock_score(score))

    elif args.action == "screen":
        start = time.time()
        results = screen_stocks(
            criteria=args.criteria,
            max_stocks=args.max_stocks,
            max_workers=args.workers,
            use_parallel=not args.no_parallel,
        )
        elapsed = time.time() - start
        mode = "并行" if not args.no_parallel and len(results) >= _PARALLEL_THRESHOLD else "串行"
        print(f"\n{'=' * 60}")
        print(f"选股结果 ({args.criteria}) 共{len(results)}只 | {mode}模式 | 耗时{elapsed:.1f}s")
        print(f"{'=' * 60}")
        for i, s in enumerate(results[: args.limit], 1):
            print(f"{i:2}. {s.ts_code} {s.name:<8} 评分:{s.score:5.1f}  B1:{s.b1_score:5.1f}")
            if s.reasons:
                print(f"    利好: {', '.join(s.reasons[:2])}")
            if s.warnings:
                print(f"    风险: {', '.join(s.warnings[:1])}")

    elif args.action == "workflow":
        daily_workflow()


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    main()
