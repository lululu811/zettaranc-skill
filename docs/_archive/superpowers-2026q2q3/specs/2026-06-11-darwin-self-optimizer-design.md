# Darwin Self-Optimizer 集成设计

> **状态**：Draft v1 · 待用户复核
> **创建日期**：2026-06-11
> **作者**：Claude (brainstorming with chenlei)
> **目标分支**：`feature/darwin-self-optimizer`（从 `main` 拉出）
> **预计工作量**：V1 5 天 + V2 1-2 周

---

## 1. 背景与目标

### 1.1 现状

zettaranc-skill 已具备自我改进的部分基础设施：

| 模块 | 状态 | 局限 |
|---|---|---|
| `modules/harness_updater.py` | ✅ 已实现 | 强制人工审核（`apply_guardrails_updates` 注释显式声明） |
| `modules/improvement_logger.py` | ✅ 已实现 | JSONL 自由格式，无结构化列 |
| `corpus/quality_check.py` | ✅ 8 项硬规则 | binary pass/fail，颗粒粗 |
| `docs/CHANGELOG.md` | ✅ 完整 | 人工维护 |
| 月度复盘数据 | ✅ 真实 | `monthly_reviews_self` 26 万+ 条 |

### 1.2 缺失的核心能力（来自 darwin-skill v2.0）

- **ratchet（棘轮）**：分数只升不降，自动回滚退步
- **reflex_blacklist（8 条反例）**：硬阻断常见踩坑
- **break_signal（触顶）**：连续 2 轮 Δ<2 自动停手
- **paired within-judge**：抗 LLM judge 噪声（PR #13 教训）
- **结构化 results.tsv**：9 列可审计日志

### 1.3 目标

**V1**：在 `feature/darwin-self-optimizer` 分支上交付 `modules/self_optimizer/` 子包，集成 ratchet + reflex_blacklist + break_signal，dry-run 模式，**不修改 SKILL.md**，产 `optimization_drafts/` + `results.tsv` 供人工 review。

**V2**（V1 跑稳后启动）：接 `git revert` 真自动模式 + CI 周更 cron + 反例黑名单扩到 12+。

### 1.4 不在范围

- 不改造 `corpus/quality_check.py`（保持 binary 不动）
- 不做 Web UI
- 不做分布式评分
- 不做多目标优化
- 不动 SKILL.md（V1 期间）

---

## 2. 架构

### 2.1 数据流

