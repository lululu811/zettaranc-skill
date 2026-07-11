# zettaranc-skill · Agent 指南

> 本文件面向 AI 编程 Agent。阅读前请确认你已通读本文件，再操作代码或文档。

---

## 项目概述

本项目是一个 **AI Skill（思维框架蒸馏包）+ 真实数据量化工具** 的混合体。

核心目标：将 B 站 UP 主 / 前阳光私募冠军基金经理 zettaranc（万千）的投资思维框架、决策启发式和表达 DNA，封装为可供 Claude Code / Cursor 等 AI 工具调用的 Skill 文件（`SKILL.md`），同时提供基于真实 Tushare 行情数据的 Python 数据层支撑。

- **核心交付物**：`SKILL.md`（可直接被 AI 工具加载的角色扮演协议）
- **数据层**：Python 模块 + SQLite 数据库 + Tushare API（JNB 模式）
- **Web 看板**：`api/`（FastAPI 后端）+ `frontend/`（React + Vite + Tailwind 前端），可选
- **语料基础**：约 467 篇直播/付费课整理文章（~200 万字）+ 13 个 ztalk 视频 transcript（~12.7 万字）+ 9 篇交易心理系列（~3.3 万字）+ 后续新增文章
- **许可证**：MIT
- **版本**：`docs/CHANGELOG.md` 与 `pyproject.toml` 当前版本为 **v3.10.2**。

### 双模式架构

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| **JNB 模式** | `DATA_MODE=jnb` | 接入 Tushare 真实行情，具备实时数据查询、技术指标计算、战法识别能力 |
| **普通小万** | `DATA_MODE=websearch` | 纯 LLM 对话，不走任何外部数据接口 |

### 架构分层

