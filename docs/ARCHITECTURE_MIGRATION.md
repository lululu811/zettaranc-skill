# 架构改进迁移说明

## 已完成的改进（2026-10-31）

### #1 DataSyncer 拆分 ✅

**改动**：`modules/data_sync/syncer.py` 从 888 行 God Class 拆分为 Orchestrator + 6 Adapters

**收益**：
- Locality: 每种数据类型的 SQL/字段映射/记录构建逻辑共处一个文件
- Leverage: 新增数据类型只需新增 adapter，不改 orchestrator
- 测试: 每个 adapter 可独立 mock SyncContext

### #5 simple_perfect 指标复用 ✅

**改动**：删除 `simple_perfect.py` 中的 4 个私有指标函数，复用 `indicators/` 公共函数

**收益**：
- Locality: 白线/黄线算法只在一处定义
- Leverage: 修改均线算法只需改一处
- 一致性: 选股和回测使用相同的指标计算

### #3 loop_engine 策略提取 ✅

**改动**：提取 4 个 `_detect_*` 方法到 `strategies/resonance.py`

**收益**：
- Locality: 策略判定变更只改 `strategies/resonance.py`
- Leverage: 检测逻辑可被选股/回测/验收复用
- 引擎文件更聚焦于状态机和离场规则

## 暂缓实施的改进

### #2 指标计算归一 ⏸️

**当前状态**：
- `shaofu.py::_calc_metrics` 使用 `calc_trade_stats`，Sharpe 用 `252/avg_holding_days` 年化
- `single.py::_calc_stats` 使用 `calc_trade_stats` + `calc_curve_metrics`，Sharpe 用 `sqrt(252)` 年化
- `portfolio.py` 使用 `calc_trade_stats` + `calc_curve_metrics`

**差异**：
- Sharpe 年化方式不同（交易频率 vs 日收益率）
- `pnl_pct` 单位不一致（`Trade` 分数 vs `LoopTrade` 百分数）

**风险**：
- 统一 Sharpe 年化方式会导致验收数字变化
- `verify/pipeline.py` 的 gates 判定依赖当前口径

**建议**：
- 如需实施，需先记录当前基线数字
- 提供迁移前后的数字对比
- 更新 `verify/gates.py` 的阈值

### #4 Trade 模型统一 ⏸️

**当前状态**：
- ADR 0002 核心决策（唯一实现是 `PortfolioBacktestEngine`）已通过架构收敛完成
- `single.py` 已大幅瘦身（923 行），主要作为兼容 adapter
- `Trade` 和 `LoopTrade` 差异：
  - `pnl_pct` 单位（分数 vs 百分数）
  - `exit_date` 空值（None vs 空字符串）
  - 字段名（`hold_days` vs `holding_days`）
  - `LoopTrade` 是 `Trade` 的严格超集（更多字段）

**风险**：
- 强行统一会改变回测数字
- 收益有限（当前架构已收敛）

**建议**：
- 保持现状，`Trade` 和 `LoopTrade` 共存
- 新代码优先使用 `LoopTrade`
- 如需迁移，提供 adapter 函数做单位换算

## 总结

当前 3 个已完成的改进已经带来了显著的架构改善：
- 代码模块化提升
- 可测试性提升
- 职责分离更清晰

剩余 2 个高风险改动涉及回测口径变化，建议在新的 PR 中单独处理，附带详细的迁移说明和数字对比。