```
┌────────────────────────────────────────────────────────────────┐
│  输入                                                           │
├────────────────────────────────────────────────────────────────┤
│  monthly_reviews_self 表（最近 N 个月复盘）                      │
│  tracking_pool_self 表（策略标签）                              │
│  SKILL.md（当前版本）                                           │
│  llm_providers.py（API 配置）                                   │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Phase 1: 基线                                                  │
├────────────────────────────────────────────────────────────────┤
│  monthly_reviews_self  ──┐                                       │
│                          ├─→ compute_trading_score (0-60)       │
│  SKILL.md 当前 Guardrails ┘                                      │
│                                                                   │
│  baseline_guardrails   ──→ compute_llm_score (paired None,       │
│                                            默认分 20/40)         │
│                                                                   │
│  baseline_score = 60分项 + 20分项 = 80                          │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Phase 2: hill-climbing (round 1-3)                             │
├────────────────────────────────────────────────────────────────┤
│  HarnessUpdater.analyze_strategy_performance()                  │
│       ↓                                                          │
│  generate_guardrails_update()                                   │
│       ↓                                                          │
│  reflex_blacklist.check_all()  ← 任何触发直接 revert            │
│       ↓                                                          │
│  compute_total_score(new_proposal) → new_score                  │
│       ↓                                                          │
│  compare: new_score > old_score?                                │
│    ├─ Yes: keep → 写 results.tsv (status=keep)                  │
│    └─ No:  revert → 写 results.tsv (status=revert)             │
│       ↓                                                          │
│  check_break_signal(history)  ← 连续 2 轮 Δ<2 → break          │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  Phase 3: STOP CHECKPOINT                                        │
├────────────────────────────────────────────────────────────────┤
│  results.tsv  ──→  gitignored 由人工 commit                      │
│  optimization_drafts/  ──→ gitignored                            │
│  improvement_log.jsonl  ──→ gitignored (已存在)                  │
│                                                                   │
│  CLI 提示:                                                       │
│    ✓ Phase 3 done. 3 rounds, 1 keep / 1 revert / 1 break        │
│    📄 results.tsv: logs/results.tsv                              │
│    📝 draft: optimization_drafts/2026-06-11-r1.md               │
│    ⚠️  请人工 review 后决定合入                                   │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 模块分层

| 文件 | 职责 | 行数估计 |
|---|---|---|
| `modules/self_optimizer/__init__.py` | 公共 API + SelfOptimizer 类 | 60 |
| `modules/self_optimizer/phase1_baseline.py` | 基线评估 | 80 |
| `modules/self_optimizer/phase2_hillclimb.py` | 迭代优化 | 120 |
| `modules/self_optimizer/phase3_report.py` | 汇总报告 | 60 |
| `modules/self_optimizer/scorer.py` | 60% 硬规则 + 40% LLM | 100 |
| `modules/self_optimizer/reflex_blacklist.py` | 8 条反例检查 | 80 |
| `modules/self_optimizer/llm_judge.py` | paired within-judge | 50 |
| `modules/cli.py` 扩展 | `self-optimize` 子命令 | +30 |

**总代码量约 580 行** + 200 行测试 = **780 行**。

---

## 3. 组件接口

### 3.1 `SelfOptimizer` 公共 API

```python
class SelfOptimizer:
    def __init__(
        self,
        target: str = "trading",         # trading | skill
        rounds: int = 3,
        mode: str = "dry_run",           # dry_run | auto_revert
        review_months: int = 3,
    ):
        ...

    def run(self) -> dict:
        """Phase 1 → 2 → 3 完整跑一次"""

    def phase1_baseline(self) -> float:
        """返回 baseline_score, 0-100"""

    def phase2_hillclimb(self, baseline: float) -> list[RoundResult]:
        """返回每轮 RoundResult(keep/revert/break, old, new, delta)"""

    def phase3_report(self, rounds: list) -> Path:
        """生成 results.tsv + optimization_drafts/ + log jsonl"""
```

### 3.2 `scorer.py` 核心公式

```python
def compute_trading_score(review_month: str, n_months: int = 3) -> float:
    """60% 真实数据 (0-60):
       - 30% 月度平均胜率 (clamp 到 [-10%, 10%] → [0, 30])
       - 30% 平均回撤反向 (回撤 <10% 满分, >50% 零分)
       - 40% 信号准确率
       返回 0-60"""

def compute_llm_score(proposed_updates: list[dict]) -> float:
    """40% LLM 评审 (0-40):
       paired within-judge, 1 轮多数决
       返回 0-40"""

def compute_total_score(review_month: str, proposed: list[dict]) -> tuple[float, dict]:
    """返回 (total, breakdown)"""
```

### 3.3 `reflex_blacklist.py` 8 条反例

| # | 反例 | 检测逻辑 |
|---|---|---|
| 1 | 胜率<-10% 仍标 good | `check_status_consistency(proposed, expected="poor")` |
| 2 | stock_count<5 强行评估 | `check_min_sample_size(analysis, min_n=5)` |
| 3 | 回撤>20% 仍未标 risky | `check_drawdown_warning(proposed, threshold=20)` |
| 4 | LLM judge 读了 harness 自己的输出 | `check_judge_isolation(llm_input)` |
| 5 | 异常被 swallow 而非 raise | `check_exception_visibility(execution_log)` |
| 6 | 单轮改 >2 个策略标签 | `check_single_proposal_scope(proposed, max_n=2)` |
| 7 | dry-run 比例 >30% | `check_dryrun_ratio(history, threshold=0.3)` |
| 8 | 只用 LLM judge 未参考 monthly_reviews_self | `check_real_data_weight(scoring, min_real_weight=0.6)` |

```python
TRADING_BLACKLIST: list[tuple[str, str, Callable]] = [
    ("high_return_no_warning", "...", lambda ctx: ...),
    ...
]

def check_all(context: dict) -> list[Violation]:
    """返回所有触发的反例 (空列表 = 通过)"""
```

### 3.4 `phase2_hillclimb.py`

```python
@dataclass
class RoundResult:
    round: int
    old_score: float
    new_score: float
    delta: float
    status: Literal["keep", "revert", "break"]
    violations: list[str]
    proposed_diff: str
    timestamp: str