```
Python 数据层（modules/）              LLM 角色层（SKILL.md）
├─ datasource.py         统一数据源协议      ├─ 角色扮演规则
├─ tushare_client.py     Tushare API 封装    ├─ Agentic Protocol（编排/分流逻辑）
├─ bridge_client.py      tushare-data-bridge ├─ 9 个核心心智模型
│                         HTTP 客户端        ├─ 决策启发式
├─ indevs_client.py      indevs 数据客户端   ├─ 表达 DNA
├─ database.py           SQLite 管理         └─ 诚实边界
├─ data_sync.py          兼容 shim
├─ data_sync/            数据同步子包
│   ├─ rate_limiter.py     120次/分限流器
│   ├─ indicator_cache.py  指标缓存写入
│   ├─ fetcher.py          Tushare/Bridge 抓取
│   ├─ syncer.py           增量/全量同步器
│   ├─ cli.py              子命令入口
│   └─ __main__.py         python -m 入口
├─ indicators/           60+ 技术指标
│   ├─ core.py           基础/数学/核心指标
│   ├─ price_patterns/   价格形态识别子包
│   │   ├─ base.py          形态识别基类
│   │   ├─ brick.py         砖形图
│   │   ├─ bull_rope.py     牛绳
│   │   ├─ complex_patterns 复杂形态（蜈蚣图等）
│   │   ├─ key_candles.py   关键 K
│   │   ├─ sandglass.py     沙漏
│   │   └─ screener_helper  选股辅助
│   ├─ volume_patterns.py 量价信号
│   ├─ wave_theory.py    三波理论识别
│   ├─ kirin_detector.py 麒麟会四阶段
│   └─ data_layer.py     数据接入/缓存/可视化
├─ screener.py           兼容 shim
├─ screener/             选股评分子包（含蜈蚣图/沙漏/牛绳过滤）
│   ├─ models.py           数据模型
│   ├─ data.py             数据接入
│   ├─ criteria.py         筛选条件（曼城/B1/趋势/量价/风险）
│   ├─ scoring.py          多维度评分
│   ├─ engine.py           引擎主入口
│   ├─ market.py           市场环境权重
│   ├─ format.py           输出格式化
│   ├─ workflow.py         选股工作流
│   └─ cli.py              子命令入口
├─ simulator/            少女/少妇模拟器（v3.4-v3.6）
│   ├─ simulator.py          主入口
│   ├─ market_context.py     市场环境判定
│   ├─ signal_filter.py      信号过滤（simple / resonance 双模式）
│   ├─ position_sizer.py     ATR 动态仓位
│   ├─ execution_engine.py   撮合执行引擎
│   ├─ execution_constraints A 股约束（T+1/涨跌停/ST/停牌）
│   ├─ cost_model.py         真实成本模型
│   ├─ slippage_model.py     动态滑点
│   ├─ exit_manager.py       止盈止损管理
│   ├─ metrics.py            绩效指标
│   ├─ strategy_adapter.py   战法信号标准化
│   ├─ resonance_scorer.py   多战法共振评分
│   ├─ environment_weights   环境权重动态调整
│   ├─ param_space.py        参数空间与网格生成
│   ├─ walk_forward.py       滚动窗口 OOS 验证
│   ├─ optimizer_report.py   walk-forward 报告输出
│   └─ narrator.py           Z 哥风格回测叙事
├─ strategies/           30+ 战法识别（5 子模块）
│   ├─ core.py               核心战法/B1/B2/B3/长安等
│   ├─ base_strategies.py    基础战法
│   ├─ compound_strategies.py 复合战法
│   ├─ sell_signals.py       卖出信号
│   └─ vectorized.py         向量化识别
├─ statistics/           统计检验框架
│   ├─ __init__.py           核心统计检验
│   ├─ criteria.py           达标规则引擎
│   ├─ sensitivity.py        参数敏感性分析
│   └─ ensemble.py           策略集成模块
├─ core/                 公共模块（v3.8+）
│   ├─ metrics.py            通用绩效指标
│   ├─ walk_forward.py       通用滚动窗口验证
│   ├─ market_context.py     通用市场环境
│   └─ net.py                网络相关公共函数（disable_proxy()）
├─ verify/               少妇战法 v1.0 验收工程化（v3.7.0+）
│   ├─ pipeline.py           统一回测管线
│   ├─ gates.py              五项硬指标自动判定
│   ├─ walk_forward.py       真切片 WF 验证
│   ├─ scorer.py             达尔文友好评分器
│   ├─ registry_writer.py    寻优结果写回 param_registry
│   ├─ report.py             JSON + Markdown 报告
│   ├─ portfolio_engine.py   组合回测引擎
│   ├─ portfolio_walk_forward.py 组合 WF 验证
│   └─ cli.py                zt verify v1.0 CLI
├─ backtest/             回测子包（v3.8+）
│   ├─ single.py             单策略回测
│   └─ portfolio.py          组合回测
├─ backtest_six_step.py  少妇战法六步闭环
├─ loop_engine.py        六步闭环状态机
├─ loop_engine_enhanced.py 增强版多策略共振闭环
├─ portfolio_diagnosis.py 持股检查
├─ watchlist.py          自选股观察池
├─ cli.py / cli_commands.py 命令行统一入口
├─ trade_parser.py       口语化输入解析
├─ trade_manager.py      交易记录 CRUD
├─ trade_reviewer.py     交割单数据准备层
├─ intent_router.py      意图路由
├─ intent_chat.py        LLM 聊天接口
├─ knowledge_retriever.py RAG 知识检索
├─ llm_providers.py      LLM 提供者抽象
├─ setup_wizard.py       初始化配置向导
├─ report.py             Z 哥量化评估报告
├─ commentary_service.py 点评服务
├─ review_generator.py   复盘生成
├─ monitor.py / notifier.py 自选股监控与推送
├─ tracking_manager.py / tracking_syncer.py 自我改进跟踪池
├─ improvement_logger.py / harness_updater.py 改进日志与 Harness 更新
├─ dynamic_config.py     动态配置管理
├─ market_regime.py      市场状态机
├─ position_manager.py   仓位管理
├─ industry_filter.py    行业过滤
└─ self_optimizer/       Darwin 自优化管线
    ├─ param_registry.py 参数注册表
    ├─ mutator.py        参数变异
    ├─ scorer.py / backtest_scorer.py 评分器
    ├─ llm_judge.py      LLM 裁判
    ├─ reflex_blacklist.py 反射黑名单
    └─ phase1_baseline.py / phase2_hillclimb.py / phase3_report.py 三阶段管线

knowledge/（知识文件，33 篇交易体系）
├─ trading-core.md       短线交易核心
├─ indicators.md         技术指标
├─ sell-discipline.md    卖出纪律
├─ position-management.md 仓位管理
├─ market-macro.md       宏观判断
├─ stock-glossary.md     个股黑话
├─ trend-lines.md        趋势线
├─ exit-strategies.md    逃顶体系
├─ key-candles.md        关键K
├─ advanced-patterns.md  高级战法
├─ portfolio-management.md 组合配置
├─ trading-psychology.md 交易心理
├─ breathing-theory.md   呼吸理论
├─ three-best-principles.md 三最原则
├─ iron-butterfly.md     铁蝴蝶识别
├─ four-rhythms.md       四大节奏
├─ six-tracks-2026.md    2026 赛道
├─ life-decision.md      人生决策框架
├─ life-decision-research.md 人生决策调研
├─ career-development.md 职业发展框架
├─ business-judgment.md  创业/商业判断框架
├─ business-judgment-research.md 商业判断调研
├─ heuristics.md         决策启发式
├─ framework-extraction.md 框架萃取方法
├─ workflow.md           回答工作流 SOP
├─ harness.md            Harness 六大部分
├─ improvement-system.md 改进系统闭环
├─ data_dictionary.md    数据字典
├─ signal_dictionary.md  信号字典
└─ ... 其他研究与专题文件

rules/
├─ intent_rules.yaml     意图匹配规则
├─ career_prompt.md      职业决策框架
└─ life_prompt.md        人生决策框架

references/research/（11 份调研提炼文件）
├─ 01-writings.md
├─ 02-conversations.md
├─ 03-expression-dna.md
├─ 04-external-views.md
├─ 05-decisions.md
├─ 06-timeline.md
└─ 07-11-*.md（小菜鸟、大富翁、tangoo、复盘、课代表等系列）
```

