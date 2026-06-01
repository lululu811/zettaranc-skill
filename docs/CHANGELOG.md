# 更新日志

所有值得记录的变更都会写在这里。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [v2.10.0-rc.1] - 2026-06-02

> **「性能地基 → 质量地基：3 个必修 CLI bug 修复、6 业务脚本薄壳化（3623→203 行）、zt 统一入口、5 个 CI job、pre-commit 护栏。」**

### P0 必修（4 项 · 1-2 天）

- **修 3 个必修 CLI bug**：`cmd_screen` 必崩（StockScore 字段错位）+ `cmd_watchlist scan` 静默零结果（`stocks`→`alerts` key 名不匹配）+ 11 种 strategy 中文别名映射到 screener 英文 criteria（STRATEGY_ALIAS）
- **CI lint 真起作用**：删 `.github/workflows/test.yml` 的 `|| true` 装饰品，加 `ruff format --check`；`pyproject.toml` 追加 `[tool.ruff]` 块（F/E/W/UP，line-length=120）
- **死代码清零 + NameError 修复 + 硬编码路径清零**：`git rm scripts/sync_db_test.py`（自 4/30 起 100% 失败）；修 `scripts/sync_and_compute.py:25` `NameError`（`with open(...) as f:` 缺 `stocks = json.load(f)`）；4 个脚本硬编码 `/Users/chenlei/.../stocks_final.json` 改 `STOCKS_JSON` env + 默认 `data/stocks_final.json` 相对路径；`scripts/fetch_tushare_data.py` 加 DEPRECATED 头（指向 `python -m modules.data_sync`）
- **SKILL.md 质量门接 CI**：`corpus/quality_check.py` 加 `--json` / `--strict` flag，CI 新增 `quality-gate` job（`continue-on-error: true` 观察期）

### P1 重构（4 项 · 3-5 天）

- **6 业务脚本薄壳化（3623 → 203 行，-94%）**：`sync_watchlist.py` / `sync_and_compute.py` / `batch_compute_indicators.py` / `generate_report.py` 全部改写为 < 60 行薄壳；`DataSyncer` 新增 `sync_missing()` + `sync_daily_and_compute()` 业务逻辑接收方；`modules/report.py` 新增（`assess_watchlist` + `render_assessment` + `write_assessment`）；删 ~600 行 `compute_ma/ema/kdj/rsi/boll/macd` 重复实现
- **合并 5 个独立 main() 到 zt 统一入口**：`modules/cli.py` 用 argparse subparser 收 7 个顶层命令（analyze/screen/score/workflow/diagnose/watchlist/sync）+ 9 个子动作（watchlist 5 + sync 4）
- **6 语料脚本迁 `corpus/`**：`batch_download_bilibili.py` / `batch_transcribe.py` / `srt_to_transcript.py` / `merge_research.py` / `quality_check.py` / `download_subtitles.sh` 从 `scripts/` 移到 `corpus/`；`AGENTS.md` + `.github/workflows/test.yml` 引用同步更新；`pyproject.toml` exclude 加 `corpus*`
- **限流升级 multiprocessing 安全**：`modules/data_sync.py` 新增模块级 `_RateLimiter`（multiprocessing.Lock + 60s 滑动窗口 token bucket）；`TUSHARE_RPM` env var 覆盖（默认 180）

### P2 加值（2 项 · 1-2 天）

- **CI 真实数据回归**：`tests/test_indicators_realdata.py`（600519.SH × MACD/KDJ/RSI vs Tushare `stk_factor` 官方值，skipif 无 token 跳过）；`.github/workflows/test.yml` 新增 `e2e-realdata` job（仅在配置 TUSHARE_TOKEN secret 时跑，`continue-on-error: true` 观察期）；新建 `.github/workflows/e2e-cron.yml`（每周一 02:00 UTC 跑）
- **pre-commit 钩子**：`.pre-commit-config.yaml` 配 ruff（lint + format）+ mypy（限于关键模块）+ SKILL.md 质量门 + 标准文件检查；CI 新增 `pre-commit` job

### 测试

- **+103 个 pytest 用例**（264 → **367 passed, 10 skipped**）
- 5 个新测试文件：`tests/test_cli_screen.py` / `tests/test_cli_subparser.py` / `tests/test_data_sync_extensions.py` / `tests/test_rate_limiter.py` / `tests/test_indicators_realdata.py` / `tests/test_quality_check.py`

### 风险与回退

- lint / quality-gate / e2e-realdata / pre-commit 4 个 CI job 均 `continue-on-error: true`（v2.10.0 观察期，不阻塞 PR）；v2.11.0 计划改为 required
- 限流仅同机多进程有效，跨机器需 Redis 协调
- 自研 vs Tushare 指标 diff 阈值 5%（观察期），v2.11.0 收紧到 2%
- `corpus/quality_check.py` 替代 `scripts/quality_check.py`（破坏性变更，旧调用方需更新）

### 下一迭代（v2.11.0 候选）

- 删 `|| true` + ruff 失败时阻塞 PR
- 限流跨机器 Redis 化
- 真实数据 diff 阈值收紧到 2%
- SKILL.md 32K 字拆 6 心智模型 + 30 启发式（推迟）
- 活跃市值 +4%/-2.3% 量化层（line C）
- 少妇战法六步端到端回测（line B / v3.0.0 候选）

---

## [v2.9.0] - 2026-05-31

> **「性能与架构极限优化：60x计算提速、多线程网络I/O、MDC 2.0 智能评分、大型模块解耦。」**

### 极致性能优化

- **指标计算向量化 (60x提速)**：移除了 `core.py` 中所有的 O(N) Python 循环，利用 Pandas 原生向量化重写了 `MACD`、`KDJ` 和 `BBI` 的预计算逻辑，计算速度提升约 60 倍，同时确保计算精度与通达信 (TongDaXin) 百分百一致。
- **SQLite 数据写入加速 (10x-50x提速)**：移除了 `data_sync.py` 中的 `iterrows()` 单行插入，重构为 `to_sql()` 及 `executemany()` 批量插入。
- **并发多线程数据拉取**：为所有的全市场批量数据同步 (`sync_all_daily_kline`, `sync_all_indicators`, `sync_all_stk_factor`) 引入 `concurrent.futures.ThreadPoolExecutor` (5 并发)，并搭配线程安全的 API 限流锁，最大化榨干 Tushare 接口网络吞吐率。
- **并发环境数据库优化**：开启了 SQLite 的 `WAL` (Write-Ahead Logging) 模式与 `NORMAL` 同步机制，彻底解决并发场景下的 `Database is locked` 问题。

