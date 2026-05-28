<!-- From: /Users/chenlei/005_skill/skills/zettaranc-skill/AGENTS.md -->
# zettaranc-skill · Agent 指南

> 本文件面向 AI 编程 Agent。阅读前请确认你已通读本文件，再操作代码或文档。

---

## 项目概述

本项目是一个**AI Skill（思维框架蒸馏包）+ 真实数据量化工具**的混合体。

核心目标：将 B 站 UP 主 / 前私募基金经理 zettaranc（万千）的投资思维框架、决策启发式和表达 DNA，封装为可供 Claude Code / Cursor 等 AI 工具调用的 Skill 文件（`SKILL.md`），同时提供基于真实 Tushare 行情数据的 Python 数据层支撑。

- **核心交付物**：`SKILL.md`（可直接被 AI 工具加载的角色扮演协议）
- **数据层**：Python 模块 + SQLite 数据库 + Tushare API（JNB 模式）
- **语料基础**：约 467 篇直播/付费课整理文章（~200 万字）+ 13 个 ztalk 视频 transcript（~12.7 万字）+ 9 篇交易心理系列（~3.3 万字）+ 15 篇 2026.4-5 月新增文章
- **许可证**：MIT
- **版本**：当前 v2.4.0，采用语义化版本（见下方）

### 双模式架构

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| **JNB 模式** | `DATA_MODE=jnb` | 接入 Tushare 真实行情，具备实时数据查询、技术指标计算、战法识别能力 |
| **普通小万** | `DATA_MODE=websearch` | 纯 LLM 对话，不走任何外部数据接口 |

架构分层：

```
Python 数据层（modules/）              LLM 角色层（SKILL.md）
├─ tushare_client.py     API 封装         ├─ 角色扮演规则
├─ database.py           SQLite 管理       ├─ Agentic Protocol
├─ data_sync.py          数据同步          ├─ 6 个核心心智模型
├─ indicators/           60+ 技术指标      ├─ 30 条决策启发式
│   ├─ core.py           基础/数学/核心指标 ├─ 表达 DNA
│   ├─ price_patterns.py 价格形态识别      └─ 诚实边界
│   ├─ volume_patterns.py 量价信号
│   └─ data_layer.py     数据接入/缓存/可视化
├─ screener.py           选股评分体系
├─ strategies.py         30+ 战法识别
├─ backtest.py           策略组合回测
├─ portfolio_diagnosis.py 持股检查
├─ watchlist.py          自选股观察池
├─ cli.py                命令行工具
├─ trade_parser.py       口语化输入解析
├─ trade_manager.py      交易记录 CRUD
├─ trade_reviewer.py     数据准备层（给 LLM 用）
├─ setup_wizard.py       初始化配置向导
└─ zettaranc_voice.py    语料库 / LLM 提示词
```

**关键设计原则**：Python 层只负责**数据准备**，所有点评、分析话术由 LLM 用 Z哥角色生成，避免"AI味"。

---

## 技术栈与运行时架构

### 技术栈

| 层级 | 技术 |
|------|------|
| 数据管道 | Python 3（标准库 + `sqlite3`、`pathlib`、`dataclasses`、`enum`） |
| 外部数据 | `tushare`（Pro API，支持中转 URL）、`pandas`、`requests` |
| 环境配置 | `python-dotenv`（`.env` 文件） |
| 数据库 | SQLite（本地文件，8 张表） |
| 测试框架 | `pytest` |
| 视频下载 | `yt-dlp`（语料采集） |
| 语音转写 | `faster-whisper`（语料采集） |
| 文档格式 | Markdown（全部文档与语料） |
| 版本控制 | Git |

### 配置说明

**`requirements.txt`** 存在，管理 Python 依赖：

```
yt-dlp>=2024.1.0
faster-whisper>=1.0.0
tushare>=1.4.0
python-dotenv>=1.0.0
```

> `pandas` 亦为项目所用，通常随 `tushare` 一并安装。

**`.env.example`** 环境变量模板：

```ini
DATA_MODE=jnb
TUSHARE_TOKEN=你的56位token
TUSHARE_API_URL=          # 可选，中转 API 地址
TUSHARE_VERIFY_TOKEN_URL= # 可选，实时行情验证地址
DATA_DIR=data
DB_PATH=data/stock_data.db
```

> 注意：v2.1.1 之后，所有 Tushare URL 均从环境变量读取，代码中不再硬编码任何内部域名。