def run_round(
    round_n: int,
    old_score: float,
    current_proposal: dict,
    history: list[RoundResult],
) -> RoundResult:
    """单轮迭代:
       1. reflex_blacklist.check_all() → 任何触发直接 status=revert
       2. compute_total_score(proposed) → new_score
       3. if new_score > old_score: keep; else: revert
       4. if 连续 2 轮 delta<2: break
       5. V1 写 optimization_drafts/; V2 调 git_revert()"""

def check_break_signal(history: list[RoundResult], threshold: float = 2.0) -> bool:
    """连续 2 轮 delta < threshold → True"""
```

### 3.5 `llm_judge.py`

```python
def paired_judge(before: str, after: str, prompt_template: str) -> bool:
    """1 轮 paired within-judge:
       - 同一 call 里同时给 before+after
       - 返回 True (after 更好) / False
       - 显式禁止单边评分 (避免 PR #13 误报)
       - 复用 modules/llm_providers.py"""

def compute_llm_score_with_baseline(baseline: dict, new: dict) -> float:
    """返回 0-40"""
```

### 3.6 CLI 扩展

```bash
# 跑一次
python -m modules.cli self-optimize run --rounds 3 --target trading

# 查看状态
python -m modules.cli self-optimize status

# 手动回滚
python -m modules.cli self-optimize rollback <round>

# 重置 state
python -m modules.cli self-optimize reset
```

---

## 4. 错误处理

| 错误类型 | 触发条件 | 行为 | 落到哪 |
|---|---|---|---|
| LLM judge 失败 | API 超时/限流/解析错误 | 用上一次成功 fallback + 标记 `eval_mode=degraded` | `results.tsv` eval_mode 列 |
| 数据库无数据 | `monthly_reviews_self` 为空 | 立即 STOP，提示"至少需要 1 个完整月份复盘" | stderr + exit 2 |
| stock_count < 5 | 单策略样本不足 | 该策略标 `low_sample` 跳过评估 | `improvement_log.jsonl` warning |
| reflex_blacklist 触发 | 8 条任一 | 强制 `status=revert` + 写 violation detail | `results.tsv` note 列 |
| 断点/中断 | Ctrl-C / 进程 kill | 已写 `results.tsv` 保留，下次 run 从下一个 round 继续 | `results.tsv` + state.json |
| 连续 3 轮 break | 触顶信号 | 立即 STOP，提示"评分已饱和，建议转人工" | stderr + exit 0 |
| Git 冲突（V2 才有） | 优化期间 SKILL.md 被改 | 强制 abort，提示"请先 pull 再 run" | stderr + exit 1 |

### 幂等性 + 状态恢复

```json
// logs/self_optimizer_state.json
{
  "run_id": "2026-06-11-r3",
  "started_at": "2026-06-11T07:30:00",
  "target": "trading",
  "mode": "dry_run",
  "current_round": 2,
  "baseline_score": 80.0,
  "rounds": [
    {"round": 1, "old": 80.0, "new": 82.5, "delta": 2.5, "status": "keep"},
    {"round": 2, "old": 82.5, "new": 83.1, "delta": 0.6, "status": "revert"}
  ]
}
```

- 断点恢复：下次 run 检测 `state.json` 存在 → 询问"从 round X 继续还是重置？"
- 重置：`python -m modules.cli self-optimize reset`
- 状态永久保留，每次 run 一份

---

## 5. 测试策略

### 5.1 测试金字塔

```
                    ▲
                   ╱ ╲
                  ╱ E2E ╲         1 个 (test_self_optimizer_e2e.py)
                 ╱ 真实 DB╲
                ╱──────────╲
               ╱  集成测试   ╲    3 个
              ╱ scorer+blacklist ╲
             ╱   +llm_judge stub  ╲
            ╱──────────────────────╲
           ╱     单元测试             ╲   12 个
          ╱  reflex_blacklist(8)        ╲
         ╱   scorer(2) + break_signal(2) ╲
        ╱──────────────────────────────────╲
