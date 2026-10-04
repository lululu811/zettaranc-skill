#!/usr/bin/env python3
"""版本号一致性校验

项目版本号分布在四处，手工同步容易遗漏（v4.3.0 时期曾出现
pyproject 4.3.0 / SKILL.md 4.2.0 的失配）。

校验：pyproject.toml / skill.json / SKILL.md / docs/CHANGELOG.md 顶端
四处版本号必须一致。

用法：
    python scripts/check_version_consistency.py        # 校验
    python scripts/check_version_consistency.py --json # 输出 JSON

退出码：0 = 一致；1 = 不一致或读取失败
在 CI 中调用即可阻断失配的提交。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RE_PYPROJECT = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']', re.M)
RE_SKILLJSON = re.compile(r'"version"\s*:\s*"([^"]+)"')
RE_SKILLMD = re.compile(r"^\s*Version:\s*(\S+)", re.M)
RE_CHANGELOG = re.compile(r"^##\s*\[?v?([\d.]+\d)", re.M)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect() -> dict[str, str | None]:
    """返回 {位置: 版本号}，读取失败为 None"""
    found: dict[str, str | None] = {}

    m = RE_PYPROJECT.search(_read(ROOT / "pyproject.toml"))
    found["pyproject.toml"] = m.group(1) if m else None

    m = RE_SKILLJSON.search(_read(ROOT / "skill.json"))
    found["skill.json"] = m.group(1) if m else None

    text = _read(ROOT / "SKILL.md")
    m = RE_SKILLMD.search(text)
    found["SKILL.md"] = m.group(1) if m else None

    text = _read(ROOT / "docs" / "CHANGELOG.md")
    m = RE_CHANGELOG.search(text)
    found["docs/CHANGELOG.md"] = m.group(1) if m else None

    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="校验项目版本号四处一致")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    found = collect()
    missing = [k for k, v in found.items() if v is None]
    values = {v for v in found.values() if v is not None}
    ok = not missing and len(values) == 1

    if args.json:
        print(json.dumps({"ok": ok, "versions": found}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print("版本号一致性检查")
    print("-" * 46)
    for k, v in found.items():
        print(f"  {k:22} {v if v else '<未找到>'}")
    print("-" * 46)

    if missing:
        print(f"[FAIL] 以下文件未找到版本号: {', '.join(missing)}")
        return 1

    if len(values) > 1:
        print(f"[FAIL] 版本号不一致，发现 {len(values)} 种: {sorted(values)}")
        print("       请统一后重试（发版时需同时改动这四处）")
        return 1

    print(f"[OK] 四处版本号一致: {values.pop()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
