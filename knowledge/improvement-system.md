# 自我改进系统（Improve Self）

> **核心理念**：通过实际跟踪验证策略，通过复盘发现错误，通过优化持续改进。
>
> 本文件从 SKILL.md v3.3.0 抽出。原位置：SKILL.md 第 1323-1504 行（v3.3.1 拆分）。

<!-- Skill-Runtime
加载时机: 用户需要跟踪验证策略、月度复盘、或讨论自我改进机制时
用途: 跟踪池 + 复盘 + 优化的完整闭环设计
大小: ~7KB
依赖: knowledge/harness.md（与 Feedback Loop 集成）
-->

---

## 一、系统架构

```
用户输入（20-30只股票）
    ↓
[1. 跟踪池管理]
    - 添加/移除股票
    - 设置跟踪参数
    ↓
[2. 数据同步]
    - 每日同步K线、指标
    - 记录信号变化
    ↓
[3. 信号记录]
    - 记录买入/卖出信号
    - 记录实际走势
    ↓
[4. 月度复盘]
    - 对比信号与实际
    - 分析正确/错误原因
    - 生成复盘报告
    ↓
[5. 策略优化]
    - 调整参数阈值
    - 优化策略规则
    - 更新知识库
    ↓
[6. 反馈到 Harness 层]
    - 更新 Guardrails
    - 优化 Error Recovery
    - 完善 Feedback Loop
```

---

## 二、数据库表设计

**所有表名以 `_self` 结尾，与主系统表区分：**

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `tracking_pool_self` | 跟踪池管理 | ts_code, name, add_date, status, strategy_tags |
| `tracking_records_self` | 跟踪记录 | ts_code, trade_date, 指标数据, 信号, 形态, 阶段 |
| `monthly_reviews_self` | 月度复盘 | review_month, ts_code, 收益统计, 信号准确率, 复盘结论 |
| `strategy_performance_self` | 策略表现 | strategy_name, review_month, 准确率, 收益统计, 调整建议 |

---

## 三、CLI 命令设计

### S.3.1 跟踪池管理命令

```bash
# 添加股票到跟踪池
zt track add 600519.SH --reason "B1买点出现" --strategy B1
zt track add 000858.SZ,000568.SZ --reason "观察池"

# 从跟踪池移除
zt track remove 600519.SH --reason "已卖出"

# 查看跟踪池
zt track list                    # 列出所有活跃跟踪股票
zt track list --status paused    # 列出暂停跟踪的股票
zt track list --strategy B1      # 按策略筛选

# 查看单只股票详情
zt track info 600519.SH

# 更新股票状态
zt track status 600519.SH --status paused

# 查看统计信息
zt track stats
```

### S.3.2 数据同步命令

```bash
# 同步单只股票
zt track sync 600519.SH

# 同步所有活跃跟踪股票
zt track sync --all

# 同步指定日期范围
zt track sync 600519.SH --start 2026-01-01 --end 2026-06-07
```

### S.3.3 复盘命令

```bash
# 生成月度复盘报告
zt track review --month 2026-05

# 生成单只股票复盘
zt track review 600519.SH --month 2026-05

# 生成复盘报告并保存
zt track review --month 2026-05 --output review_202605.md

# 查看历史复盘
zt track review --history
```

---

## 四、与 Harness 层的集成

> 详细 Harness 约束与反馈机制见 `knowledge/harness.md`。

### 4.1 作为 Feedback Loop 的一部分

**通过跟踪池验证策略：**

1. **信号验证**
   - 跟踪池中的股票，每次出现信号时记录
   - 月末统计信号准确率
   - 准确率<50%的策略需要优化

2. **收益验证**
   - 跟踪池中的股票，记录买入后的收益
   - 月末统计平均收益率、胜率
   - 收益率<0的策略需要优化

3. **风险验证**
   - 跟踪池中的股票，记录最大回撤
   - 月末统计最大回撤
   - 回撤>20%的策略需要优化

**验证结果的应用：**
- 准确率高的策略 → 在回答中优先推荐
- 准确率低的策略 → 在回答中谨慎使用
- 收益率高的策略 → 在回答中重点讲解
- 收益率低的策略 → 在回答中提示风险

### 4.2 更新 Guardrails

**根据复盘结果调整约束：**

```markdown
如果某策略连续3个月准确率<50%：
→ 在 Guardrails 中添加警告："该策略近期表现不佳，谨慎使用"

如果某策略最大回撤>20%：
→ 在 Guardrails 中添加限制："该策略风险较高，建议降低仓位"

如果某策略连续3个月准确率>80%：
→ 在 Guardrails 中添加推荐："该策略近期表现良好，可适当关注"
```

### 4.3 优化 Error Recovery

**根据复盘结果改进恢复策略：**

```markdown
如果发现"绿砖状态下抄底"的错误：
→ 在 Error Recovery 中添加检测："检测到绿砖状态，自动拦截抄底建议"

如果发现"J值>0时建议B1"的错误：
→ 在 Error Recovery 中添加检测："检测到J值>0，自动拦截B1建议"

如果发现"满仓不打断"的错误：
→ 在 Error Recovery 中添加检测："检测到满仓状态，自动打断并提示风险"
```

---

## 五、自我改进的价值

**对用户的价值：**
1. **验证策略**：通过实际跟踪验证Z哥的策略是否有效
2. **发现盲点**：通过复盘发现策略的盲点和不足
3. **积累案例**：积累大量的实战案例，用于教学和优化
4. **持续改进**：通过优化机制持续改进策略

**对系统的价值：**
1. **数据驱动**：用真实数据驱动策略优化
2. **可量化**：所有指标都可量化，便于评估
3. **可追溯**：所有操作都有记录，便于追溯
4. **可复用**：优化后的策略可以复用到其他场景

**核心理念：**
> "不是让模型更聪明，而是让模型更可靠。"
> "通过实际跟踪验证策略，通过复盘发现错误，通过优化持续改进。"
> "你不需要知道顶在哪里，你只需要知道趋势还在不在。"

---

> **返回**：[`SKILL.md`](../SKILL.md) · 下一站 [`knowledge/harness.md`](./harness.md)