**关键设计原则**：Python 层只负责 **数据准备**，所有点评、分析话术由 LLM 用 Z 哥角色生成，避免“AI 味”。宿主通过 CLI `--json` 或 Web API 获取结构化数据。

**自优化双管线说明**：
- `self_optimizer/`（Darwin 管线）：LLM 驱动的参数自优化，通过变异 + 评分 + 反射黑名单迭代策略参数组合。
- `simulator/walk_forward`：滚动窗口样本内训练 + 样本外验证的参数寻优。
- `verify/`（v3.7.0+）：少妇战法 v1.0 验收工程化，提供一键 `zt verify v1.0` 与五项硬指标判定。
- 三者**互补** —— Darwin 做探索性优化，walk-forward / verify 做验证性优化，防止过拟合。典型流程：Darwin 产出候选参数集 → walk-forward / verify 验证其样本外稳定性 → 通过者写回 `param_registry`。

---

## 技术栈与运行时架构

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 数据管道 | Python 3.10+（标准库 + `sqlite3`、`pathlib`、`dataclasses`、`enum`） |
| 外部数据 | `tushare`（Pro API，支持中转 URL）、`pandas`、`requests`、`httpx`、`pyyaml` |
| 环境配置 | `python-dotenv`（`.env` 文件） |
| 数据库 | SQLite（本地文件，15 张核心表 + 4 张自我改进跟踪表） |
| 接口协议 | CLI（`zt` 入口）、可选 FastAPI Web 服务（`zt-web`） |
| 前端看板 | React 19 + Vite 8 + TypeScript 6 + Tailwind CSS 4 + ECharts 6 |
| 状态管理 | Zustand + TanStack React Query |
| 测试框架 | `pytest`（962 用例 passed，12 skipped） |
| 代码质量 | `ruff`（lint + format）、`mypy`、pre-commit |
| 视频下载 | `yt-dlp`（语料采集，可选） |
| 语音转写 | `faster-whisper`（语料采集，可选） |
| 文档格式 | Markdown（全部文档与语料） |
| 版本控制 | Git |

