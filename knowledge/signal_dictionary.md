# Zettaranc 信号解读字典（输出）

> 版本: v2.0 | 日期: 2026-04-28
>
> 用途：告诉 agent 如何理解 `analyze_stock()` 返回的结构化数据。
>
> **原则**：Python 只输出 True/False/数字/枚举，agent 根据本字典理解信号含义后，用 Z 哥的口吻翻译给用户。
>
> 对应输入数据字典 → `data_dictionary.md`

---

## 一、MACD 信号

| 字段 | 类型 | 含义 |
|------|------|------|
| `is_dif_positive` | bool | DIF > 0，多头区间 |
| `is_dif_cross_zero` | bool | DIF 上穿 0 轴（红点） |
| `is_dif_cross_zero_down` | bool | DIF 下穿 0 轴（绿点） |
| `macd_gold_cross` | bool | DIF 上穿 DEA（金叉） |
| `macd_dead_cross` | bool | DIF 下穿 DEA（死叉） |
| `is_gold_fake` | bool | 金叉空——金叉后立刻死叉，诱多 |
| `is_dead_fake` | bool | 死叉多——死叉后立刻金叉，空中加油 |
| `is_top_divergence` | bool | 顶背离——价新高 DIF 未新高 |
| `is_bottom_divergence` | bool | 底背离——价新低 DIF 未新低 |
| `macd_veto` | bool | 一票否决——DIF<0 且无底背离，不能买 |

**agent 解读提示**：
- `is_gold_fake=True` → "A股最恶毒的诱多，金叉空"
- `macd_veto=True` → "MACD一票否决，DIF在0轴下面还没有底背离，不能碰"
- `is_top_divergence=True` → "价格到了前高附近但DIF跟不上，趋势在衰竭"

---

## 二、KDJ/RSI/WR 指标

| 字段 | 类型 | 含义 |
|------|------|------|
| `k`, `d`, `j` | float | KDJ 三值 |
| `rsi6`, `rsi12`, `rsi24` | float | RSI 多周期 |
| `wr5`, `wr10` | float | 威廉指标（-100~0） |

**agent 解读提示**：
- `j < -10` → J 值进入负值区，B1 买点候选
- `j > 80` → 超买区域
- `rsi6 > 80` → 短期超买
- `wr5 < -80` → 超卖

---

## 三、均线/布林带

| 字段 | 类型 | 含义 |
|------|------|------|
| `bbi` | float | BBI 多空指标 |
| `ma5`, `ma10`, `ma20`, `ma60` | float | 均线 |
| `boll_mid`, `boll_upper`, `boll_lower` | float | 布林带三轨 |
| `boll_width` | float | 布林带宽度（%） |
| `boll_position` | float | 股价在布林带中的位置（0-100%） |
| `vol_ratio` | float | 量比 |

---

## 四、双线战法

| 字段 | 类型 | 含义 |
|------|------|------|
| `zg_white` | float | Z哥白线 EMA(EMA(C,10),10) |
| `dg_yellow` | float | 大哥线 (MA14+MA28+MA57+MA114)/4 |
| `is_gold_cross` | bool | 白线上穿大哥线 |
| `is_dead_cross` | bool | 白线下穿大哥线 |

**agent 解读提示**：
- `zg_white > dg_yellow` → 白线在黄线之上，主力在场
- `is_dead_cross=True` → 白线死叉黄线，最后离场时机
- 白线和黄线之间的区域 = "碗"，碗越大容错率越高

---

## 五、单针信号

| 字段 | 类型 | 含义 |
|------|------|------|
| `rsl_short` | float | 短期 RSL（3日） |
| `rsl_long` | float | 长期 RSL（21日） |
| `is_needle_20` | bool | 单针下20——RSL_S≤20 AND RSL_L≥60 |
| `is_needle_30` | bool | 单针下30——RSL_L>85 AND RSL_S<30（量化资金迭代版） |

---

## 六、异动选股法

| 字段 | 类型 | 含义 |
|------|------|------|
| `is_yidong` | bool | 当日是否异动 |
| `yidong_type` | str | 异动类型：`詹姆斯级` / `徐杰级` |
| `yidong_vol_ratio` | float | 异动当日量比 |
| `yidong_above_60d` | bool | 是否从60日线附近起来 |

**分级规则**（agent 根据 type 判断）：
- `詹姆斯级` → 量比≥3.0 + 涨幅≥5% + 5日≥3根阳线，主力建仓信号
- `徐杰级` → 量比≥2.0 + 涨幅≥2%，单根放量阳线

---

## 七、砖型图

| 字段 | 类型 | 含义 |
|------|------|------|
| `brick_value` | float | 砖值 |
| `brick_trend` | str | `RED` / `GREEN` / `NEUTRAL` |
| `brick_count` | int | 当前连续砖数 |
| `brick_trend_up` | bool | 命值趋势上升 |
| `is_fanbao` | bool | 精准反包（2/3位置） |
| `is_brick_flip_green` | bool | 红砖刚翻绿，止损信号 |
| `brick_consecutive` | int | 四块砖体系下的连续砖数 |
| `brick_action` | str | `减仓` / `止损` / `持有` / `禁止抄底` / `观望` |
| `brick_action_desc` | str | 操作描述 |

