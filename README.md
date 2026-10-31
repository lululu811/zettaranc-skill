# zettaranc（万千）· 思维操作系统

> **散户最难的不是选股，是卖出时管住手。**

前阳光私募冠军基金经理、B站百大UP主的交易纪律，封装成可运行在真实行情上的 AI Skill。
基于 ~200 万字语料蒸馏，60+ 指标，30+ 战法，可回测可模拟、可自改进、可走完整闭环。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-4.11.0-green)](docs/CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-1597%20passed%20%7C%2016%20skipped-brightgreen)](tests/)
[![Quality Gate](https://img.shields.io/badge/quality-12%2F12-blue)](corpus/quality_check.py)
[![Skill](https://img.shields.io/badge/Skill--Schema--V2-✓-purple)](SKILL.md)

---

## 30 秒体验（无需 Token）

```bash
# 1. 克隆并安装
git clone https://github.com/lululu811/zettaranc-skill.git && cd zettaranc-skill
pip install -r requirements.txt && pip install -e .

# 2. 零配置模式（自动走免费数据源 a-stock-data，无需 tushare 积分）
echo "DATA_MODE=websearch" > .env

# 3. 立即体验
zt analyze 600519.SH  # 用框架分析茅台，自动获取实时行情
```

> **数据源说明**：默认集成 [a-stock-data](https://github.com/simonlin1212/a-stock-data) 免费数据源（腾讯/百度/东财/通达信），零积分即可使用实时行情、K 线、股票信息。v4.2.0 起支持 [同花顺官方金融数据服务](https://fuyao.aicubes.cn/)（hithink-finance），配置 `HITHINK_FINANCE_API_KEY` 后自动作为最优先数据源。详见 [CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md)。

---

## 它能做什么

| 能力 | 说明 | 示例 |
|------|------|------|
| 📊 **股票分析** | 60+ 技术指标 + 30+ 战法自动识别 + 综合评分 | `zt analyze 600487.SH --json` |
| 📈 **策略回测** | 少妇战法六步 / 多策略融合 / 组合回测 / B2 确认 / Walk-forward 寻优 | `zt backtest shaofu 600487.SH` |
| 🧪 **端到端模拟** | T+1 + 涨跌停 + 真实成本 + ATR 仓位 + 战法共振 | `zt simulate 000001.SZ --days 250` |
| 🔍 **智能选股** | 13 种筛股条件 + 战法共振 + 环境权重动态调整 | `zt screen --strategy B1 --limit 20` |
| 🧭 **市场择时** | 大盘择时指标，判断当前是否适合持仓 | `zt market timing --json` |
| 👁️ **观察池监控** | 自选股批量监控 + 主动预警 + 飞书推送 | `zt watchlist scan --json` |
| 🤖 **宿主集成** | 所有命令支持 `--json`，Claude / Cursor 可直接调用 | `zt daily --json` |
| 🧬 **自我改进** | 跟踪池 + 月度复盘 + Darwin 自优化管线 | `zt self-optimize run --target trading` |
| 🌐 **Web 看板**（可选） | FastAPI 后端 + React 19 + ECharts 前端 | `zt-web` + `cd frontend && npm run dev` |

---

## 核心策略：少妇战法

**六步闭环状态机驱动的趋势跟踪系统**，解决散户"不会买、不会卖、拿不住"三大痛点。

### 两条核心趋势线

| 名称 | 公式 | 含义 | 作用 |
|------|------|------|------|
| **白线** | `EMA(EMA(C,10),10)` | 短期趋势，"牵牛绳" | 入场/出场参考线 |
| **黄线** | `(MA14+MA28+MA57+MA114)/4` | 中期趋势，"牛的方向" | 择时过滤 |

> **白线 > 黄线** = 主力牵牛，下跌是洗盘，可以持仓；**白线 < 黄线** = 牛绳断了，反弹是逃命，无条件清仓。

### 六步闭环 SOP

| 步骤 | 内容 | 判定 |
|------|------|------|
| 1 | 择时 | 白线 > 黄线？否 → 空仓等待 |
| 2 | 选股 | N 型上移结构 |
| 3 | 等 B1 | J ≤ 12 + 缩量 + MACD 未否决 |
| 4 | 设止损 | 入场价 × 93% |
| 5 | 卤煮止盈 | 站上白线 + 2 阳 → 减半仓 |
| 6 | 白线破位 | 连续 2 日跌破 → 清仓 |

### 入场条件

**基础版（仅 B1 信号）**

| 条件 | 说明 | 阈值 |
|------|------|------|
| KDJ J 值 | 超卖区域，最好负值 | ≤ 12 |
| 缩量回调 | 当日量 < 前日量 × 阈值 | < 0.8 |
| N 型上移 | 近期底部不断抬高 | higher lows |
| 白线 > 黄线 | 主力牵牛中 | 趋势过滤 |
| MACD | 非顶背离/死叉多 | 一票否决 |

**B2 确认（多策略共振）**

`zt backtest b2-confirm` 实现 B1 观察 + B2 确认 + 次日开盘回测。B1 出现后若近 5-15 日出现放量长阳 ≥ 4%、量 > 1.5 倍，视为趋势确认。

### 出场三重保护

| 出场类型 | 触发条件 | 操作 | 说明 |
|----------|----------|------|------|
| **止损** | 收盘价 < 入场价 × 93% | 清仓 | 看收盘价，不看盘中 |
| **卤煮止盈** | 站上白线 + 连续 2 阳 + 量不萎缩 | 减半仓 | 保护利润 |
| **白线破位** | 收盘价连续 2 日跌破白线 | 清仓 | 趋势结束 |
| **紧急离场** | 白线死叉黄线 | 无条件清仓 | "牛绳断了" |

### 默认参数

```python
LoopConfig(
    j_threshold = 12,            # B1 J 值阈值
    stop_loss_pct = -0.07,       # 止损 -7%
    bbi_break_days = 2,          # 白线两日破位
    bbi_break_threshold = 0.01,  # 跌破阈值 1%
    min_holding_days = 3,        # 最少持仓 3 天
    lu_half = True,              # 卤煮减半仓
    position_pct = 0.3,          # 单笔仓位 30%
    vol_shrink_threshold = 0.8,  # 缩量阈值
)
```

### 回测效果（中国平安 601318.SH，500 天）

| 版本 | 交易笔数 | 胜率 | 收益 | 夏普 |
|------|---------|------|------|------|
| 基础版 | 8 | 25% | +40.74% | 1.95 |
| B2 确认 | 1 | 100% | +0.03% | — |

> 胜率从 25% 提升到 100%，代价是交易次数从 8 笔降到 1 笔。多策略共振过滤掉了 7 笔低质量交易。**样本量小，请勿据此推断未来收益。**

```bash
# 基础版六步回测
zt backtest shaofu 601318.SH --days 500

# B1 观察 + B2 确认
zt backtest b2-confirm 601318.SH --days 500
```

### 统计检验

策略是否有效不能只看回测收益。项目内置统计检验框架：

| 指标 | 门槛 |
|------|------|
| 夏普 t 检验 p-value | < 0.05 |
| Bootstrap CI 下界 | > 0.3 |
| 胜率 | > 40%（高盈亏比可降至 25%） |
| 盈亏比 | > 1.5 |
| 最大回撤 | < 25% |

统计检验的**底层能力**（`modules/statistics/`：夏普 t 检验、蒙特卡洛置换检验、子区间分析）仍在，可直接调用：

```python
from modules.statistics import sharpe_t_test, monte_carlo_permutation_test

p_value = sharpe_t_test(sharpe_ratio, n_periods)
```

> ⚠️ **该框架尚未接入验收链路**：v4.6.0 起，统计检验与 v1.0 验收（`zt verify v1.0`）是两条独立的路径——验收用的是五项硬指标（Sharpe / Calmar / WinRate / MaxDD / OOS-IS），不含统计检验。历史上的 `backtest_shaofu_with_validation` 入口因零调用方已删除。设计稿见 [docs/STATISTICS_VALIDATION.md](docs/STATISTICS_VALIDATION.md)。

详见 [docs/STATISTICS_VALIDATION.md](docs/STATISTICS_VALIDATION.md)。

---

## 安装

```bash
git clone https://github.com/lululu811/zettaranc-skill.git
cd zettaranc-skill

# 运行时依赖
pip install -r requirements.txt
pip install -e .

# 如需跑测试 / 开发，再装开发依赖（pytest 等）
pip install -e ".[dev]"
```

> 安装后注册三个命令：`zt`（CLI 主入口）、`zt-web`（FastAPI 后端）、`zt-monitor`（自选股主动监控）。不装包也可直接 `python -m modules.cli` 调用。

### 接入真实行情

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
> - **数据模式**：`DATA_MODE=jnb` 配置 Tushare 数据最全；未配置时自动走 a-stock-data 免费源；`DATA_MODE=websearch` 可留空。
> - **Token 获取**：前往 [Tushare 官网](https://tushare.pro/user/token) 注册。
> - **可选加速**：配置 `HITHINK_FINANCE_API_KEY`（同花顺官方）或 `INDEVS_API_KEY` 会自动提升数据源优先级。
> - **LLM 配置**：可选。配置 `LLM_API_KEY` 后启用 LLM 对话及点评；未配置则仅输出命令行分析。
> - **完整环境变量说明**：[docs/CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md)

---

## CLI 工具

16 个顶层子命令，全部支持 `--json`：

```bash
zt analyze 600487.SH --json                  # 股票分析（指标 + 战法 + 信号）
zt screen --strategy B1 --limit 20 --json    # 批量选股
zt score 600487.SH                            # 单股综合评分
zt market timing --json                       # 市场择时指标
zt workflow                                   # 每日五步工作流（等价 daily）
zt diagnose 600487.SH --json                 # 持仓诊断
zt watchlist add 600487.SH                    # 自选股：add/remove/list/scan/report
zt sync status                                # 数据同步状态
zt backtest shaofu 600487.SH --days 250 --json  # 少妇战法回测
zt backtest b2-confirm 600487.SH --json      # B1观察+B2确认回测
zt simulate 000001.SZ --days 250 --capital 100000 --json   # 端到端模拟
zt verify v1.0 --limit 50 --days 300 --walk-forward        # v1.0 五硬指标验收
zt trade add "口语化交易描述"                  # 记录交易
zt self-optimize run --target trading --rounds 3           # Darwin 自优化
zt monitor --json                             # 自选股主动监控
zt track --status active --json               # 跟踪池管理
```

### 选股策略别名

`--strategy` 支持 16 个别名（13 个唯一条件，`牵牛/牛绳`、`沙漏/沙漏评分` 为同义）：

`B1` `B2` `B3` `完美图形` `超级B1` `长安战法` `建仓波` `吸筹` `安全` `超跌` `突破` `牵牛` `牛绳` `沙漏` `沙漏评分` `量比战法`

完整参数说明见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)。

---

## Web 看板（可选）

```bash
pip install fastapi uvicorn pydantic-settings   # API 依赖不在 requirements.txt
zt-web                                         # 后端 http://localhost:8000
cd frontend && npm install && npm run dev      # 前端 http://localhost:5173，/api 代理到 8000
```

---

## 文档导航

| 我想知道… | 去看 |
|---|---|
| 怎么用 CLI / 安装依赖 / 第一次运行 | 本文 + [USER_GUIDE.md](docs/USER_GUIDE.md) |
| 怎么配置环境变量、数据源 key | [CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md) |
| 想参与开发 / 提 PR / 写新指标 | [CONTRIBUTING.md](docs/CONTRIBUTING.md) |
| 哪个版本改了什么 | [CHANGELOG.md](docs/CHANGELOG.md) |
| 完整文档索引 | [INDEX.md](docs/INDEX.md) |
| AI Agent 角色协议 | [SKILL.md](SKILL.md) |
| 交易体系知识库（29 篇） | [knowledge/](knowledge/) |

> ⚠️ **免责声明**：本项目仅供学习研究使用，不构成投资建议。据此操作，风险自负。

## 许可证

[MIT](LICENSE) · 语料基于公开直播/付费课整理蒸馏