```

### 5.2 单元测试（12 个）

| 文件 | 测试 | 覆盖 |
|---|---|---|
| `tests/test_reflex_blacklist.py` | `test_high_return_no_warning` | 反例 #1 |
| | `test_low_sample_size` | #2 |
| | `test_high_drawdown_no_limit` | #3 |
| | `test_self_eval_context` | #4 |
| | `test_silent_exception` | #5 |
| | `test_multi_strategy_mutation` | #6 |
| | `test_dry_run_overload` | #7 |
| | `test_ignore_real_signal` | #8 |
| `tests/test_scorer.py` | `test_trading_score_60pct` | 60% 真实分公式 |
| | `test_trading_score_clamping` | 极端值 clamp |
| `tests/test_break_signal.py` | `test_two_consecutive_small_delta` | Δ<2 触发 break |
| | `test_one_small_one_large` | 不触发 break |

### 5.3 集成测试（3 个）

```python
# tests/test_self_optimizer_integration.py

def test_phase1_baseline_with_mock_data():
    """mock 3 个月 monthly_reviews_self 数据
       验证 baseline_score 在 [0, 100]"""

def test_phase2_keep_revert_cycle():
    """mock 一个会让 new_score < old_score 的提议
       验证 status=revert + results.tsv 写入正确"""

def test_phase2_break_signal():
    """连续 3 轮 delta<2
       验证 round 3 返回 status=break + 进程优雅退出"""
```

### 5.4 E2E（1 个）

```python
# tests/test_self_optimizer_e2e.py
# @pytest.mark.slow

def test_full_run_dry_run(tmp_db, temp_skill_file):
    """端到端:
       1. 初始化 mock DB + 3 个月复盘数据
       2. python -m modules.cli self-optimize run --rounds 3
       3. 验证:
          - results.tsv 存在且 9 列格式正确
          - optimization_drafts/ 有 3 个 .md
          - improvement_log.jsonl 有 3 条记录
          - SKILL.md 未被修改 (V1 dry-run 强制)
          - state.json 可被下次 run 恢复"""
```

### 5.5 关键 fixture

```python
# tests/conftest.py 扩展

@pytest.fixture
def mock_monthly_reviews_with_poor_strategy():
    """stock_count=1 胜率 -30% → 触发反例 #2 (低样本)"""

@pytest.fixture
def mock_llm_judge_degraded():
    """mock LLM API TimeoutError → 验证 fallback"""

@pytest.fixture
def state_with_interrupted_run():
    """上次 run 到 round 2 中断 → 验证下次 run 询问恢复"""
```

### 5.6 CI 集成

```yaml
# .github/workflows/test.yml 扩展

- name: Self-optimizer tests
  run: python -m pytest tests/test_reflex_blacklist.py tests/test_scorer.py tests/test_break_signal.py -v

- name: Self-optimizer slow tests
  run: python -m pytest tests/ -v -k self_optimizer --tb=short
  continue-on-error: true  # 观察期