### 策略智能升级 (MDC 2.0)

- **多维验证 (MDC) 体系落地**：在基础逻辑上增加了资金流、布林带、DMI 动能的加分/权重机制。
- **麒麟阶段背景校验 (Contextual Validation)**：信号检测现在具备“时局观”。B1/B2 信号会根据当前是否处于“吸筹”、“拉升”或“派发”阶段动态调整置信度，有效过滤高位诱多信号。
- **资金流深度对齐**：S1 逃顶、长安战法等现在会自动校验主力大单净流入/流出比例，识别真实的机构意图。
- **DMI 趋势过滤**：引入 ADX 高位动能竭尽（冰点确认）与 DI 趋势金叉验证，显著提升买点胜率。

### 架构解耦重构

- **重构巨型 `strategies.py` 模块**：将原先近 1700 行的超大文件彻底解耦，升级为标准的 Python Package (`modules/strategies/`)。
- **职责分离**：将业务逻辑精准下沉到 `core.py` (核心枚举/基础模型), `base_strategies.py` (基础战法 B1/B2/B3等), `compound_strategies.py` (复合图形), `sell_signals.py` (逃顶防卖飞) 和 `kirin.py` (麒麟会模型)。
- **向后兼容性**：保留了模块的 API 暴露方式 (`__init__.py`)，使得所有外部调用和单元测试 (264个用例) 依然 100% 通过无缝衔接。

---

## [v2.7.0] - 2026-05-30

> **「真实数据充实：财报/PE/PB/PS/资金流全量入库，SAT/UAT 测试体系落地，使用手册交付。」**

### 数据层充实
- **真实财务数据入库**：`financial_data` 表从空数据 → 2,733 条真实记录，覆盖 53 只股票
  - 多接口组合：`fina_indicator`（财务比率）+ `income`（营收/净利）+ `balancesheet`（总资产/负债/权益）+ `daily_basic`（PE/PB/PS）
  - 日期范围：2012Q2 ~ 2026Q1，PE 覆盖率 88.9%，PB/PS 覆盖率 >97%
  - 示例：平安银行 2026Q1 营收 352.77 亿，净利 145.23 亿，PE=5.0
- **资金流向全量入库**：`moneyflow` 表 207,361 条，覆盖 60 天全市场数据
- **指标缓存打通**：`indicator_cache` 表 6,360 条，53 只股票 × 120 天
- **Tushare 官方指标**：`tushare_indicator_cache` 表 12,554 条，用于 diff 验证

### Bug 修复

- **`strategies.py` DB 路径不一致**：`_resolve_db_path()` 使用 `Path(__file__).parent`（指向 modules/），导致战法识别报 "no such table: daily_kline"，已改为 `Path(__file__).parent.parent`（指向项目根目录），与 `database.py` 保持一致

### 测试体系

- **SAT 阶段（系统接受测试）**：数据管线验证——真实 Tushare 数据同步 → 60+ 指标计算 → 30+ 战法识别 → 选股评分，全部通过
- **UAT 阶段（用户接受测试）**：端到端 CLI 场景验证——analyze/screen/diagnose 全链路跑通
- **编写 `run_sat_uat.py`**：可复用的真实数据测试脚本，支持增量同步场景

### 文档交付

- **`docs/USER_GUIDE.md`**：完整使用手册与操作手册，约 3 万字，20 个章节
  - 快速开始 / 环境配置 / 数据库初始化 / 数据同步
  - 六大核心功能详细操作手册（CLI + Python API）
  - Python API 8 种场景代码示例
  - SKILL.md 角色扮演使用指南
  - 日常操作流程（每日/每周/每月维护清单）
  - 常见问题 Q&A（10+ 条）
  - 数据库结构说明（8 张表完整字段）
  - 技术指标体系速查（60+ 指标）
  - 战法体系速查（买入 10 种/卖出 6 种/趋势 4 种）

### README / 文档更新

- README 全面重写：新增数据规模表、7 种选股策略、完整 Python API 示例、引用使用手册
- 版本路线图更新：v2.7.0 主题、数据库充实记录

---

## [v2.5.0] - 2026-05-29

> **「工程化补完：打包、架构清理、Bug修复。」**

### 工程架构

- **新增 `pyproject.toml`**：定义 `pip install -e .` 可安装为本地包，版本 2.4.0，Python >= 3.10
- **新增 `zt` 命令**：`console_scripts` 入口，安装后直接用 `zt analyze 600487.SH`，无需 `python -m modules.cli`
- **统一 dotenv 加载**：所有模块的 `.env` 重复加载改为 `modules/__init__.py` 包级别一次性加载（`override=True` 保留原始行为），17 处重复加载全部移除
- **移除 try/except 兼容分支**：`data_layer.py`、`backtest.py`、`watchlist.py`、`portfolio_diagnosis.py`、`data_sync.py` 五个文件的裸模块导入兼容代码全部删除
- **补漏 `requirements.txt`**：补加 `pandas>=2.0.0` 和 `requests>=2.28.0`（实际使用但未列入）
- **更新 `AGENTS.md`**：Python 模块规范章节更新，说明包安装方式和 dotenv 统一加载策略

### Bug 修复

- **`SKILL.md` 硬编码路径**：`F:/001_AI/skills/zettaranc-skill/.env` 改为跨平台相对路径 `.env`
- **`cli.py cmd_analyze` 运行时崩溃**：`klines` 变量未定义（`analyze_stock` 返回 `IndicatorResult` 而非 klines 列表），修复为单独调 `get_kline_data`，同时将 `args.days` 统一为 `days` 局部变量

### 测试

- 全部测试通过：261 passed, 1 skipped, 0 failures（0.92s）



> **「从修复到补完，从单点到体系。」**

### 核心指标递推修复

- **砖形图递推逻辑修复**：`calculate_brick_value` 从独立切片改为递推 SMA 序列，与通达信一致
- **MACD 递推优化**：`calculate_macd` 复用 `precompute_macd_sequence`，O(n²) → O(n)
- **RSI 递推修复**：从简单平均改为递推 SMA，与 Tushare diff 一致
- **数据源统一前复权**：`daily` → `pro_bar(adj='qfq')`，覆盖 4 个文件

### Tushare 指标对比验证

- **新增 `tushare_indicator_cache` 表**：16 个字段存储 Tushare 官方指标值
- **新增 `modules/data_sync.py stk-factor` CLI**：`python -m modules.data_sync stk-factor --ts_code 600487.SH --days 365`
- **数据一致性验证**：通过 diff 发现 RSI 偏差并修复

