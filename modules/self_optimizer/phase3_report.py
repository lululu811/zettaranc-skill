"""Phase 3: 汇总报告 (results.tsv + optimization_drafts/ + improvement_log)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from modules.self_optimizer.phase2_hillclimb import RoundResult

# results.tsv 9 列定义 (与 darwin-skill 对齐)
TSV_HEADER = [
    "timestamp",
    "commit",
    "skill",
    "old_score",
    "new_score",
    "status",
    "dimension",
    "note",
    "eval_mode",
]


def write_results_tsv(
    path: Path,
    run_id: str,
    rounds: list[RoundResult],
) -> Path:
    """写 9 列 results.tsv. 每次 run 追加, 不覆盖历史."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write("\t".join(TSV_HEADER) + "\n")
        for r in rounds:
            row = [
                r.timestamp,
                f"dry_run_{run_id}_r{r.round}",  # V1: 不是真 commit
                "trading",
                f"{r.old_score:.2f}",
                f"{r.new_score:.2f}",
                r.status,
                ",".join(r.violations) if r.violations else "none",
                r.proposed_diff[:80],  # 截断避免 tsv 爆炸
                "dry_run",
            ]
            f.write("\t".join(row) + "\n")
    return path


def write_optimization_draft(
    draft_dir: Path,
    run_id: str,
    result: RoundResult,
) -> Path:
    """生成 optimization_drafts/YYYY-MM-DD-rN.md."""
    draft_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = draft_dir / f"{date_str}-{run_id}-r{result.round}.md"
    content = f"""# Optimization Draft (Round {result.round})

- **Run ID**: {run_id}
- **Timestamp**: {result.timestamp}
- **Status**: {result.status}
- **Old Score**: {result.old_score:.2f}
- **New Score**: {result.new_score:.2f}
- **Delta**: {result.delta:+.2f}

## Proposed Diff

```json
{result.proposed_diff}
```

## Violations

{", ".join(result.violations) if result.violations else "无"}

## Decision Rationale

V1 dry-run: 提议由 HarnessUpdater 生成, 评分由 60% 真实 + 40% LLM stub.
人工 review 后决定合入与否.
"""
    path.write_text(content, encoding="utf-8")
    return path


def append_improvement_log(log_dir: Path, result: RoundResult) -> None:
    """复用现有 ImprovementLogger 写 improvement_log.jsonl."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "improvement_log.jsonl"
    entry = {
        "timestamp": result.timestamp,
        "action": "self_optimization_round",
        "category": "optimization",
        "status": "success" if result.status == "keep" else "reverted",
        "message": f"Round {result.round}: {result.old_score:.2f} -> {result.new_score:.2f} ({result.status})",
        "details": {
            "round": result.round,
            "old_score": result.old_score,
            "new_score": result.new_score,
            "delta": result.delta,
            "violations": result.violations,
        },
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