### 关键配置文件

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 包定义、`zt` / `zt-web` / `zt-monitor` 命令入口、pytest/ruff/mypy/coverage 配置、可选依赖分组 |
| `requirements.txt` | 核心 Python 依赖（含 `pyyaml`、`httpx`） |
| `.env.example` | 环境变量模板（`.env` 不入库） |
| `frontend/package.json` | 前端依赖与脚本 |
| `frontend/vite.config.ts` | Vite 配置（端口 5173，代理 `/api` 到 localhost:8000） |
| `.editorconfig` | 编辑器格式统一配置 |
| `.pre-commit-config.yaml` | 提交前 ruff、部分 mypy、SKILL.md 12 项质量门、双轴评审（手动）、merge/yaml/行尾空白检查 |
| `.github/workflows/test.yml` | CI：测试、lint、类型检查、质量门、真实数据回归、pre-commit |
| `.github/workflows/e2e-cron.yml` | 每周一真实数据回归 cron |

### 环境变量说明（`.env.example`）

```ini
DATA_MODE=jnb                       # jnb(真实数据) 或 websearch(纯对话)
TUSHARE_TOKEN=你的56位token
TUSHARE_API_URL=                    # 中转 API 地址（JNB 模式必填）
# TUSHARE_VERIFY_TOKEN_URL=***      # 可选，实时行情验证地址
DATA_DIR=data
DB_PATH=data/stock_data.db
LLM_API_KEY=***                     # 可选，LLM 回答生成
# KB_ENABLED=true                   # 可选，向量知识库
IM_PUSH_WEBHOOK=                    # 可选，飞书 webhook
```

> v2.1.1 之后，所有 Tushare URL 均从环境变量读取，代码中不再硬编码任何内部域名。

---

## 项目结构

模块级别的详细架构树见上方「架构分层」一节。顶层目录结构：

```
zettaranc-skill/
├── SKILL.md / README.md / AGENTS.md / pyproject.toml / .env.example
├── data/          # SQLite 数据库与报告（不入库）
├── docs/          # 文档（CHANGELOG, TODO, USER_GUIDE 等）
├── modules/       # Python 数据层与业务逻辑（详见架构分层）
├── api/           # FastAPI REST API（可选）
├── frontend/      # React 前端看板（可选）
├── knowledge/     # 33 篇交易体系知识文档
├── tests/         # pytest 测试（61 个文件）
├── scripts/       # 薄壳工具脚本（业务逻辑在 modules/）
├── corpus/        # 语料采集与质检工具
├── rules/         # 意图规则与决策框架
└── references/    # 调研提炼文件（原始语料不入库）
```

---

## 数据库架构

`modules/database.py` 初始化以下表：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `stock_basic` | 股票基本信息 | ts_code, name, industry, market, list_date |
| `daily_kline` | 日线 K 线 | open, high, low, close, vol, amount, pct_chg |
| `indicator_cache` | 技术指标缓存（每日快照） | KDJ/MACD/BBI/MA/RSI/WR/布林带/双线/砖形图/DMI/量比/信号 |
| `moneyflow` | 资金流向 | 大小单买卖金额、净流入 |
| `financial_data` | 财务报表 | revenue, net_profit, total_assets, pe, pb, ps |
| `trade_signals` | 交易信号记录 | signal_type, signal_score, signal_price |
| `trade_records` | 随堂测试/交易记录 | action, price, quantity, reason, signal_type, zg_review |
| `sync_log` | 数据同步日志 | data_type, last_date, status |
| `watchlist` | 自选股观察池 | ts_code, name, tags, add_date, alert_enabled |
| `tushare_indicator_cache` | Tushare 官方指标（diff 验证） | macd_dif, rsi_6, kdj_k, boll_mid 等 |
| `llm_response_log` | LLM 响应耗时日志 | ts_code, request_date, model, response_time_ms, success |
| `tracking_pool_self` | 自我改进跟踪池 | ts_code, add_date, status, strategy_tags |
| `tracking_records_self` | 跟踪记录表 | 行情 + 指标 + 信号每日快照 |
| `monthly_reviews_self` | 月度复盘表 | review_month, monthly_return, max_drawdown 等 |
| `strategy_performance_self` | 策略表现统计表 | strategy_name, review_month, accuracy_rate, sharpe_ratio |

每张表均建立合适的复合索引（如 `ts_code + trade_date DESC`）。

---

## 构建、测试与常用命令

### 安装依赖

