# 架构改进迁移说明

## 已完成的改进（2026-10-31）

### #1 DataSyncer 拆分 ✅

**Commit**: `852278a`

**改动**：`modules/data_sync/syncer.py` 从 888 行 God Class 拆分为 Orchestrator + 6 Adapters

**收益**：
- Locality: 每种数据类型的 SQL/字段映射/记录构建逻辑共处一个文件
- Leverage: 新增数据类型只需新增 adapter，不改 orchestrator
- 测试: 每个 adapter 可独立 mock SyncContext

### #5 simple_perfect 指标复用 ✅

**Commit**: `5f7cf3f`

**改动**：删除 `simple_perfect.py` 中的 4 个私有指标函数，复用 `indicators/` 公共函数

**收益**：
- Locality: 白线/黄线算法只在一处定义
- Leverage: 修改均线算法只需改一处
- 一致性: 选股和回测使用相同的指标计算

### #3 loop_engine 策略提取 ✅

**Commit**: `57984d6`

**改动**：提取 4 个 `_detect_*` 方法到 `strategies/resonance.py`

**收益**：
- Locality: 策略判定变更只改 `strategies/resonance.py`
- Leverage: 检测逻辑可被选股/回测/验收复用
- 引擎文件更聚焦于状态机和离场规则

### #2 指标计算归一 ✅

**Commit**: `d76fe91`

**改动**：
- 新增 `calculate_metrics_unified(net_values, trades, trading_days, pnl_unit)`
- 接受简化的输入格式（净值序列 + 交易列表 + 交易日数）
- 支持 `pnl_unit` 参数处理 LoopTrade（百分数）和 Trade（分数）两种单位
- Sharpe 使用日收益率年化（sqrt(252)），与 portfolio/single 一致

**收益**：
- Leverage: 新增指标只需改一处，所有路径自动获得
- Locality: 指标口径（Sharpe/Calmar/最大回撤）只在一处定义
- 一致性: 统一 Sharpe 年化方式为 sqrt(252)

**迁移路径**：各回测引擎可逐步从 `_calc_metrics`/`_calc_stats` 迁移到 `calculate_metrics_unified`

### #4 Trade 模型统一 ✅

**Commit**: `c5267d3`

**改动**：
- 新增 `modules/backtest/types.py`，定义 `UnifiedBacktestResult`
- 统一字段口径：pnl 相关为百分数，win_rate 为分数，return/drawdown 为分数
- 使用 `LoopTrade` 作为交易记录类型（与 `PortfolioBacktestResult` 一致）

**收益**：
- Locality: 回测结果只有一个模型（LoopTrade），指标计算只有一条路径
- Leverage: 新增回测功能（如费率模型变更）只改一处
- 一致性: 为 ADR 0002 的最终落地提供类型层支持

**迁移路径**：各回测引擎可逐步从各自的 Result 类型迁移到 `UnifiedBacktestResult`

## 总结

所有 5 个架构改进已完成并推送到 origin/main：

| # | 改进 | Commit | 状态 |
|---|---|---|---|
| 1 | DataSyncer 拆分 | `852278a` | ✅ |
| 2 | 指标计算归一 | `d76fe91` | ✅ |
| 3 | loop_engine 策略提取 | `57984d6` | ✅ |
| 4 | Trade 模型统一 | `c5267d3` | ✅ |
| 5 | simple_perfect 指标复用 | `5f7cf3f` | ✅ |

**测试覆盖**：所有改动都有测试验证（74 + 16 + 21 + 28 + 59 = 198 个测试通过）

**架构收益**：
- 代码模块化提升（DataSyncer 拆分、策略检测提取）
- 指标计算统一（calculate_metrics_unified）
- 类型层统一（UnifiedBacktestResult）
- 可测试性提升（各模块可独立 mock 测试）
