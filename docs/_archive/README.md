# docs/_archive

历史归档：以下内容是 2026 Q2–Q3 superpowers 工作流产物，**仅作考古参考**。

## 索引

### superpowers 工作流产物（2026 Q2–Q3）

- `superpowers-2026q2q3/` — 历史 superpowers 工作流输出（Darwin 自优化、模拟器 v0.2/v0.3/v0.4、少妇战法 v1.0、Rust 重构等）。当时的目标已被 v4.3.0 全部超越。

### 冻结的规划文档（2026-09-30 归档）

- `ROADMAP.md` — 产品路线图，2026-07 冻结。迭代排期已由 `CHANGELOG.md` 取代，不再更新。
- `TODO.md` — 待办清单，主体为「✅ 已完成」归档，版本停在 v4.1.0。新增待办请写进 CHANGELOG。
- `intent-router-design.md` — 意图路由技术方案 v2，2026-05 完成，4 个月零更新且标注为实验性。

## 当前项目状态

权威状态源：

- 版本号：`pyproject.toml` 顶部 `version = "..."`（当前 4.3.0）
- 变更日志：`docs/CHANGELOG.md`
- 文档入口：`docs/INDEX.md`
- 角色协议：`SKILL.md`

## 为什么归档

`docs/superpowers/` 在项目早期承载了工作流文档（plan/spec），但代码层与文档层都已超过其内容；保留会增加读者负担。

2026-09-30 补充：`ROADMAP.md` / `TODO.md` / `intent-router-design.md` 同样因零更新归档，遵循 `docs/INDEX.md` 的「不再维护的文档 → 移至 `_archive/`」规则。

归档后这些文件仍可通过 `git log --follow -- docs/_archive/<file>` 找回历史上下文。