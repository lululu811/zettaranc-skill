# 策略统计检验框架

> ⚠️ **状态：底层能力可用，与验收链路尚未接线。**
>
> `modules/statistics/` 提供的四项检验（夏普 t 检验 / Bootstrap CI / Monte Carlo 置换检验 / 子周期分析）**仍在**并可直接调用。
> 但把回测与统计检验打包在一起的 `backtest_shaofu_with_validation` 入口、以及 `modules/statistics/criteria.py`（`validate_strategy` / `ValidationReport` / `CriteriaLevel`）因**零调用方**已于 v4.6.0 删除。
>
> 当前 `zt verify v1.0` 的验收走的是**另一条路**——五项硬指标（Sharpe / Calmar / WinRate / MaxDD / OOS-IS，见 `modules/verify/gates.py`），**不含**统计检验。两者不可互相替代。
>
> 下面的"完整验证流程"已改为**手动组合**的写法；重新接线是独立的产品议题，不在 BacktestRunner 范围内。

## 概述

本模块提供**严格的统计检验**，用于验证交易策略的有效性，解决核心问题：

> **"夏普比率 0.8 是'真有能力'还是'运气好'？"**

## 核心功能

### 1. 夏普比率 t 检验

**目的**：判断夏普比率是否显著大于 0（策略是否有效）

**原理**：
- H0: 夏普 = 0（策略无效）
- H1: 夏普 > 0（策略有效）
- 使用 Lo (2002) 的标准误估计：SE = √[(1 + SR²/2) / n]

**用法**：
```python
from modules.statistics import sharpe_t_test

# 日收益率序列
returns = [0.01, 0.02, -0.005, 0.015, ...]
result = sharpe_t_test(returns)

print(f"夏普比率: {result.sharpe_ratio:.2f}")
print(f"p-value: {result.p_value:.4f}")
print(f"显著？ {result.is_significant}")
```

**判断标准**：
- `p < 0.05` → 95% 置信度策略有效
- `p < 0.01` → 99% 置信度策略有效

---

### 2. Bootstrap 置信区间

**目的**：估计夏普比率的真实范围

**原理**：
- 通过有放回重采样（1000次）
- 估计夏普的抽样分布
- 计算 95% 置信区间

**用法**：
```python
from modules.statistics import sharpe_t_test

result = sharpe_t_test(returns)

print(f"95% CI: [{result.ci_lower:.2f}, {result.ci_upper:.2f}]")
print(f"下界 > 0.3？ {result.ci_significant}")
```

**判断标准**：
- CI 下界 > 0.3 → 策略收益稳定
- CI 下界 < 0 → 策略可能亏损

---

### 3. Monte Carlo 置换检验

**目的**：检验策略是否是"数据挖掘产物"

**原理**：
- 打乱交易信号的时间顺序
- 计算随机策略的夏普分布
- 比较真实策略 vs 随机策略

**用法**：
```python
from modules.statistics import monte_carlo_permutation_test

result = monte_carlo_permutation_test(returns, n_permutations=1000)

print(f"真实夏普: {result.actual_sharpe:.2f}")
print(f"随机夏普均值: {result.mean_permuted_sharpe:.2f}")
print(f"p-value: {result.p_value:.4f}")
```

**判断标准**：
- `p < 0.05` → 策略显著优于随机
- `p > 0.05` → 策略可能是运气

**注意**：此检验对夏普比率效果有限（夏普只依赖均值和标准差，打乱顺序不改变这些统计量）。更有用的是 Bootstrap CI。

---

### 4. 子周期分析

**目的**：检验策略是否只在特定市场环境下有效

**原理**：
- 按市场环境（牛市/熊市/震荡）分组
- 分别计算各子周期的绩效
- 评估策略的稳健性

**用法**：
```python
from modules.statistics import analyze_sub_periods

# 交易列表 + 市场环境映射
trades = [{"date": "2024-01-01", "pnl_pct": 5.0, "holding_days": 10}, ...]
market_regimes = {"2024-01-01": "bull", "2024-01-15": "bear", ...}

result = analyze_sub_periods(trades, market_regimes)

print(f"牛市夏普: {result.bull_sharpe:.2f}")
print(f"熊市夏普: {result.bear_sharpe:.2f}")
print(f"震荡夏普: {result.sideways_sharpe:.2f}")
print(f"稳健性得分: {result.robustness_score:.0f}")
print(f"是否稳健？ {result.is_robust()}")
```

