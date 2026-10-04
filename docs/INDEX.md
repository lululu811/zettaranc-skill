# docs/INDEX — 文档入口

所有文档以本文件为导航入口。README 面向**项目使用人**（陌生人 5 分钟上手），本索引面向**需要深入的人**。

## 快速路径

| 我想知道… | 去看 |
|---|---|
| 怎么用 CLI / 安装依赖 / 第一次运行 | [README.md](../README.md) → [USER_GUIDE.md](USER_GUIDE.md) |
| 怎么配置环境变量、数据源 key、回测实现切换 | [CONFIG_GUIDE.md](CONFIG_GUIDE.md) |
| 想参与开发 / 提 PR / 写新指标 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 哪个版本改了什么 / 迁移要点 | [CHANGELOG.md](CHANGELOG.md) |
| Web 应用改造规划（进行中） | [WEB_ROADMAP.md](WEB_ROADMAP.md) |
| 回测统计显著性检验框架 | [STATISTICS_VALIDATION.md](STATISTICS_VALIDATION.md) |
| 自我改进系统设计摘要 | [IMPROVEMENT_SYSTEM_SUMMARY.md](IMPROVEMENT_SYSTEM_SUMMARY.md) |
| AI Agent 角色协议（Skill 入口） | [../SKILL.md](../SKILL.md) |
| 知识库（zettaranc 体系，29 篇） | [../knowledge/](../knowledge/) |
| 语料调研 / 原始 reference | [../references/](../references/) |
| 已归档的历史规划 | [_archive/](_archive/) |

## 文档清单

### 活文档（docs/ 顶层，仅这 8 份）

- `USER_GUIDE.md` — 用户手册（CLI、子命令、`--json` 输出、典型工作流）
- `CONFIG_GUIDE.md` — 环境变量、`.env`、数据源切换、回测实现切换
- `CONTRIBUTING.md` — 提交流程、测试、lint、发布 checklist
- `CHANGELOG.md` — 全量变更历史（append-only）
- `WEB_ROADMAP.md` — Web 应用改造规划（进行中，2026-09-06 起）
- `STATISTICS_VALIDATION.md` — 回测统计显著性检验（夏普 t-test / permutation / sub-period）
- `IMPROVEMENT_SYSTEM_SUMMARY.md` — 自我改进系统设计摘要
- `INDEX.md` — 本文件

### 已归档（docs/_archive/）

- `_archive/README.md` — 归档索引
- `_archive/ROADMAP.md` — 产品路线图（2026-07 冻结，迭代排期已由 CHANGELOG 取代）
- `_archive/TODO.md` — 待办清单（主体为已完成归档，停在 v4.1.0）
- `_archive/intent-router-design.md` — 意图路由技术方案 v2（2026-05，实验性，4 个月零更新）
- `_archive/superpowers-2026q2q3/` — 2026 Q2-Q3 工作流产物（plans/ 7 份、specs/ 8 份）

> 归档规则：不再维护的文档移至 `_archive/`，保留 git 历史可回溯。见 [_archive/README.md](_archive/README.md)。

## 维护规则

- 改 `pyproject.toml` 的 `version` → 同步改 `skill.json` / `SKILL.md` / `README.md` badge / `AGENTS.md`
- 新增 CLI 子命令 → 更新 `README.md` CLI 章、`USER_GUIDE.md` 对应章节、`AGENTS.md` 命令列表
- 新增 / 删除文档 → 同步本文件的清单
- 不再维护的文档 → 移至 `_archive/`，并在本文件标注去向
- README 面向使用人，**不放版本流水账、架构细节、项目结构树**；这些分别属于 `CHANGELOG.md` / `AGENTS.md` / 本仓库本身
