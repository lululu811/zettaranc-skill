---
status: accepted
---

# 回测引擎归一：唯一实现是 PortfolioBacktestEngine

仓库里有四套并行的回测实现。`modules/backtest_six_step.py` 自称 DEPRECATED 却被 8 处生产代码调用，而它宣称的替代者 `modules/backtest/` 根本没有 shaofu 等价物——"新"包反过来依赖"已弃用"的包。决定：把回测的唯一实现收敛到 `PortfolioBacktestEngine`（`modules/backtest/portfolio.py`），`ShaofuLoopEngine` 继续作为共享的策略/离场内核；B1 入场检测统一到 `strategies.detect_b1`；`backtest_six_step.py` 降级为兼容 re-export。同时删掉约 1,800 行零调用方的死代码。

## 背景

四套实现与它们的差异：

| 实现 | 位置 | 费率 | 闸门 | 仓位规则 | 指标口径 | 生产调用方 |
|---|---|---|---|---|---|---|
| shaofu 单股/组合 | `backtest_six_step.py` | ✗ | ✗ | ✗ | 按交易序号建曲线，Sharpe 按持仓天数年化 | 8 处 |
| 多策略组合 | `backtest/single.py` | ✗ | ✗ | 固定比例 | `pnl_pct` 分数复利 | CLI `multi` + API |
| 组合引擎 | `backtest/portfolio.py` | ✓ | ✓ | 槽位+现金保留 | 净值序列，含 calmar | verify 验收链 |
| B1/B2 | `backtest/b1_b2_backtest.py` | ✗ | ✓（注入） | 无资金 | 复用 shaofu 的 `_calc_metrics` | CLI `b2-confirm` |

三处结构性问题：

1. **依赖方向倒挂**：`modules/backtest/b1_b2_backtest.py:22` 与 `modules/backtest/_rust_bridge.py:276` 反过来 import 已弃用的 `modules/backtest_six_step.py`。
2. **`zt backtest portfolio` 报的"组合收益"不是组合**：`backtest_shaofu_portfolio`（`:172-265`）是各股独立回测后按 `1/max_concurrent` 加权平均曲线（`:236-241`）——没有共享资金池、没有费率、没有闸门。而 `zt verify v1.0` 验收用的是真组合。两条路径的数字天然对不上。
3. **两个 B1 检测器**：shaofu 路径用 `indicators.detect_b1_today`（返回 dict），组合路径用 `strategies.detect_b1`（返回 `StrategySignal`，带 MDC 打分与麒麟上下文）。两者互不调用。

## 决策

### 1. 唯一实现引擎：`PortfolioBacktestEngine`

`modules/backtest/portfolio.py` 是唯一保留的组合回测实现。

理由：它是唯一带费率（`commission_rate` / `min_commission` / `stamp_duty_rate`）、0AMV 闸门（注入式 `TradingGate`）、槽位与现金保留仓位规则、市场状态自适应加权、以及 `calmar` 字段的引擎。而 `modules/verify/gates.py` 的五项硬指标**要求 calmar**——`ShaofuBacktestResult` 没有这个字段，逼得 `verify/pipeline.py:519` 手工算一遍。它的离场路径调的是同一个 `ShaofuLoopEngine` seam，入口约定也一致（信号日收盘价买入），所以它是真的超集，不是另一套策略。

### 2. 共享内核：`ShaofuLoopEngine` + `LoopConfig` + `LoopTrade`

继续留在 `modules/loop_engine.py`，被两个包共用。它已经是正确的 seam——策略与离场规则的唯一实现。不动。

### 3. B1 检测统一到 `strategies.detect_b1`

理由：`detect_b1` 属于上层正式战法接口（`strategies/__init__.py::detect_all_strategies` 是 AGENTS.md 声明的入口，背后就是它），带 MDC 打分与麒麟上下文；`indicators.detect_b1_today` 只是 `indicators/price_patterns/screener_helper.py` 里的筛选辅助。两个检测器产出不同的入场判定，是"回测数字不可比"的深层原因之一。

