"""CLI diagnose + workflow 子命令实现。"""

from __future__ import annotations

from ._helpers import json_output


def cmd_workflow(args) -> None:
    """每日五步工作流（来自 screener.py workflow action）"""
    from modules.screener import daily_workflow

    daily_workflow()


def cmd_diagnose(args) -> None:
    """持仓诊断"""
    from modules.portfolio_diagnosis import diagnose_stock, format_report

    ts_code = args.ts_code
    diagnosis = diagnose_stock(ts_code, days=args.days)

    # ── JSON 输出 ──
    if args.json:
        from dataclasses import asdict

        json_output(asdict(diagnosis))
        return

    # ── 人类可读输出（保持原样） ──
    print(format_report(diagnosis))