**没有** `pyproject.toml`、`setup.py`、`Makefile` 或 `package.json`。所有脚本均为独立可执行文件。

---

## 项目结构与模块划分

```
zettaranc-skill/
├── SKILL.md                    # 核心 Skill 文件（Agent 角色扮演协议）
├── README.md                   # 面向人类用户的项目介绍
├── CHANGELOG.md                # 版本变更日志（Keep a Changelog 格式）
├── CONTRIBUTING.md             # 贡献指南（含风格验证清单）
├── AGENTS.md                   # 本文件
├── TODO.md                     # 项目待办与路线图
├── LICENSE                     # MIT
├── .env / .env.example         # 本地配置（.env 不入库）
├── .gitignore                  # Git 忽略规则
├── .editorconfig               # 编辑器格式统一配置
├── requirements.txt            # Python 依赖
├── data/                       # 本地 SQLite 数据库（不入库）
│   ├── stock_data.db           # 主数据库（8 张表 + 索引）
│   └── db_test.db              # 测试/全量同步数据库
├── modules/                    # Python 代码模块（~6800 行）
│   ├── __init__.py             # 包导出 + get_data_mode()
│   ├── database.py             # SQLite 数据库管理：8 张表、事务上下文、CRUD
│   ├── data_sync.py            # Tushare 数据同步器：增量/全量、限流 120次/分
│   ├── indicators/             # 技术指标计算引擎：60+ 指标（4 子模块）
│   │   ├── core.py             # 基础类型 + 数学工具 + 核心指标
│   │   ├── price_patterns.py   # 价格形态（双线/单针/砖型图/B1/B2/B3/图形识别）
│   │   ├── volume_patterns.py  # 量价信号（卖出评分/交易信号/量比异动）
│   │   └── data_layer.py       # 数据接入（get_kline_data/analyze_stock/缓存层/可视化）
│   ├── screener.py             # 选股与择时：曼城评分、B1评分、趋势/量价/风险评分、每日五步工作流
│   ├── strategies.py           # 战法识别引擎：B1/B2/B3/SB1、长安战法、四分之三阴量、娜娜图形、异动地量…
│   ├── setup_wizard.py         # 初始化向导：JNB/websearch 双模式切换、API 连通性测试
│   ├── tushare_client.py       # Tushare API 封装：限流、错误处理、实时行情
│   ├── zettaranc_voice.py      # Z哥语料库 V3.0 + LLM 提示词模板（TRADE_REVIEW_PROMPT / STOCK_ANALYSIS_PROMPT）
│   ├── trade_parser.py         # 随堂测试解析器：口语化/JSON/CSV 多格式输入、正则提取
│   ├── trade_manager.py        # 交易记录 CRUD、持仓计算、盈亏统计
│   └── trade_reviewer.py       # 交割单数据准备层：ReviewContext → LLM 提示词
├── knowledge/                  # 知识文档（交易体系/数据字典/信号字典）
│   ├── trading-core.md         # 四层交易结构、少妇战法 SOP、B1/B2/B3、量比战法
│   ├── indicators.md           # MACD 一票否决、筹码理论、麒麟会、三波理论
│   ├── sell-discipline.md      # 防卖飞 V1.4、出货五式、S1/S2/S3 逃顶
│   ├── position-management.md  # 仓位铁律、三层防火墙
│   ├── market-macro.md         # 周期思维、逆向操作、四年周期
│   ├── portfolio-management.md # 新曼城 4231、ETF 躺平、ABC 建仓
│   ├── trading-psychology.md   # 交易免疫系统、斗牛士心法、散户魔咒
│   ├── stock-glossary.md       # 60+ 个股黑话/代号
│   ├── trend-lines.md          # 双线战法、三道防线、牛绳理论
│   ├── exit-strategies.md      # S1/S2/S3 逃顶、摸顶税
│   ├── key-candles.md          # 关键 K 理论、6 种趋势转换
│   ├── advanced-patterns.md    # 长安战法、平行重炮、对称 VA
│   ├── data_dictionary.md      # 输入数据字典（DailyBar/MoneyFlow/Financial）
│   └── signal_dictionary.md    # 输出信号字典
├── tests/                      # 单元测试（pytest，~125+ 用例）
│   ├── conftest.py             # 测试基础设施：临时数据库 fixture、K线工厂函数
│   ├── test_database.py        # 数据库初始化、连接、事务、表增删
│   ├── test_indicators.py      # 56+ 指标计算测试（MA/EMA/KDJ/MACD/RSI/WR/布林带/砖形图/DMI…）
│   ├── test_strategies.py      # 战法识别测试、数据库集成
│   ├── test_screener.py        # 选股评分、趋势/量价/风险评分
│   ├── test_setup_wizard.py    # 环境变量检测、数据模式切换
│   └── test_exam_rules.py      # 交易战法考试规则验证（B1/砖型图/单针下30）
├── scripts/                    # 工具脚本
│   ├── batch_download_bilibili.py   # 批量下载 B 站 ztalk 音频
│   ├── batch_transcribe.py          # 批量音频转写（faster-whisper）
│   ├── srt_to_transcript.py         # 字幕清洗为纯文本
│   ├── download_subtitles.sh        # YouTube 字幕下载
│   ├── fetch_tushare_data.py        # Tushare Pro 高权限数据抓取（15000积分接口）
│   ├── sync_db_test.py              # db_test 全量数据库同步（股票+K线+指标）
│   ├── merge_research.py            # 合并调研结果、生成统计摘要
│   └── quality_check.py             # SKILL.md 质量自动检查（8 项维度）
└── references/
    └── research/               # 11 份调研提炼文件（蒸馏过程的中间产物）
        ├── 01-writings.md      # 著作与系统思考
        ├── 02-conversations.md # 长对话与即兴思考
        ├── 03-expression-dna.md# 碎片表达与风格 DNA
        ├── 04-external-views.md# 他者视角与批评
        ├── 05-decisions.md     # 决策记录与行动
        ├── 06-timeline.md      # 人物时间线
        └── 07-11-*.md          # 5 个新增语料源调研
```