```bash
# 核心 Python 依赖
pip install -r requirements.txt
# 或安装为本地可编辑包（推荐，会注册 zt / zt-web / zt-monitor 命令）
pip install -e .

# 语料处理可选依赖
pip install -e ".[corpus]"

# 开发测试依赖
pip install -e ".[dev]"
```

安装后可使用 `zt` 命令：

```bash
zt analyze 600487.SH
zt screen --strategy B1 --limit 20
zt watchlist scan
zt backtest shaofu 600487.SH --days 250
zt verify v1.0 --limit 50 --days 300 --walk-forward
```

### 运行测试

```bash
# 全部测试（验证结果：962 passed, 12 skipped）
python -m pytest tests/ -v

# 单文件测试
python -m pytest tests/test_indicators.py -v

# 慢速端到端测试（默认不跑）
python -m pytest tests/ -m slow -v

# 真实数据回归（需 TUSHARE_TOKEN + TUSHARE_API_URL）
python -m pytest tests/test_indicators_realdata.py -v
```

> `test_indicators_realdata.py` 等真实数据测试会在无 `TUSHARE_TOKEN` 时自动 skip。

### 数据库初始化与数据同步

```bash
# 初始化数据库（创建 15+ 张表）
python -m modules.database
# 或
zt sync init

# 同步股票基本信息（全量 5525 只）
python -m modules.data_sync sync
# 或
zt sync sync

# 同步单只股票 K 线 + 指标缓存
python -m modules.data_sync sync --ts_code 600487.SH --days 365 --indicators
# 或
zt sync sync --ts_code 600487.SH --days 365 --indicators

# 查看同步状态
zt sync status

# 同步 Tushare 官方指标（diff 验证）
zt sync stk-factor --ts_code 600487.SH --days 365
```

### CLI 主要命令

```bash
zt analyze <ts_code> [--days N] [--json]          # 分析单只股票
zt screen --strategy <策略> [--limit N] [--json]   # 批量选股（11 种策略别名）
zt score <ts_code> [--json]                        # 综合评分
zt diagnose <ts_code> [--days N] [--json]          # 持仓诊断
zt workflow                                          # 每日五步工作流
zt watchlist add <ts_code> --tags <标签>           # 添加自选股
zt watchlist list                                  # 查看观察池
zt watchlist scan [--json]                         # 批量扫描信号
zt watchlist remove <ts_code>                      # 移除自选股
zt backtest shaofu <ts_code> [--days N] [--json]   # 少妇战法回测
zt backtest multi <ts_code> [--days N] [--json]    # 多策略融合回测
zt backtest portfolio <c1,c2,...> [--days N]       # 组合回测
zt simulate [codes] --days N --capital N --max-positions N --risk R --score S --signals N --json  # 交易模拟器
zt simulate [codes] --strategy-mode resonance --strategy-lookback N --min-resonance-score S --json  # 战法共振模式
zt simulate [codes] --walk-forward --wf-train-days N --wf-test-days N --wf-objective calmar --json  # Walk-forward 寻优
zt verify v1.0 [--limit N] [--days N] [--walk-forward] [--json]  # 少妇战法 v1.0 五项硬指标验收
zt trade add "口语化交易描述"                       # 记录交易
zt trade list / review / stats                     # 交易记录管理
zt daily [--json]                                  # 每日五步工作流
zt monitor [--json] [--no-push]                    # 自选股主动监控
zt track add/list/info/status/stats                # 自我改进跟踪池
zt self-optimize run/status/reset                  # Darwin 自优化
zt sync init/sync/status/stk-factor                # 数据同步
```

### 启动 Web 看板

> `api/` 依赖 `fastapi`、`uvicorn`、`pydantic-settings`，当前未写入 `requirements.txt`，运行前请单独安装：

```bash
pip install fastapi uvicorn pydantic-settings

# 启动后端
zt-web
# 或 python -m api.main

# 启动前端（另开终端）
cd frontend
npm install
npm run dev        # 默认 http://localhost:5173
npm run build      # 生产构建
npm run lint       # ESLint 检查
```

### 质量检查