**四块砖规则**（agent 根据 action + consecutive 判断）：
- `brick_action='止损'` → 红翻绿，立刻止损
- `brick_consecutive >= 4 AND brick_trend='RED'` → 红砖满4块，至少减仓一半
- `brick_action='禁止抄底'` → 绿砖下跌中，绝不抄底，先数4块
- `brick_action='持有'` → 红砖上涨但未满4块，继续持有

---

## 八、量价形态

| 字段 | 类型 | 含义 |
|------|------|------|
| `is_beidou` | bool | 倍量——今日量≥昨日量×2 |
| `is_suoliang` | bool | 缩量——今日量≤昨日量×0.5 |
| `is_jiayin_zhenyang` | bool | 假阴真阳——收<开但收>昨收 |
| `is_jiayang_zhenyin` | bool | 假阳真阴——收>开但收<昨收 |
| `is_fangliang_yinxian` | bool | 放量阴线——跌+量>昨量×1.5 |

---

## 九、B1/B2/B3 战法

| 字段 | 类型 | 含义 |
|------|------|------|
| `is_b1` | bool | B1 建仓波信号 |
| `b1_j_value` | float | B1 当日 J 值 |
| `b1_amplitude` | float | B1 振幅（%） |
| `b1_pct_chg` | float | B1 涨幅（%） |
| `b1_volume_shrink` | bool | B1 当日是否缩量 |
| `b1_score` | int | B1 评分（0-4，满足条件数） |
| `b1_rally_pct` | float | 建仓波涨幅（%） |
| `b1_pass_30` | bool | 是否通过两个30%原则（涨幅25%-40%） |
| `is_b2` | bool | B2 突破信号 |
| `b2_follows_b1` | bool | 是否在 B1 后5天内 |
| `b2_pct_chg` | float | B2 涨幅 |
| `b2_j_value` | float | B2 当日 J 值 |
| `b2_volume_up` | bool | B2 是否放量 |
| `b2_score` | int | B2 评分（0-4） |
| `is_b3` | bool | B3 买点——B2 后缩量回踩不破低点 |

**agent 解读提示**：
- `is_b1=True AND b1_score>=3` → B1 信号可靠
- `is_b2=True` → B1 确认，突破有效
- `is_b3=True` → B2 后缩量回踩，二次买点

---

## 十、高级战法

| 字段 | 类型 | 含义 |
|------|------|------|
| `is_sb1_detailed` | bool | 超级 B1——N型回调→放量大跌→缩量企稳→J负值→反转K |
| `is_double_gun` | bool | 双枪战法——两根放量阳线+中间缩量+间隔3-10天 |
| `double_gun_vol1` | float | 第一枪量比 |
| `double_gun_vol2` | float | 第二枪量比 |
| `double_gun_gap_days` | int | 两枪间隔天数 |
| `is_nana` | bool | 娜娜图——价新高缩量+次高缩量+底部堆量 |
| `is_sb1` | bool | SB1 假摔——跌破前低→反包收回→放量 |
| `is_in_bowl` | bool | 黄金碗——价格在白线和黄线之间 |
| `bowl_upper` | float | 碗上沿（白线） |
| `bowl_lower` | float | 碗下沿（黄线） |
| `breath_phase` | str | `exhale`（放量涨）/ `inhale`（缩量跌）/ `none` |
| `breath_n_type` | bool | N 型结构（低点抬高） |

---

## 十一、关键K/暴力K

| 字段 | 类型 | 含义 |
|------|------|------|
| `key_k_list` | list[dict] | 关键K列表（60日内），每项含 date/type/body_pct/vol_ratio |
| `is_violence_k` | bool | 最新这天是否出现暴力K |
| `violence_k_type` | str | `大暴力` / `小暴力` |
| `violence_k_body` | float | 实体涨幅（%） |

---

## 十二、决策输出

| 字段 | 类型 | 含义 |
|------|------|------|
| `signal` | enum | `B1`/`B2`/`B3`/`SB1`/`S1`/`S2`/`HOLD`/`WATCH` |
| `sell_score` | int | 防卖飞评分（0-5），≥4 继续持有，≤2 准备离场 |
| `sell_items` | dict[str,bool] | 5项明细：收盘上涨/BBI支撑/非放量阴线/趋势向上/KDJ未死叉 |
| `prev_high` | float | 昨日最高价 |
| `prev_low` | float | 昨日最低价 |
| `high_52w` | float | 52周最高价 |
| `high_52w_dist` | float | 距52周高点（%） |

---

## 十三、资金流/DMI

| 字段 | 类型 | 含义 |
|------|------|------|
| `net_lg_mf` | float | 主力净流入 |
| `net_elg_mf` | float | 超大单净流入 |
| `dmi_plus` | float | DMI+ |
| `dmi_minus` | float | DMI- |
| `adx` | float | ADX |

---

## 使用方式

Agent 调用 `analyze_stock(ts_code, days)` 后，拿到 `IndicatorResult` 对象的 dict 表示。
根据本字典理解每个字段含义，再结合 SKILL.md 中的心智模型和表达 DNA，用 Z 哥的口吻输出给用户。

**不需要**把每个字段都念一遍。只挑出触发信号的字段，用 Z 哥的方式组织语言。

例如收到：
```python
{'is_yidong': True, 'yidong_type': '詹姆斯级', 'yidong_vol_ratio': 5.2, 'yidong_above_60d': True}
```

应输出：
> "异动出来了，詹姆斯级，量比5.2倍，从60日线附近起来的。这个量，主力今天是要干点什么的。"