代价：shaofu 路径的入场判定会变 → 验收数字会动 → 必须与验收阈值重新基线放在同一个 PR。

### 4. 删除死代码（约 1,800 行）

零生产调用方、零测试覆盖：

| 目标 | 行数 |
|---|---|
| `backtest_six_step.py::backtest_shaofu_portfolio_integrated`（`:417-797`） | 381 |
| `modules/position_manager.py`（整个模块） | 445 |
| `modules/industry_filter.py`（整个模块） | 393 |
| `modules/dynamic_config.py::DynamicConfigAdapter`（`:137-297`） | 161 |
| `backtest_six_step.py::backtest_shaofu_with_validation`（`:309-398`） | 90 |
| `backtest_six_step.py::summary_with_validation`（`:399-416`） | 18 |
| `modules/statistics/criteria.py`（整个模块） | 309 |

`DynamicConfigAdapter` 所在文件保留——`MarketTimingWeights` 仍被 `modules/market_timing.py` 使用。`modules/statistics/__init__.py` 保留——`sensitivity.py` / `ensemble.py` 在用它的 `sharpe_t_test` 等。

`backtest_shaofu_with_validation` 与 `modules/statistics/criteria.py` 虽零调用方，但被 `README.md:145` 与 `docs/STATISTICS_VALIDATION.md` 宣传为公开能力。**文档宣传了一个不存在的能力**——接线它是产品决策（"验收要不要带统计检验"），不是重构能顺手定的。所以删代码 + 同步改文档，而不是留着。

### 5. 解除倒挂依赖

`ShaofuBacktestResult`、`_calc_metrics`、`backtest_shaofu_single`、`summary_text` 迁入新的 `modules/backtest/shaofu.py`。`modules/backtest_six_step.py` 降级为兼容 re-export（包已发布到 PyPI，旧导入路径必须继续可用）。8 处生产调用点改为从 `modules.backtest` 导入。

### 6. 结果形状与指标聚合归一

一个 `BacktestResult` interface 承载 `LoopTrade` trades + 现有指标字段的并集（`PortfolioBacktestResult` 需补 `avg_pnl` / `avg_win` / `avg_loss` / `max_win` / `max_loss` / `avg_holding_days`）。指标聚合归到 `modules/core/metrics.py::calculate_metrics`——但要先修它的 SELL 过滤：`core/metrics.py:206` 按 `getattr(t, "action", None) == "SELL"` 筛成交，而 `LoopTrade` 没有 `action` 字段，喂进去会得到 `total_trades == 0`。

## 被否决的选项

- **一次性全做**（删死代码 + 改结果形状 + 换引擎 + 重新基线一起）：review 无法聚焦，回滚粒度差，且验收数字的变化无法归因到具体一步。拆成阶段 1–5，每阶段独立可回滚。
- **保留伪组合但改名**（叫"等权组合回测"）：数字仍然是假的（无费率、无共享资金），改名只治标。用户据此决策仍会被误导。
- **统一到 `indicators.detect_b1_today`**：它是筛选辅助，不是战法接口，且不带 MDC 打分。
- **接线 `backtest_shaofu_with_validation` 而不删**：需要产品决策，不该由架构重构代劳。
- **让 Rust 侧当统一引擎**：Rust 侧既没有费率模型也没有闸门模型，当统一引擎会静默丢掉这两项。

## 后果

- **验收数字会动两次**：阶段 3（指标口径归一）应当**数值等价**——同样交易序列算出的指标必须逐位相同，这是该阶段的硬判据。阶段 4（换引擎 + 换 B1 检测器）是**语义变更**，数字必然动，`modules/verify/gates.py` 的阈值需要显式重新基线并说明原因。
- `zt backtest portfolio` 的数字会变，并且会与 `zt verify v1.0` 的口径一致——这正是这次改动的目的。
- Rust 桥在阶段 5 之前只服务单股加速路径；`run_portfolio_backtest_py`（Rust 侧已实现、零 Python 调用方）在 Rust 补齐费率与闸门模型前不接线。
- `modules/statistics/criteria.py` 删除后，"验收带统计检验"这个能力需要新的实现路径，不是本次范围。