**注意**：`references/sources/` 下的原始语料因版权和体积原因**不提交到 Git**。仓库中只保留调研提炼文件和 `SKILL.md`。

---

## 数据库架构

SQLite 数据库包含 8 张核心表（`modules/database.py` 中定义）：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `daily_kline` | 日线 K 线 | open/high/low/close/vol/pct_chg/is_limit_up |
| `indicator_cache` | 技术指标缓存（每日快照） | KDJ/MACD/BBI/MA/RSI/WR/布林带/双线/砖形图/DMI/量比/信号 |
| `moneyflow` | 资金流向 | 大小单买卖金额、净流入 |
| `financial_data` | 财务报表 | PE/PB/营收/净利润/资产负债 |
| `stock_basic` | 股票基本信息 | ts_code/name/industry/market |
| `trade_signals` | 交易信号记录 | signal_type/signal_score/signal_price |
| `trade_records` | 随堂测试/交易记录 | action/price/quantity/reason/signal_type/zg_review |
| `sync_log` | 数据同步日志 | data_type/last_date/status |

每张表均建立合适的复合索引（ts_code + trade_date DESC）。

---

## 构建、测试与常用命令

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

```bash
# 全部测试（预期：213 passed, 1 skipped）
python -m pytest tests/ -v

# 单文件测试
python -m pytest tests/test_indicators.py -v
```

### 初始化数据库与同步数据

```bash
# 初始化数据库（创建 8 张表）
python -m modules.database

# 或统一入口
python -m modules.data_sync init

# 同步股票基本信息（全量 5510 只）
python -m modules.data_sync sync

# 同步单只股票 K 线
python -m modules.data_sync sync --ts_code 000001.SZ --days 365

# 查看同步状态
python -m modules.data_sync status
```

### 高权限数据抓取

```bash
# 查看所有可用命令
python scripts/fetch_tushare_data.py --help

# 抓取并保存到数据库
python scripts/fetch_tushare_data.py stock_basic --save-db
python scripts/fetch_tushare_data.py daily 000001.SZ --start 20260101 --end 20260501 --save-db
python scripts/fetch_tushare_data.py moneyflow 000001.SZ --date 20260509 --save-db
python scripts/fetch_tushare_data.py limit_list --date 20260509 --save-db
python scripts/fetch_tushare_data.py all --save-db
```

### db_test 全量同步工具

```bash
python scripts/sync_db_test.py init     # 初始化 db_test.db
python scripts/sync_db_test.py full     # 全量同步（股票+K线+指标）
python scripts/sync_db_test.py status   # 查看状态
```

### 质量检查

```bash
# 验证 SKILL.md 是否符合 8 项质量标准
python scripts/quality_check.py SKILL.md

# 合并调研结果
python scripts/merge_research.py .
```

### 语料采集脚本

