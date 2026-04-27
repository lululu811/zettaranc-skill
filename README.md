<div align="center">

# zettaranc（万千）· 思维操作系统

> *「利润是市场给的，都是概率的事儿，谁也别吹牛逼。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![v2.0.0](https://img.shields.io/badge/version-2.0.0-orange)](CHANGELOG.md)

<br>

**前阳光私募冠军基金经理、B站百大UP主的投资思维框架。**<br>
基于 ~467 篇直播/付费课整理文章（约 200 万字，含 5 个语料源全量解析）+ 13 个 ztalk 视频 transcript（12.7 万字）+ 9 篇股探报告交易心理系列（3.3 万字）的深度蒸馏。

<br>

[看效果](#效果示例) · [安装](#安装) · [蒸馏了什么](#蒸馏了什么) · [更新日志](CHANGELOG.md)

</div>

---

## v2.0：Agent 能力升级

Z哥 Skill 已从纯 LLM 升级为具备**实时数据查询能力**的 Agent：

### 核心能力

| 能力 | 说明 |
|------|------|
| **实时行情** | 查股价、涨跌幅、量比、市值 |
| **K线数据** | 日线 OHLCV 历史走势 |
| **技术指标** | MACD/KDJ/RSI/布林带/砖形图等 |
| **资金流向** | 超大单/大单净流入 |
| **财务数据** | PE/PB、营收、利润 |
| **涨停数据** | 当日涨停股列表 |
| **指标缓存** | SQLite 存储每日指标快照，支持历史回测 |

### 安装配置

```bash
# 1. 克隆项目
git clone https://github.com/lululu811/zettaranc-skill.git
cd zettaranc-skill

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN

# 3. 安装依赖
pip install tushare python-dotenv pandas

# 4. 初始化数据库
python -m modules.database

# 5. 同步数据
python -m modules.data_sync sync --ts_code 000001.SZ
```

### 数据架构

```
modules/
├── tushare_client.py    # Tushare API 封装
├── database.py          # SQLite 数据库管理
├── data_sync.py         # 数据同步器
├── indicators.py        # 技术指标计算
└── zettaranc_voice.py   # Z哥话术生成
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

## 安装

### 方式一：Claude Code Skill 安装

```bash
npx skills add lululu811/zettaranc-skill
```

然后在对话中输入：

```
> 用 Z 哥的视角帮我分析一下这个持仓
> zettaranc 会怎么看现在的行情？
> 切换到 Z 哥，帮我制定一个交易计划
```

### 方式二：直接克隆使用

**GitHub（主仓库）**：

```bash
git clone https://github.com/lululu811/zettaranc-skill.git
```

**Gitee（自动同步镜像）**：

```bash
git clone https://gitee.com/chenleizzzz/zettaranc-knowledge.git
```

> **注意**：Gitee 为 GitHub 自动同步镜像，无需手动推送。Gitee 平台对 Skill 类项目有公开限制，因此 Skill 核心文件仅在 GitHub 公开。

克隆后将 `SKILL.md` 文件放入你的 AI 工具（Claude Code / Cursor / 其他支持 Skill 的编辑器）的 skill 目录中。

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

### 12 个能力模块 + 5 个数据模块

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
| **advanced-patterns** | 长安战法、平行重炮、灾后重建、坑里起好货、四分之三阴量、异动地量、对称 VA、B2/B3 完整体系 |
| **portfolio-management** | 新曼城 4231、指数贡献、ETF 躺平、开超市、结构化仓位、ABC 建仓、3-2-2 阵型 |
| **trading-psychology** | 交易免疫系统、斗牛士心法、散户三大魔咒、少妇钝感力、屁胡哲学、空仓哲学 |

### 30 条决策启发式

按场景分组：短线纪律 9 条、中线管理 6 条、双线趋势 5 条、逃顶纪律 4 条、高级战法 6 条、长线与宏观 7 条。

### 最新：MACD 指标之王（2026年4月直播）

Z哥2026年4月22日长达4小时MACD专题直播，首次系统披露：

| 核心用法 | 说明 |
|---------|------|
| **零轴多空判断** | 白线上穿零轴=多头区间，下穿=空头区间 |
| **顶背离与底背离** | 股价创新高但白线未创新高=减仓信号 |
| **金叉空 / 死叉多** | 期货经典战法：眼看要金叉却拐头向下=做空信号 |

**MACD 一票否决权**：所有战法都要过 MACD 这一关。

### 仓位管理三层模型

根据市场周期调整仓位策略：

| 层级 | 市场状态 | 策略 |
|------|---------|------|
| **第一层** | 牛市（强趋势） | 仓位 > 选股，Beta > Alpha，可以满仓不动 |
| **第二层** | 震荡市 | 精准 > 分散，5-8支票，单票≤20% |
| **第三层** | 收拳头期（市场高点） | 只卖不买，半仓甚至更低 |

### 23 条决策启发式

按场景分组：短线纪律 9 条、中线管理 6 条、长线与宏观 8 条。

### 个股多轮问诊

当询问个股时，Z 哥会像医生一样逐层诊断：
1. 第一轮：周期 + 状态 + 仓位占比
2. 第二轮：按场景分流（持仓诊断/买点确认/逃命判断/长线配置）
3. 全程：散户段位自动识别（6 种类型）

详见 [CHANGELOG.md](CHANGELOG.md) 的 v1.5.0 完整变更记录。

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
├── TODO.md                     # 待办清单
├── CONTRIBUTING.md             # 贡献指南
├── LICENSE                     # MIT 许可证
├── .gitignore
├── .env.example              # 环境变量模板
├── modules/                    # 能力模块
│   ├── trading-core.md         # 交易核心引擎（四层结构、少妇战法、B1/B2/B3）
│   ├── indicators.md           # 指标工具箱（MACD、筹码、麒麟会、沙漏）
│   ├── sell-discipline.md      # 卖出纪律（防卖飞、出货五式、滴滴、S1/S2/S3）
│   ├── position-management.md  # 仓位管理（铁律、资金量分级、三层防火墙）
│   ├── market-macro.md         # 宏观判断（周期、活跃市值、逆向操作、四年周期）
│   ├── stock-glossary.md       # 个股黑话词典（60+ 代号）
│   ├── trend-lines.md          # 知行趋势线（双线战法、白线黄线、牛绳理论）
│   ├── exit-strategies.md      # S1/S2/S3 逃顶体系
│   ├── key-candles.md          # 关键K理论
│   ├── advanced-patterns.md    # 高级战法合集（长安、重炮、祖冲之...）
│   ├── portfolio-management.md # 组合配置体系（新曼城4231、ETF躺平）
│   └── trading-psychology.md   # 交易心理（免疫系统、斗牛士、屁胡哲学）
└── references/
    └── research/               # 11 份调研报告
        ├── 01-writings.md      # 文字作品蒸馏
        ├── 02-conversations.md # 对话/直播蒸馏
        ├── 03-expression-dna.md# 表达 DNA
        ├── 04-external-views.md# 外部视角
        ├── 05-decisions.md     # 决策记录
        ├── 06-timeline.md      # 时间线
        ├── 07-xiaocainiao-new.md   # 知行小菜鸟 118 文件新增
        ├── 08-dafuweng-new.md      # 大富翁小菜鸟 185 文件新增
        ├── 09-tangoo-new.md        # TANGOO 62 文件新增
        ├── 10-fupan-new.md         # 复盘专用z 49 文件新增
        └── 11-kedebiao-new.md      # 知行课代表 53 文件新增
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

### 版本规范

遵循语义化版本：MAJOR（心智模型重构）.MINOR（语料扩展/新增模块）.PATCH（排版修复）。详见 [CHANGELOG.md](CHANGELOG.md)。

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