**判断标准**：
- 三个子周期夏普都 > 0 → 策略稳健
- 稳健性得分 >= 60 → 策略可用

---

## 完整验证流程

### 方法 1：手动组合（当前唯一可用的路径）

> 历史上的"一键验证"入口（`backtest_shaofu_with_validation`）已删除——它零调用方。现在需要自己把回测与检验拼起来。

```python
from modules.backtest_six_step import backtest_shaofu_single
from modules.statistics import sharpe_t_test, monte_carlo_permutation_test, analyze_sub_periods

# 1. 跑回测
result = backtest_shaofu_single("600519.SH", days=500)

# 2. 从资金曲线提取日收益率
curve = result.equity_curve
daily_returns = [(curve[i] - curve[i - 1]) / curve[i - 1] for i in range(1, len(curve))]

# 3. 逐项检验，按门槛自行判定
sharpe_test = sharpe_t_test(daily_returns)
mc_test = monte_carlo_permutation_test(daily_returns)

print(f"夏普 t 检验 p-value: {sharpe_test.p_value:.4f}  显著: {sharpe_test.is_significant}")
print(f"Bootstrap 95% CI: [{sharpe_test.ci_lower:.2f}, {sharpe_test.ci_upper:.2f}]")
print(f"Monte Carlo p-value: {mc_test.p_value:.4f}")

# 4. 绩效指标自行对照门槛
print(f"胜率: {result.win_rate:.1%}（门槛 > 40%）")
print(f"盈亏比: {result.profit_factor:.2f}（门槛 > 1.5）")
print(f"最大回撤: {result.max_drawdown:.2%}（门槛 < 25%）")
print(f"夏普比率: {result.sharpe_ratio:.2f}（门槛 > 0.5）")
```

**判定参考**：

```
【统计显著性检验】
  夏普t检验: p=0.0012 (阈值: p<0.05)
  Bootstrap置信区间: [0.45, 1.23] (阈值: 下界>0.3)

【绩效指标】
  胜率: 52.3% (阈值: >40%)
  盈亏比: 1.85 (阈值: >1.5)
  最大回撤: 12.5% (阈值: <25%)
  夏普比率: 0.85 (阈值: >0.5)
```

---

### 方法 2：子周期分析

```python
from modules.backtest_six_step import backtest_shaofu_single
from modules.statistics import analyze_sub_periods

result = backtest_shaofu_single("600519.SH", days=500)

# 交易列表（dict）+ 市场环境映射
trades = [
    {"date": t.exit_date, "pnl_pct": t.pnl_pct, "holding_days": t.holding_days}
    for t in result.trades
    if t.exit_date
]
market_regimes = {"2024-01-01": "bull", "2024-01-15": "bear"}  # 由市场状态模块提供

analysis = analyze_sub_periods(trades, market_regimes)
print(f"牛市夏普: {analysis.bull_sharpe:.2f}")
print(f"熊市夏普: {analysis.bear_sharpe:.2f}")
print(f"震荡夏普: {analysis.sideways_sharpe:.2f}")
print(f"稳健性得分: {analysis.robustness_score:.0f}")
```

---

## 验证级别

> 三个级别的**门槛清单**仍然有效，可作为自行判定的参考。但 `CriteriaLevel` 枚举与 `validate_strategy` 已随 `modules/statistics/criteria.py` 删除——**没有内置的级别开关**，请按下面的清单自行判定。

### 严格模式（STRICT）

**适用场景**：实盘前的最终验证

**要求**：所有指标必须达标
- 夏普 t 检验 p < 0.05
- Bootstrap CI 下界 > 0.3
- Monte Carlo p < 0.05
- 子周期稳健性得分 >= 60
- 胜率 > 40%
- 盈亏比 > 1.5
- 最大回撤 < 25%
- 夏普比率 > 0.5