### P0 指标补全（高价值 + 实现简单）

- **滴滴战法** — 高位连续两根阴线下台阶，绕过防卖飞直接清仓
- **MACD 金叉空 / 死叉多** — 眼看金叉/死叉即将形成，白线突然拐头，陷阱识别
- **祖冲之法** — 目标价 = 2a - b（a=近期高点, b=近期低点）

### P1 指标补全（高价值 + 实现中等）

- **主力出货五式精细识别** — 加速天量大阴 / 次高点巨量长阴 / 阶梯放量下跌 / 双头双放量 / 绿肥红瘦
- **灾后重建** — 放量金叉后缩量回踩黄线，震仓后的最佳买点
- **跃跃欲试** — 横盘期间放巨大量，红长绿短，至少三次后突破概率大
- **关键 K 识别** — 六种趋势转换的关键 K（下跌→上涨、横盘→上涨、上涨→下跌等）

### P2 核心模块（高价值 + 实现较难）

- **三波理论识别**（`modules/indicators/wave_theory.py`）
  - 建仓波（25-50% 涨幅，无涨停）→ B1 可干
  - 拉升波（>50% 或快速脱离，有涨停）→ 等回调
  - 冲刺波（>100%，频繁涨停）→ 不看
  - 评分制判定，输出置信度 + B1 建议
- **麒麟会四阶段识别**（`modules/indicators/kirin_detector.py`）
  - 吸筹 / 拉升 / 派发 / 回落 四阶段状态机
  - 子类型判断：铁蝴蝶（传统庄）vs 学院派铁蝴蝶（机构）
  - 评分制：每个阶段 0-100 分，综合量价 + 形态 + 双线指标
- **活跃市值择时** — ⏸️ 搁置（指南针专有指标，Tushare 无对应接口）

### 策略体系集成

- **`modules/strategies.py`** — `detect_all_strategies()` 自动输出三波/麒麟会信号
- **`modules/screener.py`** — 评分加权调整 + 新增选股条件：`建仓波` / `吸筹` / `安全`
- **`modules/cli.py`** — `analyze` 输出主力阶段板块，`screen` 支持新策略选项

### 文档

- **`docs/v2.6.0-p2-integration.md`** — P2 模块集成文档（API 用法 / 评分逻辑 / CLI 示例）

### 测试

- 新增 `tests/test_wave_theory.py`（12 个用例）
- 新增 `tests/test_kirin_detector.py`（15 个用例）
- **全量回归测试**：261 passed, 1 skipped

---

## [v2.4.0] - 2026-05-28

> **「拆分到原子，组合成系统。」**

### 架构重构

- **`modules/indicators.py` → `modules/indicators/` 包（4 子模块）**
  - `core.py` — 基础类型 + 数学工具 + 核心指标（MA/EMA/KDJ/MACD/BBI/RSI/WR/布林带/量比/DMI）
  - `price_patterns.py` — 价格形态（双线/单针/砖型图/B1/B2/B3/图形识别）
  - `volume_patterns.py` — 量价信号（卖出评分/交易信号/量比异动）
  - `data_layer.py` — 数据接入（get_kline_data/analyze_stock/缓存层/可视化）
  - `__init__.py` 兼容层保持外部导入不变

### 新增模块

- **`modules/backtest.py`** — 策略组合回测框架：
  - `backtest_multi_strategy()` 单股票多策略融合，支持 `position_pct` 仓位控制
  - `backtest_portfolio()` 多股票组合回测，支持 `max_weight` 单股上限
  - `PortfolioBacktestResult` 含资金曲线、夏普比率、年化收益、最大回撤
  - `Position` 持仓记录（A股 100 股为 1 手）
- **`modules/cli.py`** — 命令行工具：
  - `python -m modules.cli analyze <ts_code>` 股票分析
  - `python -m modules.cli backtest <ts_code> --strategy b1` 单策略回测
  - `python -m modules.cli backtest <ts_code> --strategy all` 多策略组合回测
  - `python -m modules.cli watchlist` 观察池管理
  - `python -m modules.cli screener` 选股扫描

### 性能优化

- **`modules/strategies.py` `detect_all_strategies()` 26x 加速**
  - 原 800ms → 31ms（600487.SH 60 日数据）
  - 预计算指标序列避免 O(n²) 重复计算
  - 提前返回 + 缓存复用

### 数据层增强

- **指标缓存层打通**：
  - `data_sync.py` 新增 `sync_indicator_cache()` / `sync_all_indicators()`
  - `indicator_cache` 表存储 60+ 字段每日快照（KDJ/MACD/BBI/MA/RSI/WR/布林带/双线/砖形图/DMI/量比/信号）
  - `get_kline_data()` 优先读缓存，未命中回退到 `daily_kline`
- **`modules/data_sync.py`** — 增量更新优化、跳过已同步股票、2 天同步间隔保护
- **`modules/tushare_client.py`** — 移除 URL 硬编码，严格从 `.env` 读取

### Bug 修复

- `modules/cli.py` `watchlist` 命令修复：使用函数导入替代不存在的 `Watchlist` 类

### 测试

- **全量回归测试**：213 passed, 1 skipped

---

## [v2.3.0] - 2026-05-28

> **「框架的完备不是终点，落地执行才是。」**

### 量化引擎补完

- **`modules/trade_manager.py`** — 修复 3 个运行时错误（`get_indicator_data` / `get_stock_info` / `match_strategy`）
- **`modules/strategies.py`** — 补完 3 个未实现战法：
  - **平行重炮**（PINGHANG）：两根放量阳线夹阴线，第 2 根量能 ≥ 第 1 根 90%
  - **坑里起好货**（KENGQI）：放量挖坑 → 缩量填坑 → 回到坑沿 = 最后震仓
  - **对称 VA**（DUIchen）：时间对称 + 空间对称检测，识别"不守恒"突破点
- **新增 S1/S2/S3 逃顶检测**：
  - S1：流畅上涨后出现丑陋大绿帽（放量阴线 + 收盘接近低点）
  - S2：股价挑战前高但 MACD 顶背离（价格新高 + DIF 未新高）
  - S3：S1 后反弹至下沿但量能不足，最后逃生窗口
- **新增麒麟会四阶段分析**（`analyze_kirin_phase`）：吸筹 / 拉升 / 派发 / 回落

### 交互功能扩展

