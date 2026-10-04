# 少妇战法 v1.0 验收参数寻优（v3.7.1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 v3.7.0 验收框架之上，用 V2 达尔文式 self_optimizer 重新寻优，把少妇战法 v1.0 验收门从 1/5 推到 ≥4/5 通过。

**Architecture:** 把 `verify_v10_pipeline(walk_forward=True)` 包装为达尔文可调用的 `V10VerifyScorer`，由新脚本 `scripts/optimize_for_v10_verify.py` 驱动 5 轮 × 100 股 hill-climb，写回 `param_registry:shaofu_v1`，最后用 v3.7.0 `zt verify v1.0` 验收。

**Tech Stack:** Python 3.14 + 现有 Darwin pipeline（`modules/self_optimizer/` + `modules/verify/`）+ 现有 `param_registry`

---

## Global Constraints

1. 五项硬指标阈值（verifies/ 中已有）：Sharpe≥0.5 / Calmar≥0.5 / WinRate≥40% / MaxDD≤25% / OOS/IS≥0.6，**不再调整**
2. 起点 = `LoopConfig()` 默认值（用户决定）
3. 寻优维度 = `LoopConfig` 可调字段：j_threshold / stop_loss_pct / vol_shrink_threshold / bbi_break_days / min_holding_days / lu_half / position_pct
4. 不重写 optimizer；不引入 ML/LLM judge；不动五项阈值
5. WF 必须开启（OOS/IS 门才能有非零分母）
6. 真实数据优先（CLAUDE.md 强约束）：不写 mock，对接 Tushare
7. 不修改 `modules/loop_engine.py`、`modules/backtest_six_step.py`、`modules/verify/{pipeline,gates,walk_forward,registry_writer,report,cli}.py` 既有文件（v3.7.0 已锁）—— 仅追加新文件 + 修改 `__init__.py` 导出
8. 全套测试基线 ≥ 954 passed / 12 skipped（v3.7.0 终态），允许向上增长，不允许下跌
9. SKILL.md 不动（corpus 12/12 强约束）

---

## Spec 自查（已完成）

| 检查 | 状态 |
|---|---|
| 1. 占位符扫描（TBD/TODO/fill-in）| ✅ 无 |
| 2. 内部一致性（架构 ↔ feature ↔ component）| ✅ 一致 |
| 3. Scope check（是否要拆分 sub-project）| ✅ 单 spec 可交付 |
| 4. Ambiguity check（不同解读）| ✅ 上面 5 个核心问题已解析 |

---

## 组件清单（精确文件 + 行数上限）

### 新增

| 文件 | 行数上限 | 职责 |
|---|---|---|
| `modules/verify/scorer.py` | 80 | `V10VerifyScorer` 类，封装 verify_v10_pipeline 作 Darwin-friendly fitness |
| `scripts/optimize_for_v10_verify.py` | 180 | CLI 入口，跑 5×100 + WF，写 registry |
| `tests/test_verify_scorer.py` | 60 | 3 个单测（mocked gates / mocked pipeline / degraded） |

### 修改

| 文件 | 改动 |
|---|---|
| `modules/verify/__init__.py` | 追加导出 `V10VerifyScorer`（不改既有导入） |
| `pyproject.toml` | 版本号 3.7.0 → 3.7.1 |
| `docs/CHANGELOG.md` | 顶部追加 `## v3.7.1 (2026-07-11)` 段 |
| `README.md` | 追加 v3.7.1 行 + 用法说明 |

### 不动（强约束）

`modules/loop_engine.py` / `modules/backtest_six_step.py` / `modules/verify/{pipeline,gates,walk_forward,registry_writer,report,cli}.py` / `modules/self_optimizer/*` 全套既代码。

---

## 核心算法

`V10VerifyScorer.score(params: dict) -> dict` 三步：

```
1. config = LoopConfig(**params)  # 7 字段
2. result = verify_v10_pipeline(
     ts_codes = self.stock_pool,    # 100 只
     days = 240,
     config = config,
     walk_forward = True,
     wf_train_days = 120,
     wf_test_days = 60,
   )
3. gates = result.gates
   return {
     "passed_count": int(sum(g.passed for g in gates.values())),
     "total_count":  len(gates),
     "sharpe":       gates["sharpe"].value,
     "fit":          passed_count + 0.1 * gates["sharpe"].value,
   }
```

**适应度函数**：`fit = passed_count + 0.1 × sharpe`（passed_count 是主要目标，sharpe 小幅 break-tie）。

---

## Milestones

### M1 — Scorer 类（~2h）