---

### 中等模式（MODERATE）

**适用场景**：策略开发阶段

**要求**：核心指标达标
- 夏普 t 检验 p < 0.05
- Bootstrap CI 下界 > 0.3
- 胜率 > 40%
- 盈亏比 > 1.5
- 最大回撤 < 25%

---

### 宽松模式（LOOSE）

**适用场景**：快速筛选

**要求**：基本指标达标
- 胜率 > 40%
- 盈亏比 > 1.5

---

## CLI 使用

### 单股票验证

```bash
python3 scripts/demo_validation.py 600519.SH
```

### 参数敏感性测试

```bash
python3 scripts/demo_validation.py 600519.SH --sensitivity
```

---

## 达标标准（硬指标）

### 必须达标的指标（缺一不可）

| 维度 | 指标 | 门槛 | 含义 |
|------|------|------|------|
| **统计显著性** | 夏普 t 检验 p-value | < 0.05 | 95% 置信度策略有效 |
| **置信区间** | Bootstrap CI 下界 | > 0.3 | 策略收益稳定 |
| **胜率** | win_rate | > 40% | 信号质量 |
| **盈亏比** | profit_factor | > 1.5 | 风险收益比 |
| **风险控制** | 最大回撤 | < 25% | 回撤控制 |

### 建议达标的指标

| 维度 | 指标 | 门槛 | 含义 |
|------|------|------|------|
| **防数据挖掘** | Monte Carlo p-value | < 0.05 | 策略非运气 |
| **稳健性** | 子周期分析 | 三周期都赚钱 | 全市场适配 |
| **收益能力** | 夏普比率 | > 0.5 | 风险调整收益 |

---

## 常见问题

### Q1: 夏普比率 0.8，p-value = 0.08，策略有效吗？

**A**: 在 95% 置信度下不显著（p > 0.05），但在 90% 置信度下显著（p < 0.10）。建议：
- 增加样本量（更长回测期）
- 或降低置信度要求（使用 LOOSE 模式）

---

### Q2: Bootstrap CI 下界是 0.1，说明什么？

**A**: 95% 置信度下，夏普比率可能在 [0.1, 1.5] 之间。下界太低（< 0.3），说明策略收益不稳定，实盘可能表现不佳。

---

### Q3: 子周期分析显示熊市亏损，怎么办？

**A**: 策略在熊市亏损是正常的。关键是：
- 熊市亏损是否可控（最大回撤 < 10%）
- 牛市和震荡市能否弥补熊市亏损
- 考虑添加择时过滤器（如大盘均线判断）

---

### Q4: 参数敏感性高，怎么办？

**A**: 参数稍微改变，策略表现差异很大 → 过度拟合历史数据。建议：
- 使用 Walk-Forward 验证
- 减少参数数量
- 增加正则化（如更严格的止损）

---

## 技术细节

### 依赖

- Python 3.10+
- 仅使用标准库 + numpy（通过传递依赖）
- 无需 scipy/matplotlib（P0 阶段）

### 性能

- 夏普 t 检验：O(n)，n 为样本量
- Bootstrap CI：O(n × k)，k 为迭代次数（默认 1000）
- Monte Carlo：O(n × p)，p 为置换次数（默认 1000）

**实测**：500 个交易日的回测，统计检验耗时 < 1 秒。

---

## 后续优化（P1/P2）

### P1（高优先级）

- [ ] 参数敏感性热力图
- [ ] HTML 可视化报告
- [ ] Walk-Forward 统计检验集成

### P2（中优先级）

- [ ] 策略集成（投票/加权/stacking）
- [ ] Deflated Sharpe Ratio（多策略比较）
- [ ] 更高级的 Bootstrap（Block Bootstrap）

---

## 参考资料

1. Lo, A. W. (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal.
2. Harvey, C. R., & Liu, Y. (2015). Backtesting. Journal of Portfolio Management.
3. Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management.

---

## 更新日志

- 2026-07-08: P0 版本发布（夏普 t 检验 + Bootstrap CI + Monte Carlo + 子周期分析）