- **新建 `modules/portfolio_diagnosis.py`** — 持股检查端到端模块：
  - 当前状态扫描（BBI/白线/黄线位置、KDJ、MACD 状态）
  - 防卖飞评分调用（V1.4）
  - 出货信号扫描（S1/S2/S3）
  - 战法匹配（B1/B2/B3/SB1 可买区间）
  - 止损/止盈位提示
  - CLI 入口：`python -m modules.portfolio_diagnosis 000001.SZ`
- **新建 `modules/watchlist.py`** — 自选股观察池：
  - `add_watch` / `remove_watch` / `list_watch`
  - `scan_watchlist`：批量扫描 B1/B2 信号、破位预警、异动检测
  - `generate_daily_report`：每日观察报告自动生成
  - CLI 入口：`python -m modules.watchlist add 000001.SZ --tags 波段`
- **`modules/screener.py` 选股增强**：
  - 解除 50 只限制，默认 500 只性能保护，支持 `--max-stocks 0` 全量扫描
  - 新增选股策略：`super_b1` / `changan` / `b2_breakout` / `b3_consensus`
- **`modules/database.py`** — 新增 `watchlist` 表（自选股持久化）

### 内容补完

- **`knowledge/breathing-theory.md`** — 呼吸理论：吸气/呼气/屏息、呼吸紊乱识别、与四块砖法则的关系
- **`knowledge/three-best-principles.md`** — 三最原则详细展开：只选最美/只干最强/只拿最硬、权重分配
- **`knowledge/iron-butterfly.md`** — 铁蝴蝶形态：麒麟会四阶段、学院派铁蝴蝶 vs 狗庄、与筹码理论结合
- **`knowledge/four-rhythms.md`** — 四大核心节奏：建仓/拉升/洗盘/出货的节奏切换信号
- **`knowledge/six-tracks-2026.md`** — 2026 六大赛道逻辑重构：创新药/AI 算力/新能源/高端制造/消费升级/周期资源
- **`SKILL.md`** — 版本信息更新（6 个心智模型 / 30 条启发式）、新增 5 篇知识文档引用

### 测试

- 新增 `tests/test_trade_manager.py`（5 个用例）
- 新增 `tests/test_portfolio_diagnosis.py`（10 个用例）
- 新增 `tests/test_watchlist.py`（4 个用例）
- `tests/test_strategies.py` 扩展：平行重炮、坑里起好货、对称VA、S1、麒麟会阶段
- **全量回归测试**：184 passed, 1 skipped

---

## [v2.2.0] - 2026-05-23

> **「知识的增量不是加法，是乘法——每新增一个概念，都可能重构整个体系。」**

### 新增语料

- **15 篇 2026.4-5 月付费课文章**（`references/sources/`）
  - 480-482、490-491：交易战法核心（B1 筛选、防守体系、产业资本视角）
  - 492-493、495：交易战法体系专项考试（B1 / 砖型图 / 单针下 30）
  - 520-521：人生四个圈框架（体能/技术/心理/运气）
  - 531-532：大国博弈与产业链安全感
  - 541-542：城市选择与发展潜力
- **5 份新增调研报告**（`references/research/`）
  - `07-xiaocainiao-new.md`：知行小菜鸟 118 篇新增知识提取
  - `08-dafuweng-new.md`：大富翁小菜鸟 36 篇精读提取（四分之三阴量、异动地量等）
  - `09-tangoo-new.md`：TANGOO 公众号 62 篇提取（超级 B1、娜娜图形）
  - `10-fupan-new.md`：复盘专用z 49 篇提取（双线战法、B2/B3 完整体系）
  - `11-kedebiao-new.md`：知行课代表 53 篇提取（白黄线代码、十张完美图形）

### 知识库更新

| 文件 | 新增内容 | 来源 |
|------|---------|------|
| `trading-core.md` | B1 入场三问、蜈蚣图识别 | 490、491 加餐 |
| `trading-psychology.md` | 翻倍与腰斩防守意识、人生四个圈 | 482、520 加餐 |
| `portfolio-management.md` | 三换三滚动策略 | 481 加餐 |
| `market-macro.md` | 产业资本视角、大国博弈与产业链 | 480、531 加餐 |

### 新增测试

- **`tests/test_exam_rules.py`** — 交易战法考试规则验证（25 个测试用例）
  - B1 核心规则：有瑕疵不做、呼吸判断、黄线距离、压力判断等
  - 砖型图判定：阳包阴干、底部放量干、陷阱不干等
  - 单针规则：时间周期、左侧/右侧、支撑验证
  - 评分标准：各模块分值、总分 100、及格 60、2 秒判断
  - 核心原则：优中选优、不做不亏、无后见之明、独立判断

### 文档更新

- **README.md**：版本号 v2.1.0 → v2.2.0，语料统计更新，知识模块列表更新

---

## [v2.1.1] - 2026-05-11

> **「数据是交易的起点，接口是数据的钥匙。」**

### 安全修复

- **移除 Tushare URL 硬编码**：`tsy.xiaodefa.cn` 等内部域名不再硬编码在代码中
  - `modules/tushare_client.py`
  - `modules/data_sync.py`
  - `scripts/sync_db_test.py`
  - 改为从环境变量 `TUSHARE_API_URL` / `TUSHARE_VERIFY_TOKEN_URL` 读取
  - `.env.example` 同步更新，默认值为空（使用官方地址）

### 新增工具

- **`scripts/fetch_tushare_data.py`** — Tushare Pro 高权限数据抓取脚本
  - 支持 15000 积分高权限接口（12000+ 接口）
  - 按权限分类：基础接口（5000积分）、高级接口（12000积分）、实时数据
  - 默认保存到 SQLite 数据库（`--save-db`），支持 `--no-save` 仅查看
  - 支持命令行参数：`stock_basic`, `daily`, `moneyflow`, `limit_list`, `top_list`, `fina_indicator`, `dividend`, `daily_hsgt`, `index_daily`, `realtime_quote` 等
  - 集成限流控制（120次/分钟）

### 文档更新

- **README.md 新增「必需数据与 Tushare 接口对照」**
  - 完整列出所有依赖的 Tushare 接口
  - 按权限等级分类（5000积分 / 12000积分 / 实时数据）
  - 提供数据抓取命令示例

---

## [v2.1.0] - 2026-04-29

> **「复盘是散户最重要的功课，随堂测试不会骗人。」**

### 重大更新

**随堂测试复盘模块**：用户可以提交交易记录，Z哥根据战法进行点评。

- 支持口语化输入（"4月25号买了100股茅台，1800块"）
- 自动识别买点/卖点
- 匹配战法（B1/B2/B3/长安战法/娜娜图形等）
- 询问是卤煮（落袋为安）还是止损/卖飞

