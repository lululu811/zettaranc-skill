# 选股策略公式与参数全解

> 本文档从**源代码逐行提取**，非从文档摘抄。所有阈值、参数名、代码位置均标注出处。
> 相关文档：`knowledge/reference/thresholds.md`（阈值速查）、`knowledge/advanced-patterns.md`（战法语料）、`knowledge/signal_dictionary.md`（信号字段解读）
>
> 对照版本：**v4.3.1**（2026-09-13）

---

## 目录

- [零、全貌：14 种选股策略](#零全貌14-种选股策略)
- [一、参数可改性总表](#一参数可改性总表)
- [二、基础指标公式](#二基础指标公式)
- [三、买点战法（B1 / B2 / B3 / 超级B1）](#三买点战法)
- [四、复合战法（长安等）](#四复合战法)
- [五、评分型策略（perfect / oversold / breakout）](#五评分型策略)
- [六、形态评分（沙漏 / 蜈蚣图）](#六形态评分)
- [七、量能策略（量比战法）](#七量能策略)
- [八、结构型策略（三波 / 麒麟 / 牛绳）](#八结构型策略)
- [九、硬过滤器](#九硬过滤器)
- [十、参数修改指南](#十参数修改指南)

---

## 零、全貌：17 种选股策略

来源：`modules/screener/criteria.py` 的 `_CRITERIA_REGISTRY`

| # | 策略名 | 类型 | 判定依据 | 代码位置 |
|---|---|---|---|---|
| 1 | `b1` | 评分阈值 | `b1_score >= 50` | criteria.py:61 |
| 2 | `perfect` | 评分阈值 | `score >= 65` | criteria.py:66 |
| 3 | `oversold` | 评分阈值 | `trend_score <= 40` | criteria.py:71 |
| 4 | `breakout` | 评分阈值 | `volume_score >= 70` | criteria.py:76 |
| 5 | `super_b1` | 战法信号 | `detect_sb1` 近 5 日命中 | criteria.py:84 |
| 6 | `changan` | 战法信号 | `detect_changan` 近 5 日命中 | criteria.py:96 |
| 7 | `b2_breakout` | 战法信号 | `detect_b2` 近 5 日命中 | criteria.py:108 |
| 8 | `b3_consensus` | 战法信号 | `detect_b3` 近 5 日命中 | criteria.py:120 |
| 9 | `build_wave` | 结构判定 | 三波=`建仓波` 且 conf≥0.5 | criteria.py:135 |
| 10 | `xishou` | 结构判定 | 麒麟=`吸筹` 且 conf≥0.5 | criteria.py:146 |
| 11 | `safe` | 结构判定 | 非冲刺波 且 非派发/回落 | criteria.py:157 |
| 12 | `bull_rope` | 指标判定 | 牛绳=`牵牛` 且 is_bullish | criteria.py:172 |
| 13 | `sandglass_perfect` | 形态评分 | 沙漏完美 或 score≥80 | criteria.py:184 |
| 14 | `volume_ratio_super` | 量能判定 | 量比场景∈{超级攻击,攻击日,单向拉升} | criteria.py:196 |
| 15 | `simple_perfect_1` | 形态判定 | 温和放量上涨→顶部无量→缩量回调 + J 负值 + 低点抬高 | simple_perfect.py |
| 16 | `simple_perfect_2` | 形态判定 | 长期横盘(振幅<15%) → 放量异动 → 异动后仍横住±8% | simple_perfect.py |
| 17 | `simple_perfect_3` | 形态判定 | 放量站上大哥线→一波流≥20%→顶部放量下杀→缩量消化且不破黄线 | simple_perfect.py |

**信号类策略的回溯窗口**（均为「近 5 日内出现过即算命中」）：

| 策略 | 起始索引 | 说明 |
|---|---|---|
| `super_b1` | `max(10, len-5)` | 至少 10 根 K 线 |
| `changan` | `max(3, len-5)` | 至少 3 根 |
| `b2_breakout` | `max(15, len-5)` | 至少 15 根 |
| `b3_consensus` | `max(20, len-5)` | 至少 20 根 |

---

## 一、参数可改性总表

### 1.1 可动态覆盖的参数（`get_active_param`，5 个）

这些参数通过 `modules/self_optimizer/param_registry.py::get_active_param()` 读取，
**可被 Darwin 自优化（`zt self-optimize`）运行时覆盖**，无需改代码。

| 参数路径 | 默认值 | 作用 | 代码位置 |
|---|---|---|---|
| `b1.j_threshold` | **-10** | B1 的 J 值上限（J 必须 < 此值） | base_strategies.py:40 |
| `b1.green_brick_limit` | **4** | 近 4 根中阴线数达此值则排除 | base_strategies.py:47 |
| `b1.rsi6_ceiling` | **25** | RSI6 低于此值 → 超卖加分 | base_strategies.py:84 |
| `b1.adx_floor` | **40** | ADX 高于此值 → 动能竭尽加分 | base_strategies.py:91 |
| `b2.min_pct` | **4.0** | B2 放量长阳的最小涨幅(%) | base_strategies.py:177 |
| `sb1.j_negative_threshold` | **-5** | 超级B1 的 J 值上限 | base_strategies.py:349 |

> 注意：`get_active_param` 的调用点是**硬编码**的。上述 6 个之外的参数
> （如 B3 的 `pct_chg < 2`、长安的 `J < -13`）虽然写死在代码里，
> 但**改源码即可生效**，属于「改代码可改」而非「运行时可改」。

### 1.2 查看当前实际生效值

```bash
.venv/bin/python -c "
from modules.self_optimizer.param_registry import _ACTIVE_OVERRIDES
print(_ACTIVE_OVERRIDES or '{} （无覆盖，全部使用默认值）')"
```

> ⚠️ 若跑过 `zt self-optimize`，文档中的默认值可能已不是实际生效值。

### 1.3 参数可改性分级

| 级别 | 含义 | 修改方式 | 数量 |
|---|---|---|---|
| **运行时可改** | `get_active_param` 包裹 | 自优化自动改 / `set_active_params()` | 6 个 |
| **配置可改** | 集中在常量或配置模块 | 改常量 | 少量 |
| **改代码可改** | 散落在函数体内的字面量 | 编辑源码 | 绝大多数 |

---

## 二、基础指标公式

所有策略依赖这些基础指标，参数固定（**改代码可改**）。

| 指标 | 公式 / 参数 | 代码位置 |
|---|---|---|
| **KDJ** | RSV=(C-L9)/(H9-L9)×100；K=2/3·K'+1/3·RSV；D=2/3·D'+1/3·K；**J=3K-2D**（参数 9,3,3） | `indicators/core.py` |
| **MACD** | DIF=EMA12-EMA26；DEA=EMA9(DIF)；**柱=2×(DIF-DEA)**（A股口径） | `indicators/core.py` |
| **BBI** | (MA3+MA6+MA12+MA24)/4 | `indicators/core.py` |
| **白线 zg_white** | `EMA(EMA(C,10),10)` | signal_dictionary.md |
| **大哥线 dg_yellow** | `(MA14+MA28+MA57+MA114)/4` | signal_dictionary.md |
| **BOLL** | 中轨=MA20；上下轨=中轨±2σ（带宽=(上-下)/中） | `indicators/core.py` |
| **RSI** | 周期 6/12/24 | `indicators/core.py` |
| **DMI/ADX** | 标准 DMI，ADX 为动向平均数 | `indicators/core.py` |
| **量比** | `当日量 / 5日均量`（**日级别**，无分钟数据） | `indicators/core.py` |
| **振幅** | `(high-low)/prev_close×100` | 各策略内 |

---

## 三、买点战法

### 3.1 B1 —— 缩量回调买点

**代码**：`modules/strategies/base_strategies.py:12-124`

**前置条件**

```
index >= 10                                    # 至少 10 根 K 线
```

**核心过滤（不满足直接返回 None）**

| 条件 | 表达式 | 参数 | 可改性 |
|---|---|---|---|
| J 值超卖 | `J < j_threshold` | **-10** | ✅ 运行时 |
| 非连续阴线 | `近4根阴线数 < green_brick_limit` | **4** | ✅ 运行时 |

**置信度计算**

```
confidence = 0.5
           + 0.1                     if 缩量 (is_suoliang)
```

**MDC 多维加分（每项独立叠加）**

| 因子 | 条件 | 加减 | 可改 |
|---|---|---|---|
| 麒麟·吸筹 | `stage == "吸筹"` | **+0.20** | ❌ |
| 麒麟·回落 | `stage == "回落"` | +0.10 | ❌ |
| 麒麟·派发 | `stage == "派发"` | **−0.30** | ❌ |
| 布林下轨 | `close <= boll_lower × 1.02` | +0.15 | ❌ |
| 主力资金 | `large_inflow > large_outflow` | +0.10 | ❌ |
| RSI 超卖 | `RSI6 < rsi6_ceiling` | +0.05 | ✅ 运行时(25) |
| ADX 高位 | `ADX > adx_floor` | +0.10 | ✅ 运行时(40) |
| MACD 底背离 | `is_bottom_divergence`（已保证 DIF<0） | +0.15 | ❌ |

```
最终 confidence = clamp(0.1, 0.98)
止损 = today.low
```

**理论最大置信度**：0.5+0.1+0.2+0.15+0.1+0.05+0.1+0.15 = **1.35 → 截断至 0.98**

**文档出处**：`knowledge/reference/thresholds.md:84-92`

| 文档指标 | 阈值 |
|---|---|
| J 值 | ≤ -10（KDJ 9,3,3） |
| 涨幅 | -2% ~ 1.8% |
| 振幅 | < 7% |
| 累计换手率 | < 38% |
| 自由换手率(L2) | < 62% |

> ⚠️ **文档与代码差异**：文档的「涨幅/振幅/换手率」三项在 `detect_b1` 代码中**未实现**，
> 仅体现在评分函数 `score_b1_opportunity` 的近似因子中（见 5.1）。

---

### 3.2 B2 —— 放量突破确认

**代码**：`base_strategies.py:127-262`

```
index >= 15
```

**核心过滤**

| 条件 | 表达式 | 参数 |
|---|---|---|
| 前置 B1 | 前 5~14 日内存在 `J < -10` | -10（**硬编码**，非 get_active_param） |
| 放量长阳 | `pct_chg >= b2_min_pct` **且** `is_beidou` | **4.0** ✅运行时 |

**置信度**

```
confidence = 0.60
```

**MDC 加分**

| 因子 | 条件 | 加减 |
|---|---|---|
| 麒麟·拉升 | `stage=="拉升"` | +0.20 |
| 麒麟·吸筹 | `stage=="吸筹"` | +0.10 |
| 麒麟·派发 | `stage=="派发"` | **−0.40** |
| 突破布林中轨 | 昨收<昨中轨 且 今收>今中轨 | +0.15 |
| 布林开口 | `今width > 昨width × 1.05` | +0.05 |
| 主力强流入 | `净流入/成交额 > 0.05` | +0.15 |
| DMI 金叉 | 昨 +DI<−DI 且 今 +DI>−DI | +0.10 |

```
confidence = clamp(0.1, 0.98)     止损 = today.low
```

---

### 3.3 B3 —— 分歧转一致（中继买点）

**代码**：`base_strategies.py:265-312`

```
index >= 20
```

| 条件 | 表达式 | 参数 |
|---|---|---|
| 前置 B2 | 前 3~9 日内存在 `pct_chg>=4 且 is_beidou` | 4（硬编码） |
| 小阳线 | `0 < pct_chg < 2` | 2（硬编码） |
| 振幅 | `amplitude < 7` | 7（硬编码） |

```
confidence = 0.7（固定）     止损 = today.low
```

> 全部参数硬编码，**改代码可改**。无 `get_active_param`。

---

### 3.4 超级B1（SB1）—— 震仓企稳

**代码**：`base_strategies.py:315-371`

```
index >= 10
```

| 条件 | 表达式 | 参数 | 可改 |
|---|---|---|---|
| 前2日放量下跌 | `prev_2.close < prev_2.open` 且 `prev_2.vol > prev_3.vol × 1.5` | 1.5 | ❌ |
| J 值 | `J < sb1_j_threshold` | **-5** | ✅ 运行时 |
| 今日缩量 | `today.is_suoliang`（记录但**未用于判定**） | — | — |

```
confidence = 0.9（固定）
止损 = prev_2.low        # 注意：用前2日最低价，非当日
```

> ⚠️ 实现细节：`is_suoliang` 被计算并写入 `details`，但**不参与过滤条件**，
> 因此「继续缩量企稳」这一文档条件在代码中未生效。

---

## 四、复合战法

### 4.1 长安战法（三日形态，胜率 75%）

**代码**：`modules/strategies/compound_strategies.py:6-75`

```
index >= 3
```

**三日条件（全部满足）**

| 日 | 条件 | 表达式 | 参数 |
|---|---|---|---|
| Day1 | B1 | `J1 < -13` | -13（硬编码） |
| Day2 | 放量长阳 + J 拐头 | `pct_chg>=4` 且 `is_beidou` 且 `J2 > J1` | 4（硬编码） |
| Day3 | 分歧转一致 + 缩半量 | `0 < pct_chg < 2` 且 `amplitude < 7` 且 `vol <= Day2.vol × 0.5` | 2/7/0.5 |

**置信度**

```
confidence = 0.75
           + 0.15   if Day2 净流入/成交额 > 0.05
           + 0.10   if 麒麟 stage == "拉升"
= min(confidence, 0.98)        止损 = Day3.low
```

**文档出处**：`knowledge/advanced-patterns.md`（标注来源 `TANGOO 09`、`复盘专用z 10`）

### 4.2 其他复合战法（`detect_all_strategies` 会检测，但不直接用于选股）

| 战法 | 核心条件 | 代码位置 |
|---|---|---|
| 四分之三阴量 | 大阳线后次日阴量 > 阳量 × 0.75 → 判为假突破 | compound_strategies.py:78 |
| 娜娜 | — | :122 |
| 异动地量 | — | :198 |
| 平行重炮 | — | :257 |
| 坑里起好货 | — | :337 |
| 对称 VA | — | :409 |

> 这些在 `detect_all_strategies()` 中会被检测并输出信号，
> 但**未注册到 `_CRITERIA_REGISTRY`**，因此 `zt screen` 无法按它们筛选。

---

## 五、评分型策略

评分函数位于 `modules/screener/scoring.py`。

### 5.1 `b1` —— B1 机会评分（`score_b1_opportunity`）

**代码**：`scoring.py:78-171`，要求 `len(klines) >= 20`

| 因子 | 条件 | 加分 |
|---|---|---|
| **J 值** | `J < -15` | **+35** |
| | `-15 <= J < -10` | +25 |
| | `-10 <= J < 0` | +15 |
| 缩量回调 | `today.vol < MA5(vol) × 0.6` | +20 |
| BBI 下方 | `close < BBI` | +15 |
| 均线区间 | `MA20 < close < MA60` | +15 |
| 沙漏·缩量收敛 | 因子分 `>= 12` | +10 |
| | `>= 8` | +5 |
| 沙漏·枢轴邻近 | 因子分 `>= 16` | +8 |
| | `>= 12` | +4 |
| 沙漏完美 | `is_perfect` | +15 |
| | `score >= 65` | +5 |
| **风险扣分** | `J > 0` | **−10** |
| | `close > BBI × 1.05` | **−15** |

```
b1_score = clamp(0, 100)
选股条件：b1_score >= 50
```

### 5.2 `perfect` —— 完美图形评分（`is_perfect_pattern`）

**代码**：`scoring.py:17-75`，要求 `len(klines) >= 30`

| 判定项 | 满足 → reasons | 否则 → warnings |
|---|---|---|
| 价格在 BBI 之上 | `close > BBI` | 「价格在BBI下方」 |
| 缩量整理 | `vol < MA5(vol) × 0.7` | `vol > MA5(vol) × 1.5` → 「放量突破，需观察」 |
| 均线多头 | `MA5 > MA10 > MA20` | `MA5 < MA10` → 「均线空头」 |
| 非高位 | 距 60 日高点回撤 `> 30%` | 回撤 `< 10%` → 「接近历史高位」 |

```
is_perfect = (reasons 数 >= 2) 且 (warnings 数 == 0)
```

> 注意：`is_perfect_pattern` 返回布尔，但选股用的 `perfect` 策略判定的是
> **综合评分 `score >= 65`**（criteria.py:68），两者不同。

### 5.3 `oversold` —— 超跌（趋势评分 `score_trend`）

**代码**：`scoring.py:174-235`，要求 `len(klines) >= 20`

```
基础判定：
  MA5>MA20>MA60 且 close>BBI  → 上升：80（涨）或 70（跌）
  MA5<MA20<MA60 且 close<BBI  → 下降：30
  其他                        → 震荡：50

短期动能：近5日涨幅和 > 10 → +10；< -10 → −10

牛绳调整：
  牵牛    +10      牛绳断  −20
  金叉    +15      死叉    −25

选股条件：trend_score <= 40        # 即"超跌"= 趋势分低
```

### 5.4 `breakout` —— 放量突破（量价评分 `score_volume_pattern`）

**代码**：`scoring.py:238-310`，要求 `len(klines) >= 10`

```
起始分 = 50

量比战法 6 场景（优先）：
  超级攻击  +30      出货日  −25
  攻击日    +25      弱势日  −15
  单向拉升  +18
  正常震荡：action=="慢买逢低吸纳" → +5；否则「观望」不加

降级路径（量比战法失败时）：
  量比 >= 2.0   +20（倍量）
  >= 1.5        +10（放量）
  <= 0.5        +10（缩量）
  其他           −5（量能正常）

补充验证：
  pct_chg > 3  且 量比 > 1.2   → +15（价涨量增）
  pct_chg < -3 且 量比 > 1.2   → −15（价跌量增）

选股条件：volume_score >= 70
```

### 5.5 风险评分（`score_risk`，不直接用于选股，但影响综合分）

**代码**：`scoring.py:313-373`

```
起始 = 100（越高越安全）

距 60 日高点回撤 < 10%   → −30（接近历史高位）
                 < 20%   → −15（相对高位）
close < BBI              → −20（跌破BBI）
近 5 日有放量阴线         → −10（close<prev.close 且 vol>prev.vol×1.5）
连续 3 日下跌            → −15
蜈蚣图                   → −30
```

---

## 六、形态评分

### 6.1 沙漏评分 V9（五因子，各 0-20，总 0-100）

**代码**：`modules/indicators/price_patterns/sandglass.py:5+`，要求 `len >= 20`

**因子 1：缩量/收敛**

```
子A（10日均量 / 20日均量）：
  < 0.6 → 12     < 0.8 → 8     < 1.0 → 4     否则 → 0
子B（量幅收窄：近5日量幅 / 前5日量幅）：
  < 0.5 → 8      < 0.8 → 5     < 1.0 → 3     否则 → 0
因子1 = min(20, A + B)
```

**因子 2：枢轴邻近**（距近期支撑位距离）

```
<= 3% → 20      <= 5% → 16      <= 8% → 12
<= 10% → 8      <= 15% → 4      否则 → 0
```

**因子 3：量能斜率**（归一化斜率）

```
[-0.05, -0.01]  → 20      [-0.10, -0.05) → 15
(-0.01, 0.02]   → 12      [-0.15, -0.10) → 8
> 0.05          → 2       其他 → 5
```

**因子 4：均线结构**

```
MA5>MA10>MA20        → +10
MA5>MA10 或 MA10>MA20 → +5
close > MA20         → +4
均线收敛度 (MA5-MA20)/MA20：
  < 2% → +6      < 5% → +4      < 8% → +2
```

**因子 5：事件风险**（从 20 分起扣，检查跳空/连跌/异常放量/近高点）

**选股用法**

| 场景 | 阈值 | 代码 |
|---|---|---|
| `sandglass_perfect` | `is_perfect` 或 `score >= 80` | criteria.py:190 |
| 硬过滤（沙漏最低分） | `score < 50` 则排除 | criteria.py:46-55 |
| B1 评分融合 | 见 5.1 | scoring.py:128 |

### 6.2 蜈蚣图（风险形态，五因子各 0-20）

**代码**：`modules/indicators/price_patterns/screener_helper.py:260+`

| 因子 | 含义 |
|---|---|
| 长上影线比例 | — |
| 长下影线比例 | — |
| 十字星比例 | — |
| 量能无规律 | — |
| 价格无趋势 | — |

**用途**：硬过滤（`_check_centipede`）+ 风险评分 −30

> 检测失败时不触发过滤（fail-safe，见 criteria.py:40-43）

---

## 七、量能策略

### 7.1 量比战法（`detect_volume_ratio_strategy`）

**代码**：`modules/indicators/volume_patterns.py:366-500+`，要求 `len >= 6`

**量比定义**：`当日量 / 5日均量`（日级别，因无分钟数据）

**六场景决策表**（按代码判断顺序）

| 顺序 | 条件 | 场景 | action | 置信度 |
|---|---|---|---|---|
| 1 | 量比 > 40 且 涨 | **超级攻击** | 立即买 | — |
| 2 | 量比 > 20 且 涨 | 攻击日 | 立即买 | — |
| 3 | 量比 > 20 且 暴跌 | 出货日 | 观望 | — |
| 4 | 10 ≤ 量比 ≤ 20 且 量价齐升 | 单向拉升 | 买 | — |
| 5 | 10 ≤ 量比 ≤ 20 且 低开 < −2% | 弱势日 | 观望 | 0.70 |
| 6 | 量比 < 10 且 跌 < −2% | 弱势日 | 跳过不看 | 0.75 |
| 7 | 量比 < 10 | 正常震荡 | 慢买逢低吸纳 | 0.60 |
| 8 | 量比 > 20（涨幅 −3%~1% 不明确） | 出货日 | 观望 | 0.60 |

**选股用法**（`volume_ratio_super`）
```python
action == "立即买" 或 scenario ∈ {"超级攻击", "攻击日", "单向拉升"}
```

**文档出处**：`knowledge/trading-core.md` 3.6 量比战法

---

## 八、结构型策略

### 8.1 三波理论（`detect_three_waves`）

| 阶段 | 选股用途 |
|---|---|
| 建仓波 | `build_wave`：wave==`建仓波` 且 conf ≥ **0.5** |
| 拉升波 | — |
| 冲刺波 | `safe` 策略排除 |

### 8.2 麒麟会四阶段（`detect_kirin_stage`）

| 阶段 | 用途 |
|---|---|
| 吸筹 | `xishou`：stage==`吸筹` 且 conf ≥ **0.5** |
| 拉升 | B2 加分 |
| 派发 | `safe` 排除；B1 −0.30；B2 −0.40 |
| 回落 | `safe` 排除；B1 +0.10 |

### 8.3 牛绳理论（`detect_bull_rope`）

| 状态 | 用途 | 趋势评分调整 |
|---|---|---|
| 牵牛 | `bull_rope` 策略（需 `is_bullish`） | +10 |
| 牛绳断 | — | −20 |
| 金叉 | — | +15 |
| 死叉 | — | −25 |

### 8.4 `safe` 策略

```python
wave != "冲刺波" 且 kirin_stage not in ("派发", "回落")
```

---

## 九、硬过滤器

**代码**：`criteria.py:34-55`（在任何评分之前执行）

| 过滤器 | 条件 | 失败处理 |
|---|---|---|
| 蜈蚣图 | `detect_centipede_pattern().is_centipede` | 直接排除 |
| 沙漏最低分 | `calculate_sandglass_score().score < 50` | 直接排除 |

> 两者异常时**不触发过滤**（fail-safe，记录 warning 后继续）

---

## 十、参数修改指南

### 10.1 运行时改（不改代码）

适用于 6 个 `get_active_param` 参数：

```python
from modules.self_optimizer.param_registry import using_params

with using_params({"b1": {"j_threshold": -15}}):
    # 此上下文内 B1 的 J 阈值变为 -15
    ...
```

或跑自优化自动搜索：

```bash
zt self-optimize run --target trading --rounds 3
```

### 10.2 改代码（永久生效）

| 想改什么 | 改哪里 |
|---|---|
| B1 的 J / 绿砖 / RSI / ADX 默认值 | `base_strategies.py:40,47,84,91` 第三个参数 |
| B2 最小涨幅 | `base_strategies.py:177` |
| SB1 的 J 阈值 | `base_strategies.py:349` |
| B3 的 涨幅/振幅 | `base_strategies.py:295` |
| 长安的 J<-13 / 涨幅 / 缩半量 | `compound_strategies.py:29,34,40,42` |
| 各评分阈值（50/65/40/70） | `criteria.py:63,68,73,78` |
| 评分函数内各加分 | `scoring.py` 对应行 |
| 沙漏因子阈值 | `sandglass.py` |
| 量比场景阈值 | `volume_patterns.py:421-500` |
| 信号回溯窗口（近 5 日） | `criteria.py:88,100,112,124` |

### 10.3 注意事项

1. **改前先跑测试**：`pytest tests/test_strategies.py tests/test_screener.py -q`
2. **改评分阈值会影响选股结果数量**，建议先用 `--limit` 小样本验证
3. **改 `get_active_param` 默认值不等于改 override**：自优化的 override 优先级更高
4. **文档与代码可能不同步**：本文件从代码提取，如与 `knowledge/` 下的 md 冲突，**以代码为准**

---

## 附：已知的代码与文档差异

| 项 | 文档说法 | 代码实现 | 影响 |
|---|---|---|---|
| B1 涨幅/振幅/换手率 | thresholds.md:84-92 列出 | `detect_b1` 未实现 | 文档条件未生效 |
| SB1 缩量企稳 | 列为必要条件 | 计算但未参与过滤 | 条件未生效 |
| B1 评分 J 分档 | 未提及 | -15/-10/0 三档 | 文档缺失 |
| 复合战法（娜娜/异动地量等） | advanced-patterns.md 有描述 | 未注册到选股注册表 | 无法用于 `zt screen` |
| `oversold` / `safe` 策略 | 几乎无文档 | 有实现 | 用户不知道存在 |

> 建议：将本文档作为「公式事实来源」，后续代码改动同步更新本文件。

---

## 十一、简单完美图形（三种形态）

**来源**：笔记《交易系统.md》§2.2.3「完美图形选股」，实现于 `modules/screener/simple_perfect.py`，
注册为 `simple_perfect_1/2/3`，CLI 别名为 `简单完美图形-1/2/3`。

> ⚠️ 与「复杂完美图形」区分：`is_perfect_pattern`（§5.2，BBI 之上 + 缩量 + 均线多头 + 非高位）
> 与本节三种形态是**两套独立逻辑**，互不影响。

**总前提**（笔记原文）：异动 + 顶部无量 + 缩量回踩 + 绝对涨幅没有翻倍。

### 11.1 `simple_perfect_1` —— 经典

| 子条件 | 判定 | 阈值出处 |
|---|---|---|
| 温和放量上涨 | 近 30 根内连续 ≥2 根上涨，且 `vol > 昨量 × 1.2` | 1.2 出自 `screener_helper.py:215` |
| 顶部无量 | 上涨段后 3 根内无 `is_fangliang_yinxian`（下跌 + 放量） | `detect_volume_pattern` 口径 |
| 缩量回调 | 上涨段后**至少 1 根**，其量 ≤ **上涨段最大量 × 0.5**（真·缩半量） | 笔记「长阳之后突然缩半量才是最好的」+ 实战口径「缩量至少一根」；比例与根数均可调 |
| J 达大负值 | 近 5 根内出现过 `J ≤ 0` | `detect_nana` 口径（J < 0） |
| 低点抬高 | 回调段最低点 > 上涨段起点低点（排除大爷图） | 笔记「低点不断降低 = 大爷图」 |
| MACD 向上 | `DIF` 或 `DEA` 较前一日上行 | 笔记原文 |
| 绝对涨幅未翻倍 | `close < 近 60 日最低 × 2.0` | 笔记「绝对涨幅没有翻倍」 |

### 11.2 `simple_perfect_2` —— 异动后的横盘

| 子条件 | 判定 | 阈值出处 |
|---|---|---|
| 长期横盘 | 近 20 根振幅 `< 15%` | `detect_yueyu_yushi`（complex_patterns.py:548） |
| 异动 | 单根放量大阳（涨幅 >5% 且 `vol ≥ 前5日均量 ×1.5`）**或** 多根密集阳线（2 根连续放量阳线累计 >5%） | 单根口径来自 `detect_zaihou_chongjian`；密集阳线为笔记原文补充 |
| 异动后仍横住 | 异动后 ≥5 根，落在异动日区间 `±8%` 内 | 经验默认值（参数 `box_tolerance` / `box_min_bars`） |
| 排除庄股 | 底部区间缩量涨停（`pct ≥9.8%` 且 `vol < 前5日均量 ×0.7` 且 `close ≤ 60日最低 ×1.1`）不入选 | 笔记 §2.3 选股避雷 |
| 绝对涨幅未翻倍 | 同 11.1 | 笔记原文 |

### 11.3 `simple_perfect_3` —— 完美绿帽 / W 型筑底

| 子条件 | 判定 | 阈值出处 |
|---|---|---|
| 一波流 | 近 60 根内定位峰值（距今天 ≥25 根），峰值相对其前 40 根最低点涨幅 `≥ 20%` | 20% 为经验默认值（`wave_min_gain`） |
| 大哥线启动 | 底部→峰值之间曾出现 `close > 黄线` 且 `vol ≥ 前5日均量 ×1.5` | 黄线 = `(MA14+MA28+MA57+MA114)/4`；放量口径同 `detect_zaihou_chongjian` |
| 顶部放量下杀 | 峰值后 3 根内出现下跌且 `vol > 昨量 ×1.5`（大绿帽） | 波动阈值同 `is_fangliang_yinxian` |
| 时间换空间 | 绿帽后 ≥20 根，且消化期均量 ≤ 上涨段均量 ×0.7、后半段低点不创新低 | 20 根为经验默认值（`digest_min_bars`） |
| 未跌破黄线 | `close ≥ 黄线 × 0.98` | ±2% 容差沿用 `detect_zaihou_chongjian` |
| 白线未死叉 | 白线（`EMA(EMA(C,10),10)`）仍在黄线之上 | 笔记「白线没死叉」 |
| 绝对涨幅未翻倍 | 同 11.1 | 笔记原文 |

### 11.4 阈值可调性

**有出处的阈值写死**（缩半量 0.5 记录在 `SUOLIANG_RATIO` / 未翻倍 2.0 / `J<0` / 放量 1.5× /
横盘 15%·20 根 / 黄线 ±2%），**无出处的经验默认值全部注册到** `self_optimizer.param_registry`
的 `simple_perfect` 组，可被 Darwin 自优化覆盖：

| 参数 | 默认 | 说明 |
|---|---|---|
| `pullback_vol_ratio` | 0.5 | 类型A 缩量比例：回调量 / 上涨段**最大量**的上限（默认＝缩半量） |
| `pullback_min_bars` | 1 | 类型A 缩量回调至少需要的根数（笔记字面为 2，可用此参数切回） |
| `box_tolerance` | 0.08 | 类型B 异动后箱体容差 |
| `box_min_bars` | 5 | 类型B 异动后最少横住根数 |
| `digest_min_bars` | 20 | 类型C 绿帽后消化窗口 |
| `wave_min_gain` | 0.20 | 类型C 一波流最小累计涨幅 |

### 11.5 实测命中率（2026-09-30 数据）

| 策略 | `zt screen --limit 0`（前 500 只） | 全市场直扫 5562 只 |
|---|---|---|
| `simple_perfect_1` | 12 只 | — |
| `simple_perfect_2` | 15 只 | 约 25/300 抽样 ≈ 8% |
| `simple_perfect_3` | 0 只（前 500 未命中） | **6 只**（000526.SZ / 000665.SZ / 002088.SZ / 002322.SZ / 002329.SZ / 301336.SZ） |

> 注意：`zt screen` 与 API 的 `limit` 都是**扫描数量**（从股票池按代码排序取前 N 只跑判定，上限 500），
> **不是返回条数**；返回条数由 `--top N`（CLI）或 `top` 字段（API，0=全部命中）控制。
> 前端选股页对应两个下拉：「扫描数量」（50/100/200/500）与「返回条数」（10/20/50/全部）。
> 结果标题会显示 `命中 X 只 / 扫描 Y 只，展示 Z 只`。