| 脚本 | 用法 | 说明 |
|------|------|------|
| `batch_download_bilibili.py` | `cd scripts && python batch_download_bilibili.py` | 下载 B 站 ztalk 音频 |
| `batch_transcribe.py` | `cd scripts && python batch_transcribe.py` | 音频转写文本 |
| `srt_to_transcript.py` | `python srt_to_transcript.py input.srt` | 字幕清洗 |

**路径约定**：`batch_download_bilibili.py` 和 `batch_transcribe.py` 使用硬编码的相对路径 `../references/sources/transcripts/`，**必须在 `scripts/` 目录内执行**。

---

## 代码风格与开发规范

### 通用规范

- 所有脚本文件头包含 `#!/usr/bin/env python3` 或 `#!/bin/bash`
- 使用**中文**编写文档字符串和注释
- 使用标准库为主，避免引入不必要的第三方依赖
- 正则表达式用于文本解析和统计，保持简单可维护
- 每个模块文件末尾通常包含 `if __name__ == "__main__":` 命令行入口

### 编辑器配置

项目根目录存在 `.editorconfig`，统一格式：

| 文件类型 | 缩进 | 大小 |
|---------|------|------|
| `*.py` | space | 4 |
| `*.sh` | space | 4 |
| `*.md` | space | 2（且不裁剪行尾空格） |
| `*.json` | space | 2 |
| 全部 | UTF-8 | LF 换行 |

### Python 模块规范

- **数据库路径**：统一从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取，支持相对路径和绝对路径
- **环境变量加载**：每个需要 `.env` 的模块顶部统一使用 `load_dotenv(Path(__file__).parent.parent / ".env")`
- **限流控制**：所有 Tushare API 调用必须带 `_rate_limit()`，控制 120 次/分钟
- **事务管理**：数据库操作统一使用 `get_connection()` 上下文管理器（自动 commit/rollback）
- **错误处理**：API 调用用 try/except 包裹，记录 error log，返回空 DataFrame/None 而非抛异常中断
- **Import 兼容**：模块间导入同时支持包内相对导入和直接脚本运行（`try: from .xxx import ... except ImportError: from xxx import ...`）

### 版本规则

采用语义化版本，但含义针对本项目定制：

| 位 | 含义 | 示例 |
|----|------|------|
| MAJOR | 心智模型级别的重构 | v1.3.0：将 6 个心智模型重组为 5 个 |
| MINOR | 新增战术/启发式/语料/模块 | v2.0.0：新增 Tushare 数据层和 8 个 Python 模块 |
| PATCH | 排版修正、安全修复、数字更新 | v2.1.1：移除 URL 硬编码 |

---

## 测试策略

### 测试架构

- **框架**：pytest
- **Fixture**：`conftest.py` 提供 `mock_env_for_tests`（自动 mock 环境变量到临时目录）、`temp_db`（初始化好的临时数据库）、`db_conn`（数据库连接）
- **数据工厂**：`make_kline_row()`、`make_daily_data()`、`generate_uptrend_klines()`、`generate_downtrend_klines()`、`generate_b1_scenario()` 等用于生成测试数据
- **数据库隔离**：所有测试使用临时 SQLite 文件，互不干扰

### 测试覆盖范围

| 测试文件 | 覆盖范围 | 用例数 |
|---------|---------|--------|
| `test_database.py` | 路径解析、连接上下文、事务回滚、表初始化、幂等性 | ~15 |
| `test_indicators.py` | MA/EMA/SMA/KDJ/MACD/背离/BBI/RSI/WR/布林带/量比/双线/单针/异动/双枪/DMI/砖形图/量价/B1B2/四块砖/呼吸结构/SB1/B3/防卖飞/信号 | ~56 |
| `test_strategies.py` | B1/B2/B3/SB1/长安/四分之三阴量/娜娜/异动地量/全量检测 | ~15 |
| `test_screener.py` | 评分模型、趋势/量价/风险评分、完美图形 | ~15 |
| `test_setup_wizard.py` | 环境检测、文件写入、模式切换 | ~8 |
| `test_exam_rules.py` | B1 规则、砖型图规则、单针规则、评分标准、核心原则 | ~25 |
| `test_trade_manager.py` | 交易记录 CRUD、持仓计算、盈亏统计 | ~5 |
| `test_portfolio_diagnosis.py` | 持股检查、状态扫描、防卖飞、出货信号、战法匹配 | ~10 |
| `test_watchlist.py` | 观察池增删改查、批量扫描、按标签筛选 | ~4 |

### 运行预期

```bash
$ python -m pytest tests/ -v
# 预期：213 passed, 1 skipped
```