```bash
# 验证 SKILL.md 是否通过 12 项质量标准
python corpus/quality_check.py SKILL.md

# strict 模式（任一不通过则 exit 1）
python corpus/quality_check.py SKILL.md --strict

# 双轴评审（轴 A 确定性 + 轴 B LLM 深度，--skip-llm 可跳过 LLM）
python corpus/dual_axis_review.py SKILL.md --skip-llm
```

### 语料采集脚本

| 脚本 | 用法 | 说明 |
|------|------|------|
| `corpus/batch_download_bilibili.py` | `python corpus/batch_download_bilibili.py` | 下载 B 站 ztalk 音频 |
| `corpus/batch_transcribe.py` | `python corpus/batch_transcribe.py` | 音频转写文本 |
| `corpus/srt_to_transcript.py` | `python corpus/srt_to_transcript.py input.srt` | 字幕清洗为纯文本 |
| `corpus/merge_research.py` | `python corpus/merge_research.py` | 合并调研结果 |

**路径约定**：部分脚本使用硬编码相对路径，请在项目根目录执行，并注意 `references/sources/` 中的原始语料不入库。

---

## 代码风格与开发规范

### 通用规范

- 所有脚本文件头包含 `#!/usr/bin/env python3`
- 使用 **中文** 编写文档字符串和注释
- 使用标准库为主，避免引入不必要的第三方依赖
- 每个模块文件末尾包含 `if __name__ == "__main__":` 命令行入口

### 编辑器配置（`.editorconfig`）

| 文件类型 | 缩进 | 大小 |
|---------|------|------|
| `*.py` | space | 4 |
| `*.sh` | space | 4 |
| `*.md` | space | 2（不裁剪行尾空格） |
| `*.json` | space | 2 |
| 全部 | UTF-8 | LF 换行 |

### Python 模块规范

- **数据库路径**：统一从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取，支持相对路径和绝对路径
- **环境变量加载**：统一由 `modules/__init__.py` 在包首次 import 时一次性加载 `.env`；各子模块不再重复加载
- **模块间 DB 路径解析**：`modules/*.py` 使用 `Path(__file__).parent.parent`（项目根目录）；`modules/indicators/*.py` 使用 `Path(__file__).parent.parent.parent`
- **限流控制**：所有 Tushare API 调用必须带 `_rate_limit()`，控制 120 次/分钟
- **事务管理**：数据库操作统一使用 `get_connection()` 上下文管理器（自动 commit/rollback，默认 WAL 模式）
- **错误处理**：API 调用用 try/except 包裹，记录 error log，返回空 DataFrame/None 而非抛异常中断
- **包安装**：使用 `pip install -e .` 安装后，可通过 `zt` 命令或 `python -m modules.cli` 调用

### Lint / Format / Type（`pyproject.toml` 配置）

- **ruff**：`line-length = 120`，`target-version = py310`，扩展排除 `data/`、`logs/`、`knowledge/`
  - lint 选择：`F, E, W, UP`
  - 忽略：`E501, F401, F403`
  - 测试文件额外忽略 `F811`
  - format：`quote-style = "double"`，`indent-style = "space"`
- **mypy**：`ignore_missing_imports = true`，仅对关键路径做类型检查
- **pre-commit**：每次 commit 自动跑 ruff、部分 mypy、SKILL.md 12 项质量门、merge/yaml/行尾空白检查；双轴评审钩子为手动触发

### 版本规则

严格遵循语义化版本（Semantic Versioning）：`MAJOR.MINOR.PATCH`

| 位 | 含义 | 示例 |
|----|------|------|
| MAJOR | 不兼容的 API 变更 | SKILL.md 心智模型重构、CLI API 不兼容变更 |
| MINOR | 向后兼容的功能新增 | 新增战法/指标、新增 CLI 子命令、新增数据源 |
| PATCH | 向后兼容的 bug 修复和内部重构 | bug 修复、性能优化、技术债清理、文档更新 |

**版本发布策略**：
- **PATCH**：随时发布（bug 修复、小改进）
- **MINOR**：功能积累到一定程度后发布（每月/每季度）
- **MAJOR**：重大架构变更时发布（每年/每两年）

**注意**：技术债清理、内部重构属于 PATCH，不是 MINOR。避免版本号增长过快。

---

## 测试策略

### 测试架构