### 架构重构：Python 数据层 + LLM 点评层

**问题**：之前的代码模板生成的点评太"AI味"，没有Z哥的灵魂。

**解决**：Python 只做数据准备，点评由 LLM 用 Z哥角色生成。

```
Python层（数据准备）              LLM层（点评）
┌────────────────────┐           ┌──────────────────────┐
│ TradeReviewer      │           │ Z哥角色点评           │
│ ReviewContext      │ ────────→ │ (SKILL.md 描述角色)   │
│ get_full_prompt()  │           │                      │
└────────────────────┘           └──────────────────────┘
```

### 新增 Python 模块（3 个）

| 模块 | 说明 |
|------|------|
| `trade_parser.py` | 随堂测试解析器（口语化/JSON/CSV 多格式支持） |
| `trade_manager.py` | 交易记录 CRUD、持仓计算、盈亏统计 |
| `trade_reviewer.py` | 数据准备层（ReviewContext、LLM提示词生成） |

### 数据库变更

- 新增 `trade_records` 表：存储交易记录（代码/日期/方向/价格/数量/金额/原因/战法/点评）

### 点评话术重构

`zettaranc_voice.py` 重构为：
- Z哥语料库（概率/纪律/风险等模式）
- 黑话词典（卤煮/建仓/卖飞/B1/B2/S1/S2等）
- 弃用模板化点评（由LLM生成）

### SKILL.md 更新

- 随堂测试复盘模块描述（触发词、分析流程、对话示例）
- JNB 模式个股分析也改用此架构（Python数据 + LLM点评）
- LLM 角色提示词（风格要求、点评维度、黑话列表）

### 触发词

- "复盘"、"交作业"、"检查这笔操作"
- "分析随堂测试"、"点评我的交易"
- "我今天买了一只票"、"我卖了XX"

---

## [v2.0-JNB] - 2026-04-28

> **「你用假数据练出来的全是花架子，上了市场就是被割的命。」**

### 重大发布

**v2.0-JNB**：zettaranc 从纯 LLM 文字对话升级为**具备真实数据查询能力的 Agent**。接入 Tushare API 实时行情、K线、资金流向、财务数据，让 Z 哥的思维框架跑在真实数据之上。

曼城阵容 10 只重点股（茅台/平安/万科/宁德/隆基/比亚迪/招行/五粮液/中国平安/海康威视）317 天 K 线 + 120 天技术指标已全部入库。

### 新增 Python 模块（8 个）

| 模块 | 说明 |
|------|------|
| `tushare_client.py` | Tushare 中转 API 封装（120次/分钟限流，tsy.xiaodefa.cn） |
| `database.py` | SQLite 数据库管理（7 张表，context manager 事务） |
| `data_sync.py` | 数据同步器（增量/全量，K线/指标/资金流向） |
| `indicators.py` | 技术指标计算引擎（60+ 指标：MACD/KDJ/RSI/WR/布林带/DMI/砖形图/双枪/四块砖…） |
| `screener.py` | 选股器（曼城评分体系、趋势评分、量能评分、完美图形识别） |
| `strategies.py` | 30+ 战法识别引擎（B1/B2/B3/SB1、长安战法、四分之三阴量、娜娜图形、异动地量…） |
| `setup_wizard.py` | 初始化配置向导（环境检测、数据模式切换、API 连通性测试） |
| `zettaranc_voice.py` | Z哥话术生成 |

### 新增测试套件（126 个用例）

| 文件 | 覆盖范围 |
|------|---------|
| `test_database.py` | 数据库初始化、连接管理、事务回滚、表增删 |
| `test_indicators.py` | 56 个指标计算测试（MA/EMA/KDJ/MACD/RSI/WR/布林带/砖形图/DMI…） |
| `test_screener.py` | 选股评分、趋势评分、量能评分、完美图形 |
| `test_strategies.py` | 12 个战法识别测试、数据库集成 |
| `test_setup_wizard.py` | 环境变量检测、数据模式切换 |

### 新增数据能力

- 实时行情查询（股价、涨跌幅、量比、市值）
- 日线 K 线数据（支持增量更新）
- 60+ 技术指标实时计算 + SQLite 缓存
- 资金流向数据（大小单净流入）
- 涨停股列表
- 每日指标快照历史（支持回测）
- 曼城阵容预设数据（开箱即用）

### 架构重构

- **模块化拆分**：从单一 `SKILL.md` 拆分为 **12 个独立能力模块** + **8 个 Python 代码模块**
- **数据与逻辑分离**：知识文档迁移至 `knowledge/` 目录
- **测试基础设施**：`tests/conftest.py` 提供临时数据库 fixture、K 线数据工厂
- **配置向导**：`setup_wizard.py` 支持 JNB/websearch 双模式切换

### Bug 修复

- 修复 `data_sync.py` 中 `calculate_sell_score` 返回值类型不匹配（`dict` → `str`）
- 修复 `detect_trade_signal` 返回 `TradeSignal` enum 对象的解包问题
- 修复 `calculate_macd` 返回列表而非单值的 SQL 绑定错误

### 知识文档

- 新增 `knowledge/data_dictionary.md` — 输入数据字典（DailyBar/MoneyFlow/Financial 等）
- 新增 `knowledge/signal_dictionary.md` — 输出信号字典（Agent 解读指南）
- 原有 12 个能力模块 `.md` 文件从 `modules/` 迁移至 `knowledge/`

### 新增依赖

- `tushare` — Tushare API 客户端
- `python-dotenv` — 环境变量管理
- `pandas` — 数据处理
- `pytest` — 测试框架

---

## [未发布] - v2.0.0

### 重大更新
- **Agent 能力升级**：从纯 LLM 升级为具备实时数据查询能力的 Agent
- **Tushare API 集成**：支持实时行情、K线、财务数据、资金流向
- **SQLite 指标缓存**：每日技术指标快照存储，支持历史回测

### 新增模块（5 个）
- **modules/tushare_client.py** — Tushare 中转 API 客户端
- **modules/database.py** — SQLite 数据库管理
- **modules/data_sync.py** — 数据同步器（K线、指标批量同步）
- **modules/indicators.py** — 技术指标计算（MACD/KDJ/RSI/布林带/砖形图等）
- **modules/zettaranc_voice.py** — Z哥话术生成

### 新增数据能力
- 实时行情查询（股价、涨跌幅、量比）
- 日线 K 线数据
- 技术指标实时计算
- 资金流向数据
- 涨停股列表
- 每日指标快照历史

