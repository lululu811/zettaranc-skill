# BacktestRunner 实施计划

配套 [ADR-0002](adr/0002-backtest-runner-unification.md)。ADR 记"为什么这么定"，本文件记"按什么顺序落地、每一步怎么验证"。

**读法**：阶段 1–2 是纯重构，**验收数字逐位不变**；阶段 3 应当数值等价；阶段 4 是语义变更，数字必然动。每个阶段一个独立分支 / 独立提交组，任意一步可单独回滚。

---

## 阶段总览

| 阶段 | 主题 | 改动量 | 验收数字 | 可否单独合入 |
|---|---|---|---|---|
| 0 | 基线快照 | 0 行 | — | 是（准备工作） |
| 1 | 删死代码 | **−1,800 行** | 不变 | ✅ |
| 2 | 解除倒挂依赖 | 搬迁 ~176 行 | 不变 | ✅ |
| 3 | 结果形状与指标归一 | 改 3–4 个文件 | **必须逐位相同** | ✅ |
| 4 | 换引擎 + 换 B1 检测器 | 改 4–6 个文件 | **会动，需重新基线** | ⚠️ 需产品确认 |
| 5 | Rust 对齐 | 待定 | 视实现 | 视情况 |

---

## 阶段 0 · 基线快照（准备）

**目的**：在动任何代码前，把当前验收数字钉死，作为后续每个阶段的对照基准。

**做什么**
1. 在一个固定的数据快照上跑 `zt verify v1.0 --limit 50 --days 300 --json`，保存完整 JSON。
2. 记录五项硬指标的原始值：`sharpe` / `calmar` / `win_rate` / `max_drawdown` / `oos_is_ratio`。
3. 记录 `modules/verify/gates.py::THRESHOLDS` 的当前阈值。
4. 把这份 JSON 存进 `docs/adr/` 旁边的基线文件（不进版本库的历史目录，保留为可追溯的对照数据）。

**完成判据**：有一份可复现的"改动前"数字，任何后续阶段都能拿它对账。

---

## 阶段 1 · 删除死代码

**行为影响**：无。全部目标零生产调用方、零测试覆盖。

**改动清单**

| 删除对象 | 行数 | 备注 |
|---|---|---|
| `modules/position_manager.py` | 445 | 整个模块；唯一消费者是待删的 integrated 函数 |
| `modules/industry_filter.py` | 393 | 整个模块；只被 `position_manager` 用 |
| `modules/statistics/criteria.py` | 309 | 整个模块；唯一消费者是待删的 validation 函数 |
| `backtest_six_step.py::backtest_shaofu_portfolio_integrated` | 381 | `:417-797` |
| `backtest_six_step.py::backtest_shaofu_with_validation` | 90 | `:309-398` |
| `backtest_six_step.py::summary_with_validation` | 18 | `:399-416` |
| `dynamic_config.py::DynamicConfigAdapter` | 161 | `:137-297`；同文件的 `MarketTimingWeights` 保留 |

**同时要改的文档**（因为它们宣传了不存在的能力）
- `README.md:145` 附近：删除 `backtest_shaofu_with_validation` 的对外描述
- `docs/STATISTICS_VALIDATION.md`：标注"统计检验的验收集成尚未接线"，或把该节降级为"设计稿"

**验证**
```bash
python -m pytest tests/ -q                       # 全量，必须与基线同绿
ruff check modules tests && ruff format --check modules tests
mypy modules/ --ignore-missing-imports
python corpus/quality_check.py SKILL.md --strict
```
外加一条**显式的零引用断言**：删完后 `grep -rn "position_manager\|industry_filter\|DynamicConfigAdapter\|criteria\b" modules/` 应无命中（`MarketTimingWeights` 除外）。

**完成判据**：全量测试数不变或只减少（删掉的死代码没有测试）；`verify` 数字与阶段 0 快照逐位相同。

**回滚**：`git revert` 整个提交组即可，无数据迁移。

---

## 阶段 2 · 解除倒挂依赖

**行为影响**：无。纯搬迁，函数体一字不改。

**改动清单**
1. 新建 `modules/backtest/shaofu.py`，原样搬入 4 个符号：
   - `ShaofuBacktestResult`（`:39-61`，23 行）
   - `_calc_metrics`（`:62-126`，65 行）
   - `backtest_shaofu_single`（`:127-171`，45 行）
   - `summary_text`（`:266-308`，43 行）
