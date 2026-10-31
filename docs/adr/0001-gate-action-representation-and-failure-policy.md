---
status: accepted
---

# 闸门动作的表示层与失败策略

活跃市值闸门（0AMV gate）的判定结果此前有三种表示：裸字符串 `"OPEN"/"WAIT"/"CLEAR"`、普通 `Enum` `GateAction`、以及第三套语义不同的 `signal`（`"UP"/"DOWN"/"NEUTRAL"`）。调用方还必须知道阈值、开关与两个数据源路径，判定语义因此跨 seam 泄漏。

2026-08-23 的统一重构 `3e882b9`（目的正是"消除 0AMV gate 策略重复"）把 `_gate` 的返回类型从 `str` 改成 `GateAction`，迁移了 `== "CLEAR"` 却漏掉 `!= "OPEN"`。于是 B1/B2 回测自 v4.3.0 发布起恒定返回 0 笔成交——**始作俑者正是那次本该消除重复的重构**。

## 决策

1. **表示层唯一化**：`GateAction` 改为 `enum.StrEnum`，作为闸门动作的唯一表示；`get_active_market_gate` 也返回它。枚举本身就是 str，旧调用方的字符串比较与 `isinstance` 断言继续成立，而"枚举与字符串比较"从此不再是错误类别。`StrEnum` 的 `__str__` 直接给出 `"OPEN"`，文本格式化不会打印 `"GateAction.OPEN"`。

2. **失败策略 fail-closed**：闸门关闭 → OPEN（不拦）；**无数据** → WAIT（拦）；**加载异常** → WAIT（拦）。无数据与加载失败在实现中显式区分。

3. **注入而非现场创建**：回测 engine 在构造时接收闸门 port，循环内只查询动作；配置由 `GateConfig` 承载，由 CLI 构造后注入。测试以假闸门 adapter 替身。

4. **模块边界**：新建 `modules/active_market_gate.py` 作为闸门判定的唯一实现，`modules/active_market_value.py` 保留 re-export，以兼容已发布到 PyPI 的旧导入路径。

5. **阈值分组**：`signal`（当日涨跌幅）与 `gate`（两日累计涨幅）是两组不同语义的阈值，即使数值相同也不合并。

## 被否决的选项

- **保持字符串、删除枚举**：会让 `market_timing` 与全部既有调用点再次依赖字符串字面量。
- **fail-open**：见决策 2 的理由。
- **新增 `UNKNOWN` 第四态**：把"无数据 / 加载失败"的判断推回每个调用方，复杂度外泄。
- **直接删除 `get_active_market_gate` 的旧路径**：包已发布到 PyPI，外部调用方会突然 ImportError。

## Consequences

- B1/B2 回测将**首次**产出成交（自 v4.3.0 起恒为 0）。闸门默认仍为关闭，因此修复后的行为等价于 v4.2 语义。
- 闸门动作从此只有一种表示；"把返回值从 str 换成枚举"这类重构必须一次迁移全部调用点，`str, Enum` 是防止漏迁的兜底。
- 未来若新增与闸门并行的判断（例如新的择时维度），应当遵循同样的模式：一个 module、一处判定、一种表示。