---

## v1.6.0

### 重大更新
- **467 篇原始语料全量解析**：从 29% 覆盖率（136/467）扩展至 **100% 全量解析**，完成 5 个新增语料源的精读提炼
- **模块化架构重构**：从单一 SKILL.md 拆分为 **12 个独立能力模块**，实现可维护、可扩展的知识体系
- **心智模型从 5 个扩展至 6 个**：新增「双线趋势判断」模型
- **决策启发式从 23 条扩展至 30 条**

### 新增模块（6 个）
- **modules/trend-lines.md** — 知行趋势线（双线战法）：
  - 白线（EMA 双重指数平均）+ 黄线（4 参数 BBI 变体）
  - 三道防线：破白线 → 破黄线 → 白线死叉黄线（走错也要走）
  - 五种玩法：金叉回踩 B1 / 死叉离场 / 双线死叉多极限买 / 白黄区间买 / 放量金叉缩量回踩
  - "碗"的概念：白黄之间的区域，碗大=容错率高
  - 牛绳理论：白线在黄线上=主力牵着牛绳（洗盘），白线在黄线下=牛绳断了（反弹）
- **modules/exit-strategies.md** — S1/S2/S3 逃顶体系：
  - S1：流畅上涨后出现丑陋大绿帽（假阴真阳也算），100 亿以下小票直接清仓
  - S2：挑 S1 前高但 MACD 顶背离
  - S3：主力自救反抽到 S1/S2 下沿，最后逃生窗口
  - 摸顶税：浮盈中计提 20%-50% 作为"还给市场"的部分
  - 与防卖飞 V1.4 的边界：假洗盘走防卖飞，真出货走 S1 直接卖
- **modules/key-candles.md** — 关键 K 理论：
  - 6 种趋势转换：V 型反转 / 紧急刹车 / 平地惊雷 / 丢盔弃甲 / A 杀反转 / 一拍拍死
  - 衰竭信号：卖盘枯竭 + 买盘枯竭
  - 主力打明牌的 3 个前提
- **modules/advanced-patterns.md** — 高级战法合集：
  - 长安战法（75% 胜率，全 A 仅约 20 次）
  - 平行重炮/多门重炮（B2 完美图形，干错也要干）
  - 灾后重建（放量金叉后缩量回踩黄线=最后震仓）
  - 跃跃欲试（横盘多次放量红肥绿瘦）
  - 坑里起好货/祖冲之法（目标价=2a-b）
  - 四分之三阴量战法（判断真假突破，成功率 90%+）
  - 异动+地量地价（A 股选股核心逻辑）
  - 对称 VA 战法（多空守恒，只有守恒被破坏才有交易价值）
  - B2/B3 完整体系（量化指标、建仓方式、衰竭点）
  - 超级 B1 / 娜娜图形
- **modules/portfolio-management.md** — 组合配置体系：
  - 新曼城 4231 体系（70% 主配置 + 30% 量化灵动，绿/黄/红三阶段标注）
  - 指数贡献策略（按板块构建组合，选混血标的）
  - ETF 躺平策略（三关筛选：规模>10 亿/纯血/流动性）
  - 开超市规则（满仓=80%，留 20% 现金）
  - 结构化仓位（底仓 60-70% + 动态仓 30-40%）
  - ABC 三阶段建仓 / 3-2-2 阵型 / 235 原则
  - 资金量分级配仓表（10w 到 5000w 的盈利目标匹配）
- **modules/trading-psychology.md** — 交易心理：
  - 交易免疫系统（诺贝尔奖免疫耐受机制类比交易）
  - 斗牛士心法（勇气/决心/技巧 + 三种牛分类）
  - 散户三大魔咒（一买就跌/一卖就涨/买了不涨）
  - 散户必删除 5 种错误思维
  - 少妇钝感力 vs 少女心态
  - 空头思维 / 击穿对手盘 / 屁胡哲学 / 空仓哲学
  - 后厨理论 / 去弱留强 / 知行合一

### 现有模块更新（6 个）
- `trading-core.md`：补充高级战法索引、B2/B3 完整体系（量化指标 + 衰竭点 + 建仓方式）
- `indicators.md`：补充分价关系分类（倍量/天量/长阴短柱）、沙漏量化选股（V1.0→V9）
- `sell-discipline.md`：补充 S1/S2/S3 快速参考、白线死叉黄线规则、B3 止损规则、摸顶税
- `position-management.md`：补充组合配置扩展引用（新曼城 4231、指数贡献、ETF 躺平等）
- `market-macro.md`：补充市场三阶段模型（66% 垃圾时间/24% 舒适区/10% 高波动期）、四年周期理论、慢牛 30° 斜率管理、负反馈监控系统、龙队控盘逻辑
- `stock-glossary.md`：补充 30+ 新黑话（碗/牵牛绳/平行重炮/灾后重建/旋转木马/赛赛图/关键 K/对称等）

### SKILL.md 更新
- 新增模型 6：双线趋势判断（白线在黄线上=主力在场，白线死叉黄线=无条件清仓）
- 决策启发式从 23 条扩展至 30 条（新增双线趋势 5 条、逃顶纪律 4 条、高级战法 6 条、宏观 2 条）
- 所有新模块引用添加到心智模型区
- 最新动态补充：少妇战法升级双线战法、S1/S2/S3 逃顶体系、关键K理论、沙漏V9、新曼城4231、市场三阶段、四年周期、负反馈监控、全量解析 467 篇完成

### 调研文件
- `references/research/07-xiaocainiao-new.md`（知行小菜鸟 118 文件，449 行）
- `references/research/08-dafuweng-new.md`（大富翁小菜鸟 185 文件，769 行）
- `references/research/09-tangoo-new.md`（TANGOO 62 文件，647 行）
- `references/research/10-fupan-new.md`（复盘专用z 49 文件，353 行）
- `references/research/11-kedebiao-new.md`（知行课代表 53 文件）

## [1.5.0] - 2026-04-26

### 重大更新
- **第 5 个语料源接入**：TANGOO 公众号（江苏作者「渣A小学生」，62 篇 2025.6 - 2026.4 直播笔记），语料规模从 345 篇 / ~150 万字扩展至 **~407 篇 / ~170 万字**
- **心智模型 3 扩展**：短线交易系统从 13 子战法扩展到 **17 子战法/工作流**，新增主力出货识别 / 每日工作流 / 滴滴战法精确执行三个独立子节