2. `modules/backtest/__init__.py` 导出这 4 个名字。
3. `modules/backtest_six_step.py` 改为**兼容 re-export**：`from .backtest.shaofu import ShaofuBacktestResult, _calc_metrics, backtest_shaofu_single, summary_text` + `__all__`。旧导入路径 `from modules.backtest_six_step import X` 继续可用（包已发布到 PyPI）。
4. 改生产导入点（共 9 处，7 处取 `backtest_shaofu_single`、1 处取另外两个符号、1 处取 `backtest_shaofu_portfolio`）：

   | 调用点 | 当前导入 | 改成 |
   |---|---|---|
   | `modules/verify/pipeline.py:17` | `backtest_six_step` | `from modules.backtest import backtest_shaofu_single` |
   | `modules/verify/walk_forward.py:107` | `backtest_six_step` | 同上 |
   | `modules/statistics/sensitivity.py:229` | `backtest_six_step` | 同上 |
   | `modules/statistics/ensemble.py:284` | `backtest_six_step` | 同上 |
   | `api/services/backtest_service.py:11` | `backtest_six_step` | 同上 |
   | `scripts/eval_strategies.py:21` | `backtest_six_step` | 同上 |
   | `modules/backtest/_rust_bridge.py:276` | `backtest_six_step` | `from modules.backtest.shaofu import backtest_shaofu_single` |
   | `modules/backtest/b1_b2_backtest.py:22` | `backtest_six_step` | `from .shaofu import ShaofuBacktestResult, _calc_metrics` |
   | `modules/cli_commands/backtest.py:239` | `backtest_six_step` | **不变** —— 它取的是 `backtest_shaofu_portfolio`，该函数阶段 4 才被组合引擎取代 |

**验证**
```bash
python -m pytest tests/ -q
python -m pytest tests/test_cli_uses_rust.py -q   # Rust 桥的 mock 路径依赖导入位置
```
再加一条**倒挂断言**：`grep -rn "backtest_six_step" modules/backtest/` 应无命中——"新"包不再依赖"已弃用"的包。

**完成判据**：`verify` 数字与阶段 0 快照逐位相同；倒挂断言成立。

**回滚**：纯搬迁，回退无副作用。

---

## 阶段 3 · 结果形状与指标归一

**行为影响**：应当**数值等价**。这一阶段的硬判据是"同样交易序列算出的指标逐位相同"——如果不等价，说明口径搬错了。

**改动清单**
1. **修 `core/metrics.py::calculate_metrics` 的 SELL 过滤**（`:206`）：现在按 `getattr(t, "action", None) == "SELL"` 筛成交，而 `LoopTrade` 没有 `action` 字段 → `sell_trades` 恒空 → `total_trades == 0`。需要一个能同时吃 `LoopTrade` 和 dict-trade 的筛选口径。
2. **给 `PortfolioBacktestResult` 补字段**（`backtest/portfolio.py:140`）：`avg_pnl` / `avg_win` / `avg_loss` / `max_win` / `max_loss` / `avg_holding_days`（`loop_engine.py:139-140` 有 `pnl_pct` / `holding_days`）。这些字段现在只有 `ShaofuBacktestResult` 有，而 CLI（`cli_commands/backtest.py:40-47`）与 API（`api/services/backtest_service.py:88-94`）消费的正是它们——阶段 4 把 CLI 切到组合引擎后，组合结果必须补齐同一组字段，序列化器才不用改。
3. **统一一个 `BacktestResult` interface**：承载 `LoopTrade` trades + 指标字段并集，CLI 与 API 的序列化器从它派生。
4. **统一 CLI / API 的序列化形状**：现在 CLI 是扁平、API 是 `summary` 嵌套，且 trade 级字段互有出入（CLI portfolio 的 trade dict 没有 `holding_days`，API 有；API 的 `PortfolioBacktestResponse` 声明了从不填充的 `per_stock`、且丢掉 `ts_code`）。
5. **指标聚合归一**：4 份并行实现（`six_step._calc_metrics` / `single._calc_stats` / `portfolio._build_result` / `core.calculate_metrics`）收敛到 `core/metrics.py` 一处。

**验证**
```bash
python -m pytest tests/ -q
python -m pytest tests/test_output_units.py -q    # 单位约定的护栏，必须仍然全绿
```
再加**数值等价断言**：同一份 fixture 交易序列，改造前后 `_calc_metrics` 与 `calculate_metrics` 算出的每个指标 `pytest.approx` 相等（rel=1e-9）。

**完成判据**：`verify` 数字与阶段 0 快照逐位相同；单位护栏测试仍全绿。

**回滚**：本阶段是机械重构，可整体回退。

---

## 阶段 4 · 换引擎 + 换 B1 检测器（语义变更）

