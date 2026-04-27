<div align="center">

# zettaranc（万千）· 思维操作系统

> *「利润是市场给的，都是概率的事儿，谁也别吹牛逼。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![v2.0-JNB](https://img.shields.io/badge/version-2.0--JNB-red)](CHANGELOG.md)

<br>

**前阳光私募冠军基金经理、B站百大UP主的投资思维框架。**<br>
基于 ~467 篇直播/付费课整理文章（约 200 万字，含 5 个语料源全量解析）+ 13 个 ztalk 视频 transcript（12.7 万字）+ 9 篇股探报告交易心理系列（3.3 万字）的深度蒸馏。

<br>

[看效果](#效果示例) · [安装](#安装) · [JNB数据接入](#jnb-数据接入) · [蒸馏了什么](#蒸馏了什么) · [更新日志](CHANGELOG.md)

</div>

---

## v2.0-JNB：真实数据，真实战场

> **Z哥原话：「你用假数据练出来的全是花架子，上了市场就是被割的命。」**

zettaranc 不再是坐在房间里空谈理论的「嘴炮AI」了。v2.0-JNB 版本接入了**真实 Tushare API 数据源**，让 Z 哥的思维框架跑在真实行情之上——这才是真正的曼城阵容。

### 什么叫 JNB 版本？

**JNB** = 具备**实时数据查询能力**的 Agent 形态。从纯 LLM 文字对话，升级为能看行情、读指标、查资金流向的**实战型交易助手**。

| 能力 | 说明 |
|------|------|
| **实时行情** | 查股价、涨跌幅、量比、市值 |
| **K线数据** | 日线 OHLCV 历史走势 |
| **技术指标** | MACD/KDJ/RSI/布林带/砖形图/DMI... |
| **资金流向** | 超大单/大单净流入 |
| **财务数据** | PE/PB、营收、利润 |
| **涨停数据** | 当日涨停股列表 |
| **指标缓存** | SQLite 存储每日指标快照，支持历史回测 |
| **曼城阵容** | 内置 10 只重点股真实数据，开箱即用 |

### 数据架构

```
zettaranc-skill/
├── modules/
│   ├── tushare_client.py    # Tushare API 封装（120次/分钟限流）
│   ├── database.py          # SQLite 数据库管理（7 张表）
│   ├── data_sync.py         # 数据同步器（增量/全量）
│   ├── indicators.py        # 技术指标计算引擎（60+ 指标）
│   ├── screener.py          # 选股器（曼城评分体系）
│   ├── strategies.py        # 30+ 战法识别引擎
│   ├── setup_wizard.py      # 初始化配置向导
│   └── zettaranc_voice.py   # Z哥话术生成
├── tests/                   # 单元测试（126 个用例）
│   ├── conftest.py          # 测试基础设施
│   ├── test_database.py
│   ├── test_indicators.py
│   ├── test_screener.py
│   ├── test_strategies.py
│   └── test_setup_wizard.py
└── data/
    └── stock_data.db        # SQLite 数据库（5510 只股票 + 指标缓存）
```

---

## 安装

### 第一步：克隆项目

```bash
# GitHub（主仓库）
git clone https://github.com/lululu811/zettaranc-skill.git
cd zettaranc-skill

# Gitee（自动同步镜像）
git clone https://gitee.com/chenleizzzz/zettaranc-knowledge.git
cd zettaranc-knowledge
```

### 第二步：安装依赖

```bash
pip install -r requirements.txt
```

### 第三步：配置 Tushare Token

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 Tushare Token：

```ini
DATA_MODE=jnb
TUSHARE_TOKEN=你的token
DATA_DIR=data
DB_PATH=data/stock_data.db
```

> **没有 Token？** 前往 [Tushare 官网](https://tushare.pro/) 注册获取。本项目使用的是中转 API 服务（tsy.xiaodefa.cn），不需要高级积分。

### 第四步：初始化数据库 & 同步数据

```bash
# 初始化数据库（创建 7 张表）
python -m modules.database

# 同步股票基本信息（全量 5510 只）
python -m modules.data_sync sync

# 同步单只股票 K 线
python -m modules.data_sync sync --ts_code 000001.SZ --days 365

# 查看同步状态
python -m modules.data_sync status
```

### 第五步：验证

```bash
# 运行测试
python -m pytest tests/ -v

# 预期结果：125 passed, 1 skipped
```

---

## JNB 数据接入详解

### 数据模式说明

| 模式 | DATA_MODE | 说明 |
|------|-----------|------|
| **JNB 模式** | `jnb` | 走 Tushare API，具备实时数据查询能力 |
| **普通小万** | `websearch` | 走网络搜索，纯 LLM 对话 |

在 `.env` 中设置 `DATA_MODE=jnb` 即可启用真实数据能力。

### 数据库表结构

| 表名 | 用途 | 字段 |
|------|------|------|
| `stock_basic` | 股票基本信息 | ts_code, name, industry, market... |
| `daily_kline` | 日线 K 线 | open, high, low, close, vol, pct_chg... |
| `indicator_cache` | 技术指标缓存 | KDJ, MACD, BBI, RSI, WR, 布林带... |
| `moneyflow` | 资金流向 | 大小单买卖金额, 净流入... |
| `financial_data` | 财务报表 | PE, PB, 营收, 净利润... |
| `trade_signals` | 交易信号记录 | signal_type, signal_score... |
| `sync_log` | 同步日志 | data_type, last_date, status... |

### 内置曼城阵容

项目已预置 10 只重点股真实数据（317 天 K 线 + 120 天技术指标）：

| 代码 | 名称 | 行业 |
|------|------|------|
| 600519.SH | 贵州茅台 | 白酒 |
| 000001.SZ | 平安银行 | 银行 |
| 000002.SZ | 万科A | 地产 |
| 300750.SZ | 宁德时代 | 新能源 |
| 601012.SH | 隆基绿能 | 光伏 |
| 002594.SZ | 比亚迪 | 汽车 |
| 600036.SH | 招商银行 | 银行 |
| 000858.SZ | 五粮液 | 白酒 |
| 601318.SH | 中国平安 | 保险 |
| 002415.SZ | 海康威视 | 科技 |

### 同步你自己的股票

```bash
# 同步单只
python -c "
from modules.data_sync import DataSyncer
syncer = DataSyncer()
syncer.sync_daily_kline('000001.SZ', start_date='20250101')
syncer.sync_indicator_cache('000001.SZ', days=120)
"

# 批量同步（需要先在 stock_basic 中有数据）
python -c "
from modules.data_sync import DataSyncer
syncer = DataSyncer()
syncer.sync_stock_basic()  # 先同步基本信息
syncer.sync_all_daily_kline(days=365)  # 批量同步K线
"
```

### 命令行工具

```bash
# 初始化数据库
python -m modules.data_sync init

# 同步所有股票（基本信息 + K线）
python -m modules.data_sync sync

# 同步指定股票
python -m modules.data_sync sync --ts_code 600519.SH --days 365

# 查看状态
python -m modules.data_sync status
```

---

## 效果示例

### 问：这只票我买了三天没涨，该割吗？

```
zettaranc  ❯ 三天没涨？兄弟，少妇战法的纪律摆在这儿——
             买入后第二天 9:33/9:37 不能拉起来，就得走了。

             你犹豫到现在，不是因为这票有多好，
             是因为你不舍得那 3 个点的浮亏。

             记住一句话：只输一根 K 线。
             你现在输了几根了？
```

### 问：现在全仓梭哈AI，Z哥怎么看？

```
zettaranc  ❯ 全仓梭哈？你这是少妇还是大爷？

             我的原则：三波不做。
             第三波你才进去的——你是去给前面两波人结账的。

             全仓一只票？2017 年我管产品的时候，单票仓位上限 10%。
             震荡市 5%，下跌市 2-3%。
             这不是保守，这是活到下一把桌的门票。

             记住：宁可错过，不做错。
             错过只是少赚，做错是本金没了。
```

### 问：我想辞职全职炒股

```
zettaranc  ❯ 辞职全职炒股？兄弟，我劝你慎重。

             你以为全职炒股是自由？
             是每天早上 9:15 坐在电脑前，
             周末还要研究政策、财报、行业数据。
             这叫自由？这叫给自己找了个 7×24 的老板。

             先兼职做，用闲钱做，把交易系统跑通至少一个牛熊周期。
             选择大于努力。但选择之前，先把基本功练扎实。
```

> 这不是套了个面具复读语录，而是用 zettaranc 的认知框架分析你的问题。

---

## 安装方式

### Claude Code Skill 安装

```bash
npx skills add lululu811/zettaranc-skill
```

然后在对话中输入：

```
> 用 Z 哥的视角帮我分析一下这个持仓
> zettaranc 会怎么看现在的行情？
> 切换到 Z 哥，帮我制定一个交易计划
```

---

## 蒸馏了什么

### 6 个核心心智模型

| 模型 | 一句话 |
|------|--------|
| **不确定性为底，纪律为桥** | 战略上找高概率方向，战术上用交易系统代替直觉 |
| **周期思维 / 时代主线** | 赚大钱本质是赚时代的钱，掐头去尾抓中间 |
| **短线交易系统** | 30+ 子战法/工作流：少妇战法、四块砖、B1B2B3、量比战法、麒麟会、防卖飞 V1.4、出货五式、五步工作流、滴滴战法、长安战法、平行重炮等 |
| **长线配置框架** | 稀缺性资产 + 曼城阵容 + ETF躺平 + 筹码思维 |
| **逆向操作 / 反共识** | 人人弃之时买入，人人知能赚钱时出货 |
| **双线趋势判断** | 白线在黄线上=主力在场，白线死叉黄线=无条件清仓 |

### 模块总览

| 模块 | 内容 |
|------|------|
| **trading-core** | 四层交易结构、少妇战法 SOP、四块砖、B1/B2/B3、量比战法、双枪、对称 VA |
| **indicators** | MACD 一票否决、筹码理论四大法则、麒麟会、三波理论、沙漏量化、量价分类 |
| **sell-discipline** | 防卖飞 V1.4、出货五式、滴滴战法、S1/S2/S3 逃顶体系 |
| **position-management** | 仓位铁律、资金量分级、三层防火墙、新曼城 4231、指数贡献策略 |
| **market-macro** | 周期思维、活跃市值、逆向操作、市场三阶段、四年周期、负反馈监控 |
| **stock-glossary** | 全品类个股黑话（60+ 代号）、双线战法术语、B2/B3 战法术语、宏观术语 |
| **trend-lines** | 知行趋势线（白线+黄线）、三道防线、五种玩法、碗的概念、牛绳理论 |
| **exit-strategies** | S1/S2/S3 逃顶体系、摸顶税、与防卖飞边界 |
| **key-candles** | 关键K理论、6 种趋势转换、衰竭信号、主力打明牌 |
| **advanced-patterns** | 长安战法、平行重炮、灾后重建、坑里起好货、四分之三阴量、异动地量、对称 VA |
| **portfolio-management** | 新曼城 4231、指数贡献、ETF 躺平、开超市、结构化仓位、ABC 建仓、3-2-2 阵型 |
| **trading-psychology** | 交易免疫系统、斗牛士心法、散户三大魔咒、少妇钝感力、屁胡哲学、空仓哲学 |

### 30 条决策启发式

按场景分组：短线纪律 9 条、中线管理 6 条、双线趋势 5 条、逃顶纪律 4 条、高级战法 6 条、长线与宏观 7 条。

### MACD 指标之王（2026年4月直播）

Z哥2026年4月22日长达4小时MACD专题直播，首次系统披露：

| 核心用法 | 说明 |
|---------|------|
| **零轴多空判断** | 白线上穿零轴=多头区间，下穿=空头区间 |
| **顶背离与底背离** | 股价创新高但白线未创新高=减仓信号 |
| **金叉空 / 死叉多** | 期货经典战法：眼看要金叉却拐头向下=做空信号 |

**MACD 一票否决权**：所有战法都要过 MACD 这一关。

### 仓位管理三层模型

| 层级 | 市场状态 | 策略 |
|------|---------|------|
| **第一层** | 牛市（强趋势） | 仓位 > 选股，Beta > Alpha，可以满仓不动 |
| **第二层** | 震荡市 | 精准 > 分散，5-8支票，单票≤20% |
| **第三层** | 收拳头期（市场高点） | 只卖不买，半仓甚至更低 |

### 个股多轮问诊

当询问个股时，Z 哥会像医生一样逐层诊断：
1. 第一轮：周期 + 状态 + 仓位占比
2. 第二轮：按场景分流（持仓诊断/买点确认/逃命判断/长线配置）
3. 全程：散户段位自动识别（6 种类型）

---

## 语料基础

| 来源 | 数量 | 时间 |
|------|------|------|
| 本地直播/付费课整理文章 | **~467 篇**（约 **200 万字**，全量解析） | 2025.6 - 2026.4 |
| ztalk B 站视频 transcript | 13 个 (~12.7 万字) | 2019 - 2021 |
| 股探报告系列（微博小号 @股探报告） | 9 篇 (~3.3 万字) | 2017.12 |
| 雪球专栏长文 | 1 篇 | 2014.12 |

调研提炼文件详见 `references/research/` 目录（11 份调研报告）。

---

## 仓库结构

```
zettaranc-skill/
├── SKILL.md                    # 可直接使用的 Skill 文件（核心路由器）
├── README.md                   # 本文件
├── CHANGELOG.md                # 更新日志
├── .env.example                # 环境变量模板
├── .env                        # 本地配置（不入库）
├── .gitignore                  # Git 忽略规则
├── requirements.txt            # Python 依赖
├── data/                       # 本地数据（不入库，SQLite/CSV/JSON）
│   └── stock_data.db           # 指标缓存数据库
├── modules/                    # Python 代码模块
│   ├── __init__.py
│   ├── database.py             # SQLite 数据库管理
│   ├── data_sync.py            # 数据同步器
│   ├── indicators.py           # 技术指标计算引擎（纯结构化输出）
│   ├── screener.py             # 选股器
│   ├── setup_wizard.py         # 初始化向导
│   ├── strategies.py           # 策略模板
│   ├── tushare_client.py       # Tushare API 封装
│   └── zettaranc_voice.py      # Z哥话术生成
├── knowledge/                  # 知识文档（交易体系/数据字典）
│   ├── trading-core.md
│   ├── sell-discipline.md
│   ├── position-management.md
│   ├── market-macro.md
│   ├── indicators.md
│   ├── trend-lines.md
│   ├── exit-strategies.md
│   ├── key-candles.md
│   ├── advanced-patterns.md
│   ├── portfolio-management.md
│   ├── trading-psychology.md
│   ├── stock-glossary.md
│   ├── data_dictionary.md
│   └── signal_dictionary.md
├── tests/                      # 单元测试
│   ├── conftest.py             # 测试基础设施
│   ├── test_database.py
│   ├── test_indicators.py
│   ├── test_screener.py
│   ├── test_strategies.py
│   └── test_setup_wizard.py
└── references/
    └── research/               # 11 份调研报告
```

**注**：出于版权和体积考虑，原始语料（视频 transcript、直播文章等）不包含在本仓库中。

---

## 本地开发

### 环境准备

```bash
pip install -r requirements.txt
```

### 常用命令

```bash
# 运行测试
python -m pytest tests/ -v

# 质量检查：验证 SKILL.md 是否符合质量标准
python scripts/quality_check.py SKILL.md

# 合并调研结果：生成来源统计和矛盾检测摘要
python scripts/merge_research.py .

# 批量下载 B 站 ztalk 合集音频
cd scripts && python batch_download_bilibili.py

# 批量转写音频为文本（需要 faster-whisper）
cd scripts && python batch_transcribe.py

# SRT/VTT 字幕清洗
python scripts/srt_to_transcript.py input.srt > output.txt
```

### TODO / 下一步

- [ ] **实时行情接入**：盘中等间隔刷新，支持盘中实时问诊
- [ ] **策略回测引擎**：基于指标缓存做历史回测，验证战法胜率
- [ ] **自动选股**：曼城评分体系全市场扫描，每日推荐候选
- [ ] **信号推送**：B1/B2/B3 买点触发时自动通知
- [ ] **财务报表深度解析**：营收、利润、现金流趋势分析
- [ ] **可视化看板**：K线 + 指标叠加的图表展示
- [ ] **多周期共振**：日线/周线/分钟线多周期信号对齐
- [ ] **增量语料接入**：持续蒸馏新的直播/课内容
- [ ] **Agent 自进化**：基于真实交易结果的反馈优化

---

## 版本规范

遵循语义化版本：MAJOR（心智模型重构 / 架构升级）.MINOR（语料扩展/新增模块）.PATCH（排版修复）。详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 免责声明

此 Skill 用于理解 zettaranc（万千）的思维模式，**不构成任何投资建议**。金融市场风险极高，任何基于历史信息的交易框架都可能失效。

- 外部可查记录显示 zettaranc 主要经历在私募基金/券商资管，最高规模约 11 亿
- 2017 年太平洋证券资管产品「柏悦量化1号」全年收益 -9.1%，大幅跑输沪深 300（+21.78%）
- 交易纪律的知行合一是最大瓶颈，Skill 可以提供框架但无法替你执行止损

**理解不等于模仿。投资有风险，入市需谨慎。**

---

## 仓库关联

| 平台 | 地址 | 说明 |
|------|------|------|
| **GitHub** | https://github.com/lululu811/zettaranc-skill.git | 主仓库，所有内容在此公开 |
| **Gitee** | https://gitee.com/chenleizzzz/zettaranc-knowledge.git | 镜像同步，Gitee 对 Skill 类项目有公开限制，部分内容可能受限 |

---

## 关注公众号

关注「知行 AI」公众号，获取更多 Z 哥直播精华解读 + AI 投资工具更新。

<div align="center">

![知行 AI 公众号二维码](assets/wechat-qr.png)

> 扫码关注，Z哥最新知识分享，不推荐个股

</div>

---

<div align="center">

*心中无牛熊，唯有纪律坚。*

<br>

MIT License

</div>