### 新增
- **3.15 主力出货五种经典方式**（2025-09-18 直播）：
  - 方式一：加速后单日放天量大阴 → 至少卖一半（中材KJ / 镇洋FZ）
  - 方式二：加速后次高点巨量长阴 → 资金盘断裂或对手盘信号（民生Bank / 东财 / 宁德）
  - 方式三：新高之后阶梯放量下跌 → 量能需仔细识别（晋亿SY / 万科）
  - 方式四：双头双放量巨阴 → 中盘股常见（卫宁JK）
  - 方式五：顶部绿肥红瘦 → 与底部红肥绿瘦相反（中色 / 华谊）
  - 4 条总纲：出货 ≠ 见顶 / 盘子越大越综合 / 出货后不看黄白线 / 牛逼的票不让人操心
- **3.16 每日五步工作流**（2025-11 仓位实战直播）：
  - 择时 1 分 → 定策略 2 分 → 复盘 3 分 → 选股 5 分 → 执行 1 秒
  - 松紧手原则：盘中松（不操作）/ 盘后紧（计划）
  - 新黑话：瑜伽裤 = 游资 / 铁蝴蝶 = 麒麟会 / 学院派铁蝴蝶 = 机构
- **3.17 滴滴战法精确执行**（2025-09 直播）：
  - 触发条件：14:55 + 跌破昨低 + 浮盈或浮亏
  - 执行规则：浮盈飞一半 / 浮亏全清
  - 关键纪律：手机定 14:55 闹钟、不在 14:30 提前判断、跌破昨低不是预测是事实
  - 与防卖飞 V1.4 的边界区分
- **3.3 B1 选股双补丁**（2026-02 / 2026-03 升级）：
  - 补丁 1：周线 55 / 144 / 233 多头排列（5000 票筛到 1600 票，过滤走坏的下跌票）
  - 补丁 2：累计换手率 < 38%（华纳 36.12 / 小微 18.31 / 航发 29.58 三大完美图形参照）
- **3.10 防卖飞策略 V1.3 → V1.4 升级**（2025-07-31 直播）：
  - J 死叉是状态不是瞬间（J 在 K 和 D 之下即为死叉）
  - 放量看相对（与近期对比）不看绝对
  - 扣分制打分（价格→成交量→bbi→J→趋势）
  - 持股 ≠ 买入：浮盈持有的赔率远大于当天新开仓
  - 赔率 ≠ 胜率：忍 3 次错 1 次也值
  - 本质 = 把碗变大，接住牛市掉落的金币（牛市多长阴、容错率高）
  - 真出货 vs 假洗盘识别：阳阳 7-23（假洗盘）/ 三人行 7-18（戴绿帽真出货）/ 顶部大风车
- **3.14 资金量分级配仓表**(2025-11-13 仓位实战直播):
  - < 100 万高手 4-5 票 / 新手 10 票 / 500 万 10 票 / 1000 万+ 15-20 票必配 4-5 板块
  - 波段 vs 短线的仓位反差
  - 过度分散三大致命缺陷：收益平庸 / 精力分散 / 下单随意
- **4.2 曼城首发阵容更新**（2025-11-27）：巴巴正式入选首发阵容
- **创新药主题五大三小代号专栏**（2025-06-22 直播）：
  - 行业奇点：三生制药 12.5 亿美元首付款（中国创新药出海最高纪录）
  - BD 四节点炒作模型：蹭概念 → 获得首付款 → 获得里程碑付款 → 销售分成
  - 五大：痛风（一品红 / 康哲）/ 自免（荣昌 / 康诺亚 / 智翔金泰）/ 肺癌（三生制药 / 贝达）/ 麻醉（海思科 / 恩华）/ 胰腺癌（微芯生物）
  - 三小：阿尔茨海默（国药股份）/ 抑郁症（华纳药厂 ZG001）/ 小细胞胰腺癌（泽璟制药 ZG006）
- **黑话词典扩展**：
  - 港股区新增：巴巴 / 美团
  - 新增「操盘术语 / 主力运作」7 项：戴绿帽 / 顶部大风车 / 瑜伽裤 / 铁蝴蝶 / 学院派铁蝴蝶 / 百岁山 / 狗庄

### 改进
- README.md 版本 badge：v1.4.0 → v1.5.0
- 语料统计数字：345 篇 / ~150 万字 → ~407 篇 / ~170 万字
- 模型 3 子战法计数：11 → 17

## [1.4.0] - 2026-04-23

### 重大更新
- **语料规模大幅扩展**：从 191 篇 / 100 万字扩展至 **345 篇 / 约 150 万字**（增量 154 篇约 50 万字，主要来自大富翁小菜鸟 185 篇推文与知行小菜鸟新付费课）
- **时效性更新**：所有市场判断、主题观点更新至 2026 年 4 月最新状态

### 新增
- **MACD 指标之王专题**（2026年4月22日4小时直播）：
  - 零轴多空判断：白线上穿零轴=多头区间，下穿=空头区间
  - 顶背离与底背离：股价创新高但白线未创新高=减仓信号
  - 金叉空/死叉多：期货经典战法
  - **MACD一票否决权**：所有战法都要过MACD这一关
  - 黄线位置交易价值：MACD多头区间股价打到黄线=高性价比买点
- **筹码理论四大法则**：
  - 低位密集：一切行情的起点
  - 锁仓拉升：牛股的核心基因
  - 双峰填谷：行情的中继与变盘信号
  - 高位密集：行情的终局与风险起点
- **仓位铁律整合**（v1.4.1 补落地，原条目改写）：在 SKILL.md 模型 3 新增「3.14 仓位铁律」子节，整合"单票≤10%、总仓≤80%、永留 20%"（2012 产品清盘后定下的铁律）+"牛市玩仓位/熊市玩精准/震荡市只卖不买"+"多大屁股穿多大裤衩"碎片化表述
- **模型 1 十二年一致性补充**（v1.4.1 补落地，原"时间维度演变轨迹"改写）：在 SKILL.md 模型 1 「证据」段后新增三节点表（2014 雪球→2017 股探→2025+ 知行），标注"承认不确定→反讽确定性→用纪律封装不确定"的演化轨迹
- **个股黑话词典完整六分类**（半导体 / 券商 / 新能源 / 消费 / 医药 / 港股，共 30+ 代号）

### 改进
- README.md 版本 badge：v1.3.0 → v1.4.0
- 语料统计数字更新为 345 篇 / 约 150 万字

## [1.3.0] - 2026-04-18