- **框架**：pytest
- **配置**：`pyproject.toml` 中 `testpaths = ["tests"]`，默认 `-v --tb=short`
- **标记**：
  - `@pytest.mark.slow` 用于慢速端到端测试（如 self_optimizer 多轮），默认不跑
  - `@pytest.mark.realdata` 用于真实数据回归测试（需 `TUSHARE_TOKEN` + `RUN_REALDATA=true`），默认 skip
- **Fixture**：`tests/conftest.py` 提供
  - `mock_env_for_tests`：自动将环境变量 mock 到临时目录
  - `temp_db`：初始化好的临时数据库
  - `db_conn`：数据库连接
- **数据工厂**：`make_kline_row()`、`make_daily_data()`、`generate_uptrend_klines()`、`generate_downtrend_klines()`、`generate_b1_scenario()` 等
- **数据库隔离**：所有测试使用临时 SQLite 文件，互不干扰

### 测试覆盖范围（当前 61 个测试文件）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_database.py` | 路径解析、连接上下文、事务回滚、表初始化、幂等性 |
| `test_indicators.py` | 60+ 指标计算（MA/EMA/KDJ/MACD/背离/BBI/RSI/WR/布林带/量比/双线/单针/砖形图/B1B2/呼吸结构/SB1/沙漏/牛绳/蜈蚣图等） |
| `test_strategies.py` | B1/B2/B3/SB1/长安/四分之三阴量/娜娜/异动地量/出货五式等 |
| `test_screener.py` / `test_screener_p3.py` / `test_screener_data.py` | 选股评分、P3 指标接入评分、数据层 |
| `test_backtest.py` / `test_loop_engine.py` / `test_backtest_six_step.py` / `test_backtest_scorer.py` | 回测框架与六步闭环 |
| `test_portfolio_diagnosis.py` | 持股检查、防卖飞、出货信号、战法匹配 |
| `test_watchlist.py` | 观察池增删改查、批量扫描 |
| `test_wave_theory.py` | 三波理论识别 |
| `test_kirin_detector.py` | 麒麟会四阶段 |
| `test_cli_screen.py` / `test_cli_subparser.py` / `test_cli_simulate.py` | CLI 子命令分发与参数解析 |
| `test_data_e2e.py` / `test_data_sync.py` / `test_data_sync_extensions.py` / `test_datasource.py` / `test_indicator_cache.py` | 数据层端到端、同步、数据源、指标缓存 |
| `test_trade_manager.py` / `test_trade_parser.py` | 交易记录 CRUD、口语化解析 |
| `test_intent_router.py` | 意图路由规则匹配 |
| `test_quality_check.py` | SKILL.md 12 项质量检查 |
| `test_rate_limiter.py` | 120次/分钟限流器 |
| `test_bridge_client.py` / `test_tushare_client.py` | Tushare 客户端与 bridge 降级网关 |
| `test_monitor.py` / `test_notifier.py` | 自选股监控与推送 |
| `test_tracking_system.py` | 自我改进跟踪池 |
| `test_self_optimizer_*.py` / `test_param_registry.py` / `test_mutator.py` / `test_scorer.py` / `test_break_signal.py` / `test_reflex_blacklist.py` / `test_backtest_scorer.py` | Darwin 自优化管线 |
| `test_setup_wizard.py` / `test_report.py` / `test_exam_rules.py` | 初始化向导、报告、考试规则 |
| `test_simulator*.py`（11 个文件） | 模拟器约束、成本、环境权重、指标、参数空间、共振、strategy_adapter、仓位、walk_forward、optimizer_report、narrator |
| `test_statistics.py` | 统计检验框架 |
| `test_verify_*.py`（7 个文件） | v1.0 验收 CLI / gates / pipeline / registry_writer / report / scorer / walk_forward |
| `test_indicators_realdata.py` | 真实 Tushare 数据指标回归（无 token 时 skip） |

### 运行预期

```bash
$ python -m pytest tests/ -v
# 验证结果：962 passed, 12 skipped
```

---

## 文件修改优先级