| 步骤 | 内容 |
|---|---|
| 1.1 | TDD：写 `test_verify_scorer.py` 三例（mocked gates 返回 5/5，mocked pipeline 抛异常 degraded） |
| 1.2 | 实现 `modules/verify/scorer.py`（`V10VerifyScorer` + `score()` + 异常处理） |
| 1.3 | 跑单测：3/3 通过；跑 lint/format 零错 |
| 1.4 | commit `feat(verify): V10VerifyScorer 接入 verify 管线` |

### M2 — 寻优脚本（~3h）

| 步骤 | 内容 |
|---|---|
| 2.1 | 写 `scripts/optimize_for_v10_verify.py` argparse + 调 SelfOptimizer + 写回 registry |
| 2.2 | 不写脚本级单测（脚本=orchestrator；行为由 M3 E2E 验证） |
| 2.3 | `--smoke` 模式跑：rounds=1, stocks=5，冒烟命令 5 分钟内完成 |
| 2.4 | commit `feat(verify): scripts/optimize_for_v10_verify.py 驱动 5 轮寻优` |

### M3 — 真实数据寻优（~2-3h 跑批）

| 步骤 | 内容 |
|---|---|
| 3.1 | 正式跑：`python3 -m scripts.optimize_for_v10_verify --rounds 5 --stocks 100 --seed 42` |
| 3.2 | 跑批结束标准：5 轮收敛（连续 2 轮无 improvement 后 break）|
| 3.3 | 写 `param_registry:shaofu_v1` 的 active 配置（用 `write_optimization_to_registry`） |
| 3.4 | 中间产物：`optimization_drafts/v10_verify_<timestamp>.json`（含 rounds/best/final） |
| 3.5 | 验证：`LoopConfig.from_registry("shaofu_v1")` 返回非 None |

### M4 — 验收 + 打 v3.7.1 tag（~15 min）

| 步骤 | 内容 |
|---|---|
| 4.1 | 跑 `python3 -m modules.cli verify v1.0 --limit 50 --days 250 --walk-forward` |
| 4.2 | 读最新 JSON 报告，断言 `passed_count >= 4`（严格执行） |
| 4.3 | 若 4.2 失败 → 退回 M3 加 `--extras` 自动跑额外 3 轮；若仍失败 → BLOCKED 上报 |
| 4.4 | 通过：跑全套测试确认 954+ 仍通过（无回归） |
| 4.5 | 文档同步（pyproject/CHANGELOG/README） |
| 4.6 | commit + tag v3.7.1 + 推 origin |

---

## 错误处理矩阵

| 场景 | 行为 |
|---|---|
| 单股 K 线 < 60 天 | `StockResult.skipped` 已存在；scorer 不抛 |
| verify 全部 5 项失败 | `passed_count=0`，fit 仍计算（无负值兜底，因为 passed_count 已超 0） |
| Tushare 速率限制 | SelfOptimizer 内部有重试；上层不处理 |
| ParamRegistry 持久化失败 | 抛异常退出 |
| WF splits < 3 | 现成 degradation；fit 仍计算但 OOS 分项 -1 |
| 寻优 5 轮不收敛 | M3 步骤 3.4 + M4 步骤 4.3 加 `--extras` 自动续跑 3 轮 |
| 总耗时超 3 小时 | M3 步骤 3.2 提示 + M3 步骤 3.5 自动开启 `--extras` |

---

## 测试策略

| 层 | 数量 | 类型 |
|---|---|---|
| Scorer 单测 | 3 | mock-heavy，聚焦 contract |
| M3 端到端 | 1 | 真实跑批结果 = 把 best 写进 registry |
| M4 验收 | 1 | 重跑 v1.0 verify，断言 passed_count ≥ 4 |

**回归基线**：≥ 954 passed / 12 skipped（基线锁定）

---

## 假设（若不实将调整）

1. **Tushare token 可用**（.env 已 set）+ 库内已有 5525 只 stock_basic（验证过）
2. **5 轮 × 100 股 + WF 单跑 ≤ 1.5 小时**（v3.3.0 multifactor 经验值）
3. **少妇战法参数空间足够大**让达尔文爬上可行域（理论：j_threshold ∈ [3, 20]，stop_loss ∈ [-0.10, -0.01] 至少有 200+ 组合）
4. **OOS/IS 门（≥ 0.6）在 WF 切片=3 段时可达成**（若不行，fallback 在 R3 加大 split 数量）

---

## 不在范围（明确排除）

- ❌ 改 v3.7.0 五项阈值
- ❌ 重写 optimizer
- ❌ 引入 LLM judge / ML 评分
- ❌ 改动 `modules/loop_engine.py` / `modules/backtest_six_step.py`
- ❌ SKILL.md 任何改动
- ❌ 自动 deploy / SaaS 化