### 重构
- **心智模型从 6 个重组为 5 个**：将原模型 3（交易系统）拆分为：
  - **模型 3：短线交易系统** — 整合 11 个子战法：少妇战法 SOP、四块砖法则、B1/B2/B3 确认、超级 B1、SB1、量比战法、双枪战法、对称 VA 战法、麒麟会/吸拉派落、防卖飞策略 V1.3、三最原则
  - **模型 4：长线配置框架** — 整合 6 个子策略：稀缺性资产、曼城首发阵容、ETF 躺平、海权-商业扩张、开超市策略、筹码思维
- **Agentic Protocol 新增 Step 1.5：多轮问诊系统** — 个股/持仓追问从一句话升级为完整门诊流程：
  - 第一轮三问（周期 + 状态 + 仓位占比）
  - 第二轮按场景分流：持仓诊断 / 买点确认 / 逃命判断 / 长线配置
  - 补充：散户段位判断表格（6 种段位自动识别触发）
  - 每条诊断逻辑都配 Z 哥原话式回应
- **决策启发式从 15 条扩展到 23 条**，按场景分组：短线纪律 9 条、中线管理 6 条、长线与宏观 8 条

### 新增
- **问诊铁律 6 条**：不跳问诊、仓位优先、保守兜底、必给结论、Z 哥节奏、段位识别
- **仓位警报**：用户满仓/梭哈时立即打断，引用 2017 年产品单票上限 10% 的机构纪律
- **信号来源追问**：「你自己分析的还是听别人说的？」— 对应股探报告「看别人抄底成功自己也要试一试」反心理特征
- **上次失败阴影识别**：对应股探报告「上次失败直接影响下次」反心理特征四
- **周期位置判断**：长线问诊新增「你觉得这票现在在周期的什么位置？」— 对应逆向操作模型

### 改进
- 表达 DNA 新增量化词频表（B1:494 次、确定性:103 次等）、死规矩/铁律体、算账句、设问自答句、极端对比句
- 01-writings.md 新增「来源 E：第二轮深度蒸馏新增发现」
- 05-decisions.md 新增 2026 年 4 月决策记录（活跃市值框架、量比战法、防卖飞策略、三最原则、筹码思维）

## [1.2.1] - 2026-04-17

### 改进
- 优化 `SKILL.md` 排版：在证据列表、局限列表、决策启发式、关键引用之间增加空行，提升可读性
- 合并证据引文拆分：将多句话挤在一行的引文拆分为独立条目

## [1.2.0] - 2026-04-17

### 新增
- **增量语料整合**：导入 45 篇「复盘专用z」充电直播文章（2025.7-2026.2），语料总量从 136 篇增至 **191 篇**
- **心智模型 3 大幅扩展**：在「少妇战法 + 四块砖」基础上新增 5 个子模块：
  - **B1/B2/B3 战役确认体系** — 建仓/趋势/加速三层买点，三重保险确认波段
  - **双枪战法** — 两根放量阳柱夹缩量阴线的暴力图形，「箭在弦上，不得不发」
  - **对称 VA 战法** — 走势必对称，交易做「不守恒」，只有守恒被破坏的位置才有交易价值
  - **麒麟会 / 吸拉派落** — 庄的运作四阶段识别（吸→拉→派→落），建仓波 b1 可干、拉升波第一个 b1 不干
  - **ETF 躺平策略** — 仅适用于牛市强趋势，b1 买→波段持有→高切低→爆发减仓
- **决策启发式 10 条 → 15 条**，新增：
  11. 散户必删的 5 种思维
  12. 对称守恒被破坏，才是交易时机
  13. 建仓波 b1 可干，拉升波第一个 b1 不干
  14. 摸顶税：利润要还 20% 给市场
  15. 分歧转一致才买，十六岁杨幂还得再长长
- **表达 DNA 扩充**：新增「吸拉派落」「麒麟会」「对称 VA」「双枪」「不守恒」「摸顶税」「分歧转一致」「箭在弦上」「十六岁杨幂」等高频词汇
- **新增金句引用**：「永不套牢」「完美图形干错也要做」「A股是人情世故，港股美股才是打打杀杀」

### 改进
- 更新语料统计数字：136 篇 → 191 篇，69.6 万字 → 约 100 万字，10 条启发式 → 15 条
- 更新 README.md 中的统计数字与描述

## [1.1.0] - 2026-04-17

### 新增
- **股探报告深度整合**：将微博小号 @股探报告（2017.12.24）发布的 9 篇交易心理系列纳入语料库
  - 包含 8 篇「市场交易反心理特征」+ 1 篇研究篇
  - 提取早期工具原型：3/4 量阴线、砖型图、无穷成本线
  - 新增 3 条引用金句到 SKILL.md
- **书单智识谱系**：验证并补全 Z 哥 2020 年 B 站直播推荐的完整书单（14 本），建立智识谱系表格
  - 核心著作：《股票大作手回忆录》《华尔街幽灵》《澄明之境》《十年一梦》等
- **决策启发式新增 2 条**：
  9. 完美图形，干错也要干 + 严格止损（来自股探报告）
  10. 走坏的票不砍，是最大风险（来自股探报告）

### 改进
- 心智模型 1 更新：从「确定性优先」改为「不确定性为底，纪律为桥」，强化十二年一致性（2014→2017→2025）

## [1.0.0] - 2026-04-17

### 初始版本
- **SKILL.md 核心文件**：构建 6 个核心心智模型、10 条决策启发式、完整表达 DNA
  - 心智模型：不确定性为底 / 周期思维 / 交易系统（少妇战法+四块砖）/ 逆向操作 / 稀缺性资产 / 海权-商业映射
  - 决策启发式：9:33 清仓 / 四块红砖减仓 / 绿砖不抄底 / J-10 B1 买点 / BBI 减半 / 三波不做 / 人人皆知出货 / 宁可错过 / 完美图形干错也干
- **Agentic Protocol**：Z 哥式研究 → 框架分析 → 风格回答的三步工作流
- **角色扮演规则**：用「我」而非「Z 哥认为」，保持表达 DNA 一致性
- **GitHub 开源准备**：README.md、CONTRIBUTING.md、LICENSE（MIT）、.gitignore
- **语料基础**：136 篇本地文章 + 13 个 ztalk transcript + 雪球专栏 + 网络预研
- **辅助脚本**：B 站视频批量下载（yt-dlp）、音频 ASR 转录（faster-whisper）

---

**版本说明**：本项目采用语义化版本（MAJOR.MINOR.PATCH）。MAJOR 表示心智模型级别的重构，MINOR 表示新增战术/启发式/语料，PATCH 表示排版修正或数字更新。