---

## 文件修改优先级

1. **`SKILL.md`** —— 直接影响 Skill 表现，任何改动都需语料支撑
2. **`modules/*.py`** —— 数据层代码改动需同步更新测试
3. **`knowledge/*.md`** —— 知识文档，补充新语料或修正旧发现时更新
4. **`references/research/*.md`** —— 调研档案，新增语料源时更新
5. **`README.md` / `CHANGELOG.md`** —— 项目对外文档，版本发布时同步更新
6. **`scripts/`** —— 工具脚本，仅在数据管道或检查逻辑需要改进时修改

---

## 内容修改原则

1. **最小改动原则**：只改确实不准确的部分
2. **有依据**：任何改动都需要语料支撑，不能凭印象。优先来源：
   - zettaranc 本人直接产出（视频、直播、付费课、雪球专栏）
   - 权威媒体报道（澎湃新闻等）
   - 证券业协会公示资料
   - **不应作为主要依据**：知乎回答、非本人微信公众号、股吧/雪球帖子（除本人账号外）
3. **保持角色一致性**：修改后的回答仍需符合 zettaranc 的表达 DNA

### 风格验证清单（来自 CONTRIBUTING.md）

修改 SKILL.md 后，用以下问题自检：

- [ ] 是否用「我」而非「Z 哥认为...」？
- [ ] 是否包含职业背书开场？
- [ ] 是否分 1/2/3/4 点拆解？
- [ ] 是否用了具体数字或案例？
- [ ] 是否以金句或反问收尾？
- [ ] 是否避免跳出角色的表述？
- [ ] 交易建议是否包含具体的进场/止损/止盈规则？

---

## 安全与合规考虑

1. **免责声明**：`SKILL.md` 和 `README.md` 均包含明确免责声明——**不构成任何投资建议**。金融市场风险极高，任何基于历史信息的交易框架都可能失效。
2. **版权边界**：原始语料（视频 transcript、直播文章等）不提交到仓库。仓库中只保留粉丝整理的 Markdown 提炼文件和转写文本。
3. **敏感信息**：Tushare Token 和 API URL 通过 `.env` 文件管理，**绝不硬编码**。v2.1.1 已彻底移除所有内部域名硬编码。
4. **信息偏差标注**：`SKILL.md` 的「诚实边界」一节明确标注了公开表达与真实想法的差异（如「公募基金经理」title 争议、2017 年产品跑输沪深 300 等）。
5. **语料截止期**：信息截止到调研时间（2026-04-18 及后续更新），金融市场瞬息万变，历史框架可能因政策/技术/国际形势突变而失效。

---

## 常见任务速查

| 任务 | 操作 |
|------|------|
| 更新心智模型或交易规则 | 先查 `references/research/01-writings.md` 和 `05-decisions.md` → 修改 `SKILL.md` → 运行 `quality_check.py` |
| 补充新语料 | 将新文章放入 `references/sources/articles/` → 更新对应 `references/research/*.md` → **不要**将原始语料加入 git |
| 新增 B 站视频 transcript | `cd scripts && python batch_download_bilibili.py && python batch_transcribe.py` |
| 发布新版本 | 更新 `SKILL.md` → 更新 `CHANGELOG.md` → 更新 `README.md` 中的版本 badge → 打 git tag |
| 验证风格一致性 | 对照 `CONTRIBUTING.md` 中的「风格验证清单」逐项检查 |
| 修复数据层 bug | 修改 `modules/*.py` → 补充/更新 `tests/test_*.py` → `pytest tests/ -v` |
| 接入新 Tushare 接口 | 修改 `scripts/fetch_tushare_data.py` 或 `modules/tushare_client.py` → 在 `modules/database.py` 中确认表结构支持 → 补充保存逻辑 |
| 初始化全新环境 | `cp .env.example .env` → 填入 Token → `python -m modules.database` → `python -m modules.data_sync sync` → `pytest tests/ -v` |

---

## 外部依赖安装

若需要运行数据管道脚本，手动安装以下工具：

```bash
# Python 依赖
pip install -r requirements.txt

# yt-dlp 可能需要 ffmpeg（处理音频）
# macOS: brew install ffmpeg
# Linux: sudo apt install ffmpeg
```

**注意**：`faster-whisper` 的 base 模型首次运行时会自动下载到本地缓存（约 150MB）。

---

> 如有疑问，参考 `CONTRIBUTING.md` 或直接在 Discussions 中交流。
>
> Love and Share 🖤