```

**总测试数：~383（现有 367 + 新增 16）**。**LLM judge 必须 stub**——不能在 CI 里真打 API。

---

## 6. 实施路径

### 6.1 V1（5 天）

| Day | 任务 | 验收 |
|---|---|---|
| 1 | 骨架 + 8 条反例 + 12 个单测 | `pytest tests/test_reflex_blacklist.py -v` 全过 |
| 2 | phase1_baseline + scorer 60% 真实分 + 集成测试 #1 | baseline 在 [0, 100] |
| 3 | phase2_hillclimb + ratchet + break_signal + 集成测试 #2/#3 | keep/revert/break 三态都跑出 |
| 4 | phase3_report + results.tsv + drafts + state + CLI | E2E `test_full_run_dry_run` 过 |
| 5 | CI 集成 + 真实 dry-run 一轮 | CLI 跑通，结果写入正确 |

### 6.2 V1 验收门

- [ ] **16 个新测试全过**
- [ ] **真实数据 dry-run 一轮 ≤ 30 秒**（LLM judge 5s timeout）
- [ ] **results.tsv 9 列格式与 darwin 对齐**
- [ ] **SKILL.md 在 V1 期间零修改**（dry-run 强制）
- [ ] **state.json 可恢复**
- [ ] **在 `feature/darwin-self-optimizer` 分支上完成**（不污染 main）
- [ ] **PR 合入 main 前必须经人工 review**

### 6.3 V2 范围（V1 跑稳后启动，1-2 周）

| 任务 | 必要性 | 风险 |
|---|---|---|
| 接 `git revert` 真自动模式 | 必备 | 中 |
| CI 周更 cron（每周日 03:00） | 推荐 | 低 |
| 反例黑名单扩到 12+ | 必备 | 低 |
| paired within-judge 改 N=3 多数决 | 推荐 | 中 |

### 6.4 V2 启动门

- [ ] V1 dry-run 跑过 4 周无重大异常
- [ ] 人工 review 至少 3 次 optimization_drafts/，认可 ≥ 60% 提议
- [ ] 反例黑名单触发率 ≤ 20%
- [ ] LLM judge 失败率 ≤ 10%

---

## 7. 风险登记册

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM judge 评分波动大 | 中 | 中 | paired within-judge + 40% 权重 + V1 观察 |
| 反例黑名单触发率过高 | 中 | 低 | V1 dry-run 影响小；V2 上 git revert 后再观察 |
| monthly_reviews_self 数据不足 | 低 | 高 | stock_count<5 跳过 + 数据库空立即 STOP |
| CI 周更引发不可控 git 历史 | 低 | 中 | V2 才上 cron，V1 纯手动 |
| 评分系统本身有 bug 导致"伪提升" | 中 | 中 | V1 期间人工 review 100% 提议 |
| 分支合并冲突 | 中 | 低 | V1 在独立 feature 分支；V1 完成后合 main 一次 |

---

## 8. YAGNI 清单（明确不做）

- ❌ Web UI（CLI + Markdown 报告足够）
- ❌ 分布式评分（单机足够）
- ❌ 多目标优化（单目标：总分最大化）
- ❌ 实时调度（CI 周更 + 手动触发足够）
- ❌ 改造 `corpus/quality_check.py`（保持 binary 不动）
- ❌ Phase 0.5 test-prompts 设计（有 367 个真实测试）
- ❌ 多 LLM provider 适配（复用 `llm_providers.py`）
- ❌ SKILL.md 真自动修改（V2 才考虑）
- ❌ 跨 runtime 适配性审查（darwin 的 gate 项，与 trading 目标无关）

---

## 9. 引用来源

- **darwin-skill 深度研究**：worktree `/private/tmp/claude-501/-Users-chenlei-005-skill-skills-zettaranc-skill/90666b4d-ff0e-496c-8e64-558b8c1c2b15/tasks/wvu6gkhhj.output`
- **darwin-skill 源码**：[github.com/alchaincyf/darwin-skill](https://github.com/alchaincyf/darwin-skill) (master 分支, SKILL.md line 20-21/60/111-287/356-369)
- **微软 SkillLens 论文**：[arXiv:2605.23899](https://arxiv.org/abs/2605.23899)
- **微软 SkillOpt 论文**：[arXiv:2605.23904](https://arxiv.org/abs/2605.23904)
- **zettaranc-skill 现有模块**：
  - `modules/harness_updater.py` line 57-115（已有策略分析 SQL）
  - `modules/harness_updater.py` line 191-192（"目前先返回更新建议，供人工审核"）
  - `modules/improvement_logger.py` line 41-75（已有 JSONL 格式）
  - `corpus/quality_check.py` line 213-223（8 项硬规则检查）

---

## 10. 决策记录

| 决策 | 选择 | 拒绝的方案 | 理由 |
|---|---|---|---|
| 优化对象 | trading 策略 | SKILL.md / both | 用户偏好 + 真实复盘数据可端到端验证 |
| 评分公式 | 60% 真实 + 40% LLM | 纯硬规则 / 纯 LLM / 多信号 | 平衡可重放性与细粒度 |
| HITL | Darwin 三层式 | 二段式 / 单点 / 全自动 | 与 darwin 理论对齐，可随时打断 |
| 引入范围 | 补全核心三件套 | 全量引入 / 只学思想 / 最小实验 | 最小风险最大杠杆 |
| 实施策略 | 混合渐进 V1+V2 | 保守 / 激进 | 先验证评分系统再上 git 闭环 |
| 评分主体 | trading 真实胜率 | LLM judge | 规避 PR #13 绝对分差棘轮缺陷 |
| 反例来源 | 交易踩坑 | 工程踩坑 | 优化对象决定反例来源 |
| 分支策略 | `feature/darwin-self-optimizer` | 直接在 main | 用户明确要求新建分支 |