> ⚠️ 这一阶段**会移动验收数字**，且需要产品确认。ADR-0002 决策 3 指出 B1 检测器换掉后入场判定会变。

**改动清单**
1. `zt backtest portfolio` 从 `backtest_shaofu_portfolio`（伪组合）切到 `PortfolioBacktestEngine`（真组合：共享资金池 + 费率 + 闸门 + 仓位上限）。
2. B1 检测统一到 `strategies.detect_b1`：shaofu 路径的入场判定改用 `StrategySignal`（MDC 打分 + 麒麟上下文），不再用 `indicators.detect_b1_today`。
3. **闸门默认值要定**：`verify/pipeline.py:379` 构造 `PortfolioConfig` 时**没有传 `gate=`**，所以验收链路里 0AMV 闸门是关的；`backtest_shaofu_single` 则根本没有闸门参数。换引擎前必须先定"验收时闸门开不开"。
4. **费率默认值**：`PortfolioConfig` 的 `commission_rate=0.00025` / `min_commission=5.0` / `stamp_duty_rate=0.0005` 会首次进入验收数字——之前 shaofu 路径**没有任何费率**。
5. **重新基线 `modules/verify/gates.py::THRESHOLDS`**：五项阈值（`sharpe ≥ 0.5` / `calmar ≥ 0.5` / `win_rate ≥ 0.40` / `max_drawdown ≤ 0.25` / `oos_is_ratio ≥ 0.60`）需要按新基线重新校准，并**在 CHANGELOG 里写明每个阈值为什么变**。
6. 补 `PortfolioBacktestEngine` 的单股入口（CLI 的 `zt backtest portfolio <单只代码>` 与 `zt backtest shaofu` 需要一致的单股路径）。

**验证**
```bash
python -m pytest tests/ -q
python -m pytest tests/test_verify_portfolio_engine.py -q
```
外加**新旧对照表**：同一批股票、同一数据窗口，跑改造前后的 `zt backtest portfolio`，逐项列出差异并逐条解释原因（费率 / 真实资金池 / 闸门 / B1 打分）。

**完成判据**
- `zt backtest portfolio` 与 `zt verify v1.0` 的引擎口径一致
- 新阈值有明确的重新基线依据
- CHANGELOG 记录了数字变化的每一项原因

**回滚**：需要回退 `verify/gates.py` 的阈值 + 引擎切换两组改动。**这是唯一一个回滚代价高的阶段**——所以必须独立成 PR，且在合入前拿到产品确认。

---

## 阶段 5 · Rust 对齐（待定范围）

**背景**：Rust 侧**既没有费率模型也没有闸门模型**。`run_portfolio_backtest_py`（`rust/crates/bindings/src/backtest_bindings.rs:414`）已实现但零 Python 调用方；`bridge_shaofu_single` 是当前单股路径的加速通道，Rust 失败时回落到 Python。

**三个选项**（需要在阶段 4 之后再定）
| 选项 | 内容 | 代价 |
|---|---|---|
| A. 明确分工 | Rust 只服务单股加速路径，组合一律走 Python | 最低。但需在 ADR 里写明"组合路径没有 Rust 加速" |
| B. 补 Rust 模型 | 在 Rust 侧实现费率与闸门，再接 `run_portfolio_backtest_py` | 高。要保证 Rust 与 Python 数值一致 |
| C. 撤掉未接线的桥 | 删 `bridge_grid_search` / `try_call` / `reset_all_caches` / `run_portfolio_backtest_py` | 低。零调用方，删了零风险 |

**建议**：先做 C（零风险的清理），A 或 B 留作独立议题。

---

## 贯穿全程的纪律

1. **每个阶段一个分支、一个提交组**，提交粒度与阶段一致，不跨阶段混提。
2. **阶段 1–3 的硬判据是"验收数字逐位不变"**——用阶段 0 的快照逐项对账，不靠"测试绿了"就放行。
3. **删源码文本断言，换行为测试**。本轮已经栽过一次：`tests/test_active_mv_gate.py` 里两条 `assert "get_active_market_gate(" not in src` 形式的断言，在 B1/B2 那个真实 bug 存在时同样是绿的。新的测试要断言行为，不要断言源码形状。
4. **每个阶段跑全量门禁**：`pytest` / `ruff` / `mypy` / `corpus/quality_check.py --strict`。
5. **版本号同步 7 处**：`pyproject.toml` / `SKILL.md`（frontmatter + 版本表）/ `skill.json` / `README.md`（version badge + tests badge）/ `AGENTS.md` / `docs/CHANGELOG.md`。
