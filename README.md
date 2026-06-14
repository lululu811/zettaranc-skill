# zettaranc（万千）· 思维操作系统

> *「利润是市场给的，都是概率的事儿，谁也别吹牛逼。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![v3.1.1](https://img.shields.io/badge/version-3.1.1-green)](docs/CHANGELOG.md)


<br>

**前阳光私募冠军基金经理、B站百大UP主的投资思维框架，可运行在真实行情数据之上。**<br>
基于 ~467 篇直播/付费课整理文章（约 200 万字）+ 13 个 ztalk 视频 transcript（12.7 万字）+ 9 篇股探报告交易心理系列（3.3 万字）的深度蒸馏。

<br>

[快速开始](#快速开始) · [CLI 工具](#cli-工具) · [Python API](#python-api) · [使用手册](docs/USER_GUIDE.md) · [架构说明](#架构说明) · [更新日志](docs/CHANGELOG.md)

</div>

---

## v3.1.1 能做什么


> **不只是炒股工具，是多场景智能决策系统。宿主（Claude Code / Cursor）可直接调用 CLI 工具获取真实数据。**

### 数据规模

| 数据表 | 行数 | 说明 |
|--------|------|------|
| stock_basic | 5,525 | 全量 A 股基本信息 |
| daily_kline | 25,591 | 测试股票 2 年 K 线（可增量同步至全量） |
| indicator_cache | 6,360 | 60+ 技术指标每日快照 |
| moneyflow | 207,361 | 全市场资金流向（60 天） |
| financial_data | 2,733 | 财报数据（含 PE/PB/PS） |
| tushare_indicator_cache | 12,554 | Tushare 官方指标（diff 验证用） |

### 六大核心能力

| 能力 | 说明 | 示例 |
|------|------|------|
| **🎯 意图识别** | 自动识别 stock/career/life/chat 四种意图，路由到对应角色框架 | `python -m modules.intent_chat "B1 买点怎么判断"` |
| **📊 股票分析** | 60+ 技术指标实时计算，战法自动识别，支持 `--json` 输出 | `zt analyze 600487.SH --json` |
| **📈 策略回测** | 少妇战法六步闭环 / 多策略融合 / 组合回测 | `zt backtest shaofu 600487.SH` |
| **🔍 智能选股** | 曼城评分 + 蜈蚣图过滤 + 沙漏评分 + 牛绳判断 | `zt screen --strategy B1 --limit 20` |
| **👁️ 观察池管理** | 自选股批量监控，每日信号扫描 + 报告生成 | `zt watchlist scan --json` |
| **🤖 宿主集成** | 所有 CLI 命令支持 `--json`，宿主可直接调用获取结构化数据 | `zt daily --json` |

### 完整功能清单

**策略与架构优化（v3.1.1 升级）**
- 🛡️ **输入数据大一统**：策略判定函数全面升级为 `list[DailyData]` 强类型输入，并通过智能防御网关实现对字典类型的 100% 向后兼容。
- 🚀 **彻底清空“猴子补丁”**：移除了针对核心指标模块动态劫持的补丁机制，升级为全量指标属性一次性挂载，各战法读取指标降低为 O(1) 开销。
- 🎣 **逃顶出货五式联动**：在 S2 (顶背离) / S3 (反弹受阻) 逃顶策略中集成出货五式量化验证，通过出货共振高危过滤大幅优化逃顶准确率。

**性能与架构优化（v2.10.0 新增）**

- ⚡️ **60x 指标计算提速**：全面引入 Pandas 向量化引擎（替换 Python For 循环），严格匹配通达信（TDX）算法精度。
- 🚀 **10x-50x 写入提速**：SQLite 数据同步全量采用 Batch Insert 并发写入（`executemany`），彻底消除性能瓶颈。
- 🌐 **多线程网络 I/O**：全市场 5000+ 股票数据并发拉取（`ThreadPoolExecutor`），带线程安全的 Tushare API 防封限流锁。
- 🧩 **模块深度解耦**：超大策略文件（1600行+）解耦为标准 Python 策略包，确保 367 项单元测试 100% 隔离安全。

**意图识别（v2.8.0 新增）**
- ✅ 四意图自动路由：stock / career / life / chat
- ✅ 规则匹配引擎（keywords + patterns，零 token 消耗）
- ✅ 向量知识库检索适配器（Qdrant，按意图分类过滤，默认关闭）
- ✅ LLM 生成层（MiniMax / OpenAI 兼容格式，可选）
- ✅ Z哥职业决策框架（rules/career_prompt.md）
- ✅ Z哥人生决策框架（rules/life_prompt.md）

**数据层**
- ✅ Tushare 真实行情接入（日线 OHLCV、资金流向、财报、财务指标）
- ✅ SQLite 本地缓存（5525 只股票基本信息 + K线 + 指标快照 + 财报）
- ✅ 增量同步（只拉取新增数据，避免重复请求）
- ✅ 120次/分钟限流保护
- ✅ 财务数据多接口组合（fina_indicator + income + balancesheet + daily_basic）

**指标计算（60+）**
- ✅ KDJ / MACD / BBI / RSI / WR / 布林带 / DMI
- ✅ 双线战法（白线+黄线）/ 单针下 20 / 砖形图
- ✅ 量比 / 资金流向 / 筹码分布

**P3 新指标（v3.1.0）**
- ✅ 蜈蚣图识别：5 因子评分（长上影/长下影/十字星/量能无规律/价格无趋势），≥60 分判定为呼吸紊乱
- ✅ 牛绳理论量化：牵牛/牛绳断/金叉/死叉 + 缺口百分比 + 白线趋势
- ✅ 量比战法引擎：6 种场景判定（攻击日/出货日/单向拉升/正常震荡/弱势日/超级攻击）
- ✅ 沙漏评分 V9：5 因子评分（缩量收敛/枢轴邻近/量能斜率/均线结构/事件风险），≥80 分为完美图形

**战法识别（30+）**
- ✅ B1 / B2 / B3 / SB1 / 超级 B1
- ✅ 长安战法 / 平行重炮 / 坑里起好货 / 对称 VA
- ✅ 四分之三阴量 / 娜娜图形 / 异动地量
- ✅ S1/S2/S3 逃顶体系
- ✅ 滴滴战法 / MACD 金叉空·死叉多 / 祖冲之法（目标价）
- ✅ 主力出货五式 / 灾后重建 / 跃跃欲试 / 关键 K 识别
- ✅ 三波理论（建仓波/拉升波/冲刺波）
- ✅ 麒麟会四阶段（吸筹/拉升/派发/回落）

**分析工具**
- ✅ 持股诊断（当前状态 + 防卖飞评分 + 出货信号扫描）
- ✅ 选股评分（趋势/量价/风险三维度）
- ✅ 自选股观察池（增删改查 + 批量扫描）
- ✅ 策略组合回测（多策略融合 + 资金曲线 + 仓位管理）
- ✅ 随堂交易记录（口语化输入 → 战法匹配 → Z 哥点评）

**LLM 角色层**
- ✅ Z 哥角色扮演（用「我」而非「Z哥认为」）
- ✅ 多轮问诊系统（周期 → 状态 → 仓位 → 诊断）
- ✅ 随堂测试复盘（口语化输入 → 战法匹配 → LLM 点评）

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/lululu811/zettaranc-skill.git
cd zettaranc-skill
pip install -r requirements.txt
```

> 安装完成后会注册 `zt` 命令（`zt analyze`、`zt screen`、`zt watchlist`、`zt diagnose`）。如不安装，也可直接 `python -m modules.cli` 调用。

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
DATA_MODE=jnb
TUSHARE_TOKEN=你的56位token
TUSHARE_API_URL=中转API地址
```

> [!NOTE]
> * **数据模式**：`DATA_MODE=jnb` 时必须配置 Tushare Token 和 API URL；`DATA_MODE=websearch` 时可留空。
> * **Token 获取**：前往 [Tushare 官网](https://tushare.pro/user/token) 注册获取 Token。
> * **中转 API**：可使用中转服务商提供的代理地址。
> * **LLM 配置**：可选。配置 `LLM_API_KEY` 等参数后可启用小万 LLM 对话及点评功能；未配置时将仅输出命令行分析及意图路由。
> * **向量知识库**：默认关闭，设置 `KB_ENABLED=true` 并配置对应服务后可开启本地 RAG 知识检索。

### 3. 初始化

```bash
# 创建数据库（8张表）
python -m modules.database

# 同步股票基本信息（5525只，只需执行一次）
python -m modules.data_sync sync

# 同步单只股票K线 + 指标缓存
python -m modules.data_sync sync --ts_code 600487.SH --days 120
```

### 4. 验证

```bash
# 运行测试（572 passed, 10 skipped）
python -m pytest tests/ -v

# 分析一只股票
python -m modules.cli analyze 600487.SH

# 选股扫描
python -m modules.cli screen --strategy B1 --limit 20

# 少妇战法回测
python -m modules.cli backtest shaofu 600487.SH --days 250
```


---

## CLI 工具

安装完成后，所有功能都可以通过命令行调用。

### 股票分析

```bash
# 完整分析（技术指标 + 战法识别 + 信号判断）
python -m modules.cli analyze 600487.SH

# 指定分析天数
python -m modules.cli analyze 600487.SH --days 60
```

### 选股扫描

```bash
# B1 选股
python -m modules.cli screen --strategy B1 --limit 20

# 完美图形
python -m modules.cli screen --strategy 完美图形 --limit 10

# 超级 B1
python -m modules.cli screen --strategy 超级B1 --limit 10

# 建仓波选股
python -m modules.cli screen --strategy 建仓波 --limit 20

# 吸筹阶段
python -m modules.cli screen --strategy 吸筹 --limit 20

# 安全标的
python -m modules.cli screen --strategy 安全 --limit 20
```

### 观察池

```bash
# 添加自选股
python -m modules.cli watchlist add 600487.SH --tags 波段,通信

# 查看观察池
python -m modules.cli watchlist list

# 批量扫描信号
python -m modules.cli watchlist scan

# 移除
python -m modules.cli watchlist remove 600487.SH
```

### 持仓诊断

```bash
# 诊断单只股票
python -m modules.cli diagnose 600487.SH

# 指定诊断天数
python -m modules.cli diagnose 600487.SH --days 100

# JSON 输出（宿主可直接解析）
python -m modules.cli diagnose 600487.SH --json
```

### 策略回测

```bash
# 少妇战法六步闭环回测
python -m modules.cli backtest shaofu 600487.SH --days 250

# 多策略融合回测
python -m modules.cli backtest multi 600487.SH --strategy b1,b2

# 多股票组合回测
python -m modules.cli backtest portfolio 600487.SH,601318.SH

# JSON 输出
python -m modules.cli backtest shaofu 600487.SH --json
```

### 交易记录

```bash
# 记录交易（口语化输入）
python -m modules.cli trade add "4月25号买了100股茅台，1800块"

# 查看交易记录
python -m modules.cli trade list

# 复盘
python -m modules.cli trade review

# 统计
python -m modules.cli trade stats
```

### 每日工作流

```bash
# 执行五步工作流（扫描观察池 + 选股 + 持仓检查 + 信号汇总 + 报告）
python -m modules.cli daily

# JSON 输出
python -m modules.cli daily --json
```

### 数据同步

```bash
# 查看同步状态
python -m modules.data_sync status

# 同步单只股票
python -m modules.data_sync sync --ts_code 600487.SH --days 120

# 同步并计算指标缓存
python -m modules.data_sync sync --ts_code 600487.SH --days 120 --indicators

# 同步 Tushare 官方指标（用于 diff 验证）
python -m modules.data_sync stk-factor --ts_code 600487.SH --days 365
```

---

## Python API

### 分析单只股票

```python
from modules.indicators import analyze_stock

result = analyze_stock("600487.SH", days=60)
print(f"J={result.j:.1f}, MACD DIF={result.dif:.2f}")
print(f"B1={result.is_b1}, B2={result.is_b2}")
print(f"信号: {result.signal}")
```

### 战法识别

```python
from modules.strategies import detect_all_strategies

signals = detect_all_strategies("600487.SH", days=60)
for s in signals:
    print(f"{s.trade_date}: {s.strategy} 置信度={s.confidence} 操作={s.action}")
```

### 策略回测

```python
from modules.backtest import backtest_multi_strategy, backtest_portfolio

# 单股票多策略融合
result = backtest_multi_strategy(
    ts_code="600487.SH",
    days=120,
    strategies=["b1", "b2"],
    position_pct=0.3  # 单信号30%仓位
)
print(f"胜率: {result.win_rate:.1%}")
print(f"夏普: {result.sharpe_ratio:.2f}")

# 多股票组合
portfolio_result = backtest_portfolio(
    ts_codes=["600487.SH", "000001.SZ"],
    days=120,
    max_weight=0.4  # 单股上限40%
)
```

### 少妇战法六步回测

```python
from modules.backtest_six_step import backtest_shaofu_single, backtest_shaofu_portfolio

# 单股票回测（择时→选股→等B1→止损→卤煮止盈→BBI离场）
result = backtest_shaofu_single("600487.SH", days=250)
print(f"交易: {result.total_trades}笔  胜率: {result.win_rate:.1%}")
print(f"收益: {result.total_return:+.1f}%  夏普: {result.sharpe_ratio:.2f}")

# 组合回测
portfolio = backtest_shaofu_portfolio(["600519.SH", "601318.SH", "000858.SZ"])
```

### 选股

```python
from modules.screener import screen_stocks

results = screen_stocks(criteria="b1", max_stocks=50)
for r in sorted(results, key=lambda x: x.score, reverse=True)[:10]:
    print(f"{r.ts_code}({r.name}): 总分={r.score}")
```

### 持股诊断

```python
from modules.portfolio_diagnosis import diagnose_stock, format_report

report = diagnose_stock("600487.SH", days=100)
print(format_report(report))
```

### 获取 K 线数据

```python
from modules.indicators import get_kline_data

klines = get_kline_data("600487.SH", days=60)
for k in klines[-5:]:
    print(f"{k.trade_date}: 开{k.open} 高{k.high} 低{k.low} 收{k.close} 量{k.vol}")
```

---

## 架构说明

### 双模式架构

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| **JNB 模式** | `DATA_MODE=jnb` | 接入 Tushare 真实行情，具备实时数据查询、技术指标计算、战法识别能力 |
| **普通小万** | `DATA_MODE=websearch` | 纯 LLM 对话，不走任何外部数据接口 |

### 项目结构

```
zettaranc-skill/
├── SKILL.md                    # 核心 Skill 文件（LLM 角色扮演协议）
├── README.md                   # 本文件
├── CHANGELOG.md                # 版本变更日志
├── AGENTS.md                   # AI Agent 开发指南
├── docs/
│   ├── USER_GUIDE.md           # 详细使用手册与操作手册
│   ├── CONFIG_GUIDE.md         # 配置指南（v2.8.0 新增）
│   └── CHANGELOG.md            # 版本变更日志
├── .env / .env.example         # 本地配置
├── rules/                      # 意图识别规则与角色框架（v2.8.0 新增）
│   ├── intent_rules.yaml       # 意图匹配规则（keywords + patterns）
│   ├── career_prompt.md        # Z哥职业决策框架
│   └── life_prompt.md          # Z哥人生决策框架
├── data/
│   └── stock_data.db           # SQLite 数据库（8张表）
├── modules/                    # Python 数据层（~11800 行）
│   ├── tushare_client.py       # Tushare API 封装
│   ├── database.py             # SQLite 管理（8张表 + 事务上下文）
│   ├── data_sync.py            # 数据同步（增量/全量，限流120次/分）
│   ├── indicators/             # 技术指标引擎（60+指标，6子模块）
│   │   ├── core.py             # 基础类型 + 数学工具 + 核心指标
│   │   ├── price_patterns.py   # 价格形态（双线/单针/砖型图/B1B2B3/三波理论）
│   │   ├── volume_patterns.py  # 量价信号（卖出评分/交易信号/出货五式）
│   │   ├── wave_theory.py      # 三波理论识别（建仓/拉升/冲刺波）
│   │   ├── kirin_detector.py   # 麒麟会四阶段（吸筹/拉升/派发/回落）
│   │   └── data_layer.py       # 数据接入 + 缓存层 + 可视化
│   ├── strategies/             # 30+ 战法识别引擎（6 子模块）
│   ├── screener.py             # 选股评分体系（含蜈蚣图/沙漏/牛绳过滤）
│   ├── backtest.py             # 策略组合回测框架
│   ├── backtest_six_step.py    # 少妇战法六步闭环回测
│   ├── loop_engine.py          # 六步闭环状态机（择时→选股→B1→止损→卤煮→BBI离场）
│   ├── portfolio_diagnosis.py  # 持股检查端到端（含蜈蚣图/牛绳/沙漏诊断）
│   ├── watchlist.py            # 自选股观察池
│   ├── cli.py                  # 命令行工具入口（analyze/screen/backtest/trade/daily）
│   ├── cli_commands.py         # 扩展命令（backtest/trade/daily）
│   ├── intent_router.py        # 意图识别与路由（v2.8.0 新增）
│   ├── knowledge_retriever.py  # 向量知识库检索适配器（v2.8.0 新增）
│   ├── intent_chat.py          # 意图聊天界面（v2.8.0 新增）
│   ├── llm_providers.py        # LLM 提供商（v2.8.0 新增）
│   ├── trade_parser.py         # 口语化输入解析
│   ├── trade_manager.py        # 交易记录 CRUD
│   ├── trade_reviewer.py       # 交割单数据准备层（给 LLM 用）
│   ├── setup_wizard.py         # 初始化配置向导
│   └── trade_reviewer.py       # 交割单数据准备层（含 Z 哥话术常量）
├── knowledge/                  # 知识文档（14篇交易体系）
├── tests/                      # 单元测试（pytest，543 用例，24 个测试文件）
├── scripts/                    # 工具脚本（薄壳，业务逻辑在 modules/）
│   ├── _common.py              # 共享工具（load_watchlist 等）
│   ├── sync_watchlist.py       # 同步缺失的自选股 K 线
│   ├── sync_and_compute.py     # 一站式同步 + 指标计算
│   ├── batch_compute_indicators.py  # 批量计算指标缓存
│   ├── generate_report.py      # 生成 Z 哥量化评估报告
│   └── fetch_tushare_data.py   # Tushare 数据抓取（DEPRECATED）
├── corpus/                     # 语料采集与质检工具
│   ├── quality_check.py        # SKILL.md 质量自动检查（8 项）
│   └── ...                     # 批量下载/转写/合并工具
└── references/                 # 调研提炼文件
```

### 数据库表结构

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `stock_basic` | 股票基本信息 | ts_code, name, industry, market |
| `daily_kline` | 日线 K 线 | open, high, low, close, vol, pct_chg |
| `indicator_cache` | 技术指标缓存 | KDJ, MACD, BBI, MA, RSI, WR, 布林带, 双线, 砖形图, DMI, 量比 |
| `moneyflow` | 资金流向 | 大小单买卖金额, 净流入 |
| `financial_data` | 财务报表 | revenue, net_profit, total_assets, pe, pb, ps |
| `trade_signals` | 交易信号记录 | signal_type, signal_score, signal_price |
| `trade_records` | 交易记录 | action, price, quantity, reason, zg_review |
| `watchlist` | 自选股观察池 | ts_code, name, tags, add_date |

### 回测数据（v3.1.0 真实数据验证）

**测试环境**：20 只 A 股（000001.SZ ~ 000032.SZ），484 天 K 线，回测 250 天。

**少妇战法六步闭环**（J≤12 + 缩量 + N型上移 + 最少持仓3天 + BBI跌破1%阈值）：

| 指标 | 数值 |
|------|------|
| 总交易 | 120 笔 |
| 胜率 | 35.0%（42/120） |
| 总收益 | +81.4%（20 只股票合计） |
| 平均持仓 | 5 天 |
| 有交易股票 | 20/20 |

**多策略融合回测**（B1+B2+B3，10 只头部股票）：

| 指标 | 数值 |
|------|------|
| 平均胜率 | 52.1% |
| 平均累计收益 | +2.5% |
| 平均夏普比率 | 0.31 |
| 平均最大回撤 | 4.7% |
| 最高收益 | 深中华A +12.0% |
| 最高夏普 | 深粮控股 1.32 |

**关键发现**：
- 沙漏评分是最有效的选股过滤器：≥69 分的 7 只股票中 5 只赚钱（万科 +16.9%、沙河 +21.5%、深中华 +17.5%、深科技 +19.4%、深圳能源 +13.5%）
- 蜈蚣图≥60 分的票表现两极化，不能单独作为硬过滤
- BBI 离场需要最少持仓天数保护，否则次日就被震出

### 关键设计原则

**Python 层只做数据准备，所有点评由 LLM 用 Z哥角色生成。宿主通过 CLI `--json` 获取结构化数据。**

```
用户输入 → 宿主(Claude Code/Cursor) → 调用 CLI 工具(zt analyze/screen/backtest --json)
                                            ↓
                                    Python 层执行真实计算
                                            ↓
                                    JSON 结构化数据返回宿主
                                            ↓
                                    宿主用 Z哥口吻包装回复

Tushare API → data_sync → SQLite → indicators/ → strategies/ → backtest/
                                              ↓
                                    screener（蜈蚣图/沙漏/牛绳过滤）
                                              ↓
                                    loop_engine（少妇六步闭环）
                                              ↓
                                    SKILL.md (LLM 角色层 + 工具描述)
```

---

## 效果示例

### 问：帮我分析一下亨通光电

```
用户 > zt analyze 600487.SH

zettaranc ❯ 亨通光电，22.81，跌了1.76%。

         我看看指标——KDJ还没死叉，J值57，还在多头区间。
         MACD白线在零轴上方，趋势没坏。

         但注意：今天这根阴线放量，而且破了昨日低点。
         这是滴滴战法的触发条件：浮盈的飞一半，浮亏的全清。

         如果你还拿着，现在不是加仓的时候，是先防守。
         等站稳再说。

         综合评分：72.5 ★★★★☆ 推荐
         牛绳理论：牵牛（缺口+4.1%，白线上升）
         沙漏评分：72/100
```

### 问：B1买点现在还能买吗？

```
zettaranc ❯ B1不是想买就能买，得满足三个条件：

         1. 黄线在下面托着（主力在场）
         2. KDJ的J值在0-30之间（超卖区）
         3. 成交量不能是地量（要有资金进来）

         你现在这只票，J值58，不在超卖区。
         这不是B1，这是追高。

         记住：宁可错过，不做错。
         错过只是少赚，做错是本金没了。
```

### 问：我想辞职全职炒股

```
zettaranc ❯ 辞职全职炒股？兄弟，我劝你慎重。

         你以为全职炒股是自由？
         是每天早上 9:15 坐在电脑前，
         周末还要研究政策、财报、行业数据。
         这叫自由？这叫给自己找了个 7×24 的老板。

         先兼职做，用闲钱做，把交易系统跑通至少一个牛熊周期。
         选择大于努力。但选择之前，先把基本功练扎实。
```

### 问：回测一下万科A

```
用户 > zt backtest shaofu 000002.SZ --days 250

zettaranc ❯ 万科A，跑了250天的回测：

         8笔交易，6笔赚钱，胜率75%。
         累计收益+16.9%，平均持仓7天。

         赚钱的关键是什么？沙漏评分72分，图形质量不错。
         B1信号出现时，牛绳虽然断了，但缩量回调到位，
         N型结构也形成了，所以入场时机抓得准。

         止损只触发了2次，说明入场点选得好，
         不是靠扛，是靠等。
```

---

## 语料基础

| 来源 | 数量 | 时间 |
|------|------|------|
| 本地直播/付费课整理文章 | **~467 篇**（约 **200 万字**） | 2025.6 - 2026.4 |
| ztalk B 站视频 transcript | 13 个 (~12.7 万字) | 2019 - 2021 |
| 股探报告系列（微博小号 @股探报告） | 9 篇 (~3.3 万字) | 2017.12 |
| 雪球专栏长文 | 1 篇 | 2014.12 |

调研提炼文件详见 `references/research/` 目录（11 份调研报告）。

---

## 版本规范

遵循语义化版本：MAJOR（心智模型重构 / 架构升级）.MINOR（语料扩展/新增模块）.PATCH（排版修复）。

| 版本 | 核心变化 |
|------|---------|
| **v3.1.0** | P3 指标补完（蜈蚣图/牛绳/量比战法/沙漏V9）、少妇六步闭环引擎、CLI --json 输出 + backtest/trade/daily 新命令、screener 集成新指标、真实数据回测验证 |
| **v3.0.0** | 编排模式 + 人生/创业蒸馏 + 双维度扩展 + 14 条决策启发式 |
| **v2.10.0** | CLI 3 bug 修复 + zt 统一入口、6 脚本薄壳化（-94%）、5 CI job + pre-commit 护栏、501 测试、代码审查、废弃模块清理 |
| **v2.9.0** | 60x 指标计算提速（Pandas 向量化）、10x-50x 写入提速（executemany）、多线程并发拉取、模块解耦 |
| **v2.7.0** | 数据层充实（真实财报/PE/PB/PS/资金流全量入库）、SAT/UAT 测试体系、策略 DB 路径修复、使用手册 |
| **v2.6.0** | P2 核心模块（三波理论/麒麟会四阶段）、screener 新增选股条件 |
| **v2.5.0** | P0/P1 指标补全（滴滴/金叉空/出货五式/灾后重建）、工程化补完（pyproject.toml / dotenv 统一 / Bug 修复） |
| **v2.4.0** | indicators 拆分子模块 + 缓存层 + CLI 工具 + 回测框架 + 递推修复 |
| **v2.3.0** | 持股诊断、观察池、S1/S2/S3 逃顶、战法补完 |
| **v2.2.0** | 15 篇新增语料、5 份调研报告、考试规则验证 |
| **v2.1.0** | 随堂测试复盘、Python 数据层 + LLM 点评层架构 |
| **v2.0.0** | Tushare 真实数据接入、60+ 指标、30+ 战法 |

详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 使用手册

详细的使用手册与操作指南请查看 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)，包含：

- 环境配置详解
- 数据库初始化与数据同步
- 六大核心功能完整操作手册
- Python API 调用示例
- 技术指标体系速查
- 战法体系速查
- 日常操作流程（每日/每周/每月）
- 常见问题 Q&A

---

## 免责声明

此 Skill 用于理解 zettaranc（万千）的思维模式，**不构成任何投资建议**。金融市场风险极高，任何基于历史信息的交易框架都可能失效。

- 外部可查记录显示 zettaranc 主要经历在私募基金/券商资管，最高规模约 11 亿
- 2017 年太平洋证券资管产品「柏悦量化1号」全年收益 -9.1%，大幅跑输沪深 300（+21.78%）
- 交易纪律的知行合一是最大瓶颈，Skill 可以提供框架但无法替你执行止损

**理解不等于模仿。投资有风险，入市需谨慎。**

---

## 关注公众号

关注「小陈无所事事的一天」，分享日常生活和瞎折腾。

<div align="center">

![小陈无所事事的一天](assets/wechat-qr.png)

> 扫码关注，看小陈今天又折腾了什么

</div>

---

## 仓库关联

| 平台 | 地址 | 说明 |
|------|------|------|
| **GitHub** | https://github.com/lululu811/zettaranc-skill.git | 主仓库 |
| **Gitee** | https://gitee.com/chenleizzzz/zettaranc-knowledge.git | 镜像同步 |

---

<div align="center">

*心中无牛熊，唯有纪律坚。*

<br>

MIT License

</div>