1. **`SKILL.md`** —— 直接影响 Skill 表现，任何改动都需语料支撑
2. **`knowledge/*.md`** —— 知识文档，补充新语料或修正旧发现时更新
3. **`modules/*.py`** —— 数据层代码改动需同步更新测试
4. **`references/research/*.md`** —— 调研档案，新增语料源时更新
5. **`README.md` / `docs/CHANGELOG.md`** —— 项目对外文档，版本发布时同步更新
6. **`api/` / `frontend/`** —— Web 看板，仅在交互层需要改进时修改
7. **`scripts/`** —— 工具脚本，仅在数据管道或检查逻辑需要改进时修改

---

## 内容修改原则

1. **最小改动原则**：只改确实不准确的部分
2. **有依据**：任何改动都需要语料支撑，不能凭印象。优先来源：
   - zettaranc 本人直接产出（视频、直播、付费课、雪球专栏）
   - 权威媒体报道（澎湃新闻等）
   - 证券业协会公示资料
   - **不应作为主要依据**：知乎回答、非本人微信公众号、股吧/雪球帖子（除本人账号外）
3. **保持角色一致性**：修改后的回答仍需符合 zettaranc 的表达 DNA

### 风格验证清单

修改 `SKILL.md` 后，用以下问题自检：

- [ ] 是否用「我」而非「Z 哥认为...」？
- [ ] 是否包含职业背书开场？
- [ ] 是否分 1/2/3/4 点拆解？
- [ ] 是否用了具体数字或案例？
- [ ] 是否以金句或反问收尾？
- [ ] 是否避免跳出角色的表述？
- [ ] 交易建议是否包含具体的进场/止损/止盈规则？

---

## 安全与合规考虑

1. **免责声明**：`SKILL.md` 和 `README.md` 均包含明确免责声明——**不构成任何投资建议**。
2. **版权边界**：原始语料不提交到仓库。仓库中只保留粉丝整理的 Markdown 提炼文件和转写文本。
3. **敏感信息**：Tushare Token、API URL、LLM API Key、飞书 webhook 通过 `.env` 文件管理，**绝不硬编码**；`.env` 已加入 `.gitignore`。
4. **信息偏差标注**：`SKILL.md` 的「诚实边界」一节明确标注了公开表达与真实想法的差异。
5. **高风险动作**：Skill 不会代下单、转账或处理内幕信息；给出买卖建议时必须附加免责声明。
6. **语料截止期**：信息截止到调研时间（2026-04-18 及后续更新）。

---

## 常见任务速查

| 任务 | 操作 |
|------|------|
| 更新心智模型或交易规则 | 先查 `references/research/01-writings.md` 和 `05-decisions.md` → 修改 `SKILL.md` 与对应 `knowledge/*.md` → 运行 `corpus/quality_check.py SKILL.md` |
| 补充新语料 | 将新文章放入 `references/sources/articles/` → 更新对应 `references/research/*.md` → **不要**将原始语料加入 git |
| 新增 B 站视频 transcript | `python corpus/batch_download_bilibili.py && python corpus/batch_transcribe.py` |
| 发布新版本 | 更新 `SKILL.md` → 更新 `docs/CHANGELOG.md` → 同步 `README.md` 版本 badge → 同步 `pyproject.toml` 版本号 → 打 git tag |
| 验证风格一致性 | 对照「风格验证清单」逐项检查 |
| 修复数据层 bug | 修改 `modules/*.py` → 补充/更新 `tests/test_*.py` → `pytest tests/ -v` |
| 接入新 Tushare 接口 | 修改 `modules/tushare_client.py` 或 `modules/data_sync.py` → 确认 `modules/database.py` 表结构支持 → 补充保存逻辑与测试 |
| 初始化全新环境 | `cp .env.example .env` → 填入 Token → `python -m modules.database` → `python -m modules.data_sync sync` → `pytest tests/ -v` |
| 运行 Web 看板 | 安装 `fastapi uvicorn pydantic-settings` → `zt-web` → `cd frontend && npm install && npm run dev` |
| 跑 Darwin 自优化 | `zt self-optimize run --target trading --rounds 3` |
| 跑少妇战法 v1.0 验收 | `zt verify v1.0 --limit 50 --days 300 --walk-forward` |
| 跑参数寻优（v1.0） | `python scripts/optimize_for_v10_verify.py --rounds 5 --stocks 100 --days 300` |

---

> Love and Share 🖤
