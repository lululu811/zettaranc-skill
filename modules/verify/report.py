"""
v1.0 验收报告输出

JSON 是 source of truth，Markdown 由 JSON 渲染。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .pipeline import VerifyResult
from modules.core.paths import REPORTS_DIR


@dataclass
class ReportPaths:
    json_path: Path
    md_path: Path


def render_json(result: VerifyResult) -> str:
    """把 VerifyResult 渲染为 JSON 字符串"""
    data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config_used": result.config_used,
        "config_source": result.meta.get("config_source", "loop_engine:default"),
        "sample": {
            "ts_codes_count": result.meta.get("ts_codes_count", 0),
            "days": result.meta.get("days", 0),
            "skipped_count": result.meta.get("skipped_count", 0),
            "wf_degraded": result.meta.get("wf_degraded", False),
            "wf_splits": result.meta.get("wf_splits", 0),
        },
        "aggregate": asdict(result.aggregate),
        "gates": {name: asdict(g) for name, g in result.gates.items()},
        "passed_count": _gate_counts(result.gates)[0],
        "total_count": _gate_counts(result.gates)[1],
        "summary": _make_summary(result),
        "per_stock": [asdict(s) for s in result.per_stock],
        "meta": result.meta,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _gate_counts(gates: dict) -> tuple[int, int]:
    """统计 (通过数, 适用项总数)。

    **不适用**的项（``applicable=False``，如数据不足算不出 OOS/IS）既不算通过
    也不算失败，且不进分母——否则会出现 "4/5 通过" 但实际 4 项全过的误导。
    """
    applicable = [g for g in gates.values() if getattr(g, "applicable", True)]
    return sum(1 for g in applicable if g.passed), len(applicable)


def render_markdown(result: VerifyResult) -> str:
    """把 VerifyResult 渲染为 Markdown 报告"""
    agg = result.aggregate
    passed, total = _gate_counts(result.gates)

    md = [
        "# 少妇战法 v1.0 验收报告",
        "",
        f"**日期**：{datetime.now().isoformat(timespec='seconds', sep=' ')}",
        f"**样本**：{result.meta.get('ts_codes_count', 0)} 只 × "
        f"{result.meta.get('days', 0)} 天 "
        f"（跳过 {result.meta.get('skipped_count', 0)} 只）",
        "",
        "## 五项硬指标",
        "",
        "| 指标 | 实际 | 阈值 | 判定 |",
        "|------|------|------|------|",
    ]

    label_map = {
        "sharpe": ("Sharpe", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
        "calmar": ("Calmar", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
        "win_rate": ("WinRate", lambda v: f"{v:.1%}", lambda t: f"≥ {t:.0%}"),
        "max_drawdown": ("MaxDD", lambda v: f"{v:.1%}", lambda t: f"≤ {t:.0%}"),
        "oos_is_ratio": ("OOS/IS", lambda v: f"{v:.2f}", lambda t: f"≥ {t:.2f}"),
    }

    for name, gate in result.gates.items():
        label, fmt_v, fmt_t = label_map.get(name, (name, str, str))
        if not getattr(gate, "applicable", True):
            # 不适用：显示 N/A，不给 ✅/❌（既非通过也非未达标）
            md.append(f"| {label} | N/A | {fmt_t(gate.threshold)} | ➖ 不适用 |")
            continue
        icon = "✅" if gate.passed else "❌"
        md.append(f"| {label} | {fmt_v(gate.value)} | {fmt_t(gate.threshold)} | {icon} |")

    md.extend(
        [
            "",
            f"**总评**：{passed}/{total} 通过 {_summary_emoji(passed, total)}",
            "",
        ]
    )

    # 失败项的改进建议（不适用项不算失败）
    failed = [g for g in result.gates.values() if not g.passed and getattr(g, "applicable", True)]
    if failed:
        md.extend(["## 改进建议", ""])
        for g in failed:
            md.append(f"- **{g.name}**：{g.message}")
        md.append("")

    md.extend(
        [
            "## 聚合指标",
            "",
            f"- 总交易：{agg.total_trades}",
            f"- 总收益：{agg.total_return_pct:+.1f}%",
            f"- 年化收益：{agg.annualized_return:+.1f}%",
            f"- 最大回撤：{agg.max_drawdown:.1%}",
            f"- 索提诺：{agg.sortino:.2f}",
            "",
        ]
    )

    return "\n".join(md)


def write_report(
    result: VerifyResult,
    output_dir: Path | str | None = None,
    base_name: str | None = None,
    write_markdown: bool = True,
) -> ReportPaths:
    """写 JSON + Markdown 文件，返回路径"""
    output_dir = Path(output_dir) if output_dir is not None else REPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = base_name or f"verify_v10_{ts}"

    json_path = output_dir / f"{base_name}.json"
    json_path.write_text(render_json(result), encoding="utf-8")

    md_path = output_dir / f"{base_name}.md"
    if write_markdown:
        md_path.write_text(render_markdown(result), encoding="utf-8")

    return ReportPaths(json_path=json_path, md_path=md_path)


def _make_summary(result: VerifyResult) -> str:
    passed, total = _gate_counts(result.gates)
    if total == 0:
        return "无指标"
    if passed == total:
        return f"{passed}/{total} 通过 🎉"
    return f"{passed}/{total} 通过 ⚠️ 待优化"


def _summary_emoji(passed: int, total: int) -> str:
    if total == 0:
        return ""
    if passed == total:
        return "🎉"
    return "⚠️ 待优化"
