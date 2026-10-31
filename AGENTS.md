# Repository Guidelines

> 本文件面向 AI 编程 Agent：是**功能指南**，不是架构全书。架构细节在 `docs/`，模块树在源码，这里只给入口、命令、约定、关键路径与注意事项。所有事实（版本、命令、路径）均对照仓库核实。

## Project Overview

**zettaranc-skill** = 「Z 哥（zettaranc/万千）思维框架蒸馏包」+「A 股真实数据量化工具」双轨项目。

- **核心交付物**：`SKILL.md`（Skill-Schema-V2 合规的角色扮演协议，被 Claude Code/Cursor 加载）——LLM 用 Z 哥角色生成点评/话术。
- **数据层**：Python 包 `modules/`，只负责**数据准备**（指标、信号、回测、评分），不做投资话术——这是刻意分层，避免「AI 味」。
- **可选层**：`api/`（FastAPI REST）+ `frontend/`（React 看板）+ `rust/`（Rust 加速计算核）。
- **当前版本**：`v4.12.0`（`pyproject.toml:7`、`SKILL.md` frontmatter + 版本表、`skill.json:3`、`README.md` badge、`docs/CHANGELOG.md` 顶端、`AGENTS.md` 本行，共 **7 处**必须一致；改 `pyproject.toml` 的 `version` 时同步这 7 处，`docs/INDEX.md` 维护规则有同样的清单）。
- **许可证**：MIT。

## Architecture & Data Flow

### 双模式

| 模式 | 环境变量 | 说明 |
|---|---|---|
| JNB / 真实数据 | `DATA_MODE=jnb` | 走数据源取真实行情，可算指标/战法 |
| 普通小万 | `DATA_MODE=websearch` | 纯 LLM 对话，无事可查外部数据 |

### 数据源优先级（`modules/datasource_resolution.py` 统一决议）

**「环境变量 → 用哪个 provider」只有一个定义处**：`modules/datasource_resolution.py::resolve_provider()`。读路径（`CompositeDataSource`）与写路径（`DataSyncer`）都消费它，因此两边永远选到同一个源。

```
hithink（HITHINK_FINANCE_API_KEY 配置时最优先，v4.2.0）
  → Indevs（INDEVS_API_KEY，v3.8.1）
  → Tushare Pro（JNB 模式配置 TUSHARE_TOKEN）
  → a-stock-data（免费源，零配置默认，v4.1.0）
  → tushare-data-bridge（HTTP 缓存代理）
  → 本地 SQLite（data/stock_data.db，离线兜底）
```

读路径（`CompositeDataSource`）在此基础上**按方法链式回退**；写路径（`DataSyncer`）取**同一个首选源**（单源，保留重试与退避语义）。

> 改优先级只改 `resolve_provider()` 一处。`modules/data_sync/syncer.py` 与 `modules/datasource.py` 此前各抄了一份环境变量判断且已经漂移（写路径没有 hithink 分支），`zt sync` 还直接钉死 tushare——在默认 websearch 模式下 tushare 无数据后端，整次同步静默同步 0 行却打印"同步完成"。v4.5.0 起统一。

约定：**DB 优先读 K 线**（先查 `daily_kline` 表，没有才调 API 并写回）。K 线读取统一走 `modules/indicators/data_layer.py::get_kline_data` 或 `modules/strategies/core.py::get_kline_data`。数据源缺 key 时**绝不编造价格/信号**，明确报告当前数据状态。

### 数据流链条

```
数据源 (CompositeDataSource)
  → indicators/data_layer.py      # get_kline_data + indicator_cache + analyze_stock() 30步管线 → IndicatorResult
  → strategies/__init__.py        # detect_all_strategies(ts_code, days) 折叠每日战法探测器 → 战法信号
  → screener/engine.py            # screen_stocks(criteria, ...) 并行选股
  → backtest/ + simulator/        # 单策略/组合回测/少女少妇模拟器 → 绩效结果
                                    #   ↑ active_market_gate.py 注入闸门 port（TradingGate）控制开仓/强平
  → verify/pipeline.py            # 五项硬指标验收（v1.0）
  → CLI --json / Web API          # 宿主消费结构化数据
```

### Rust 加速桥（重要）

回测热路径有一层 Rust 计算核，经 PyO3 桥接进 Python：

```
modules/core/_rust_compat.py      # ZETTARANC_BACKTEST_IMPL=rust|python|auto（默认 rust）
modules/backtest/_rust_bridge.py  # is_rust_available() / bridge_shaofu_single() → Rust 单股加速，失败 fallback 到 Python
```

- Rust 侧为 Cargo workspace（`rust/Cargo.toml`，6 crates）：`core_types / indicators / backtest_engine / grid_search / screener / bindings`。`bindings` 用 pyo3（abi3-py312）+ pyo3-polars（polars 0.54）。
- 构建产物是 `_core_compute`（pyo3 扩展模块，`python/_core_compute/` 仅存 `__init__.py` 桩，`.so` 是 build artifact）。
- 构建：在 `rust/crates/bindings` 下 `maturin develop --release`（macOS 用 `rust/scripts/build_macos.sh`，Linux 兜底 `rust/Dockerfile.test` / `rust/scripts/build-linux.sh`）。
- **降级是静默的**：`auto` 模式导入失败就退回 Python，容易掩盖 Rust 回归。CI 有 `tests/test_rust_compat.py` + `tests/test_cli_uses_rust.py` 覆盖接线；`ZETTARANC_BACKTEST_IMPL=python` 可强制走 Python。
- 注意：`api/services/backtest_service.py` 目前直接用 Python 回测模块，**不走** Rust 桥。
- **Rust 只服务单股加速路径**（`run_single_strategy_backtest_py`）。组合与网格搜索的 Rust 入口从未被 Python 调用，且 Rust 侧**既无费率模型也无闸门模型**——当组合引擎会静默丢掉这两项，因此已删除。组合回测一律走 Python 的 `PortfolioBacktestEngine`。

### 单一事实来源

- `MarketRegime` 枚举 → `modules/core/market_context.py`（STRONG/NEUTRAL/WEAK）。
- `PerformanceMetrics`（20 字段）→ `modules/core/metrics.py`；`TRADING_DAYS_PER_YEAR=252` 也在此。
- 路径常量（`DATA_DIR/REGISTRY_DIR/REPORTS_DIR`）→ `modules/core/paths.py`。
- ATR → `modules/core/atr.py`。
- 错误 → `modules/core/errors.py`（`ZettarancError` 基类 + 统一错误码）。
- 命令结果外壳（CLI `--json` / API 错误响应）→ `modules/core/command_result.py`（`exception_to_dict` / `http_status_for` / `CommandResult`）。
- K 线读取 SQL → `modules/core/kline.py`（`KLINE_COLUMNS` / `read_kline_rows` / `read_kline_rows_batch` / `resolve_kline_limit`）。
- 请求限流 → `modules/core/rate_limit.py`（`wait_min_interval` / `WindowRateLimiter` / `make_window_limiter`）。
- 模拟器规范默认值 → `modules/simulator/config.py`（`SIMULATION_DEFAULTS` / `build_cost_model` / `build_simulation_config`）。
- 数据源决议 → `modules/datasource_resolution.py`（`resolve_provider()`：读路径与写路径共用同一份"环境变量 → provider"判断）。
- 少妇战法回测实现 → `modules/backtest/shaofu.py`（`ShaofuBacktestResult` / `_calc_metrics` / `backtest_shaofu_single` / `summary_text`）。`modules/backtest_six_step.py` 只是**兼容 re-export**，新代码不要从那里导入。
- 少妇战法 B1 战法规则 → `modules/strategies/shaofu_b1.py::detect_shaofu_b1`（指标级 `indicators.detect_b1_today` 只管指标，战法条件在 strategies 层）。**与 `strategies.detect_b1` 是两套不同策略**，实测重合度仅 3%，不可互相替代。
- 组合回测实现 → `modules/backtest/portfolio.py::PortfolioBacktestEngine`（**唯一**的真组合：共享资金池 + 费率 + 闸门 + 仓位上限）。`zt backtest portfolio` 与 `zt verify v1.0` 都用它。
- 活跃市值闸门 → `modules/active_market_gate.py`（`GateAction` 枚举、`GateThresholds` 阈值、`TradingGate` port、失败策略的唯一来源）。注意 `signal`（当日涨跌幅判多空）与 `gate`（两日累计判闸门）是**两组不同语义的阈值**，不可合并；详见 `CONTEXT.md` 与 `docs/adr/0001-*.md`。
- **不要**在新代码里另立第二套 `MarketRegime`/`PerformanceMetrics`/ATR/路径常量；一律从 `modules/core` 导入。
- **不要**另写 K 线查询 SQL——一律走 `modules/core/kline.py`（并用 `resolve_kline_limit` 决定截断，别自己写 `if not start_date and days > 0`）。
- **不要**另写限流 sleep——走 `modules/core/rate_limit.py`。
- **不要**在 CLI/API 里另造错误响应形状——走 `modules/core/command_result.py`；CLI `--json` 出错时 stdout 必须是合法 JSON（带 `error_code`），API 用 `api/utils/errors.py::raise_api_error`（不要用 `HTTPException`，它会被 FastAPI 多包一层 `detail`）。
- **不要**硬编码模拟器默认值——走 `modules/simulator/config.py::build_simulation_config`。
- `min_resonance_score` 的单位**统一是 0-1**（不是 0-100），CLI 与 API 都一样。

## Key Directories

| 目录 | 用途 |
|---|---|
| `modules/` | Python 数据层与业务逻辑（核心） |
| `modules/core/` | 公共：metrics / market_context / walk_forward / atr / paths / errors / net / kline / rate_limit / command_result / `_rust_compat.py` |
| `modules/indicators/` | 60+ 技术指标 + 价格形态（`data_layer.py`、`core.py`（KDJ/BBI/…）、`price_patterns/`、`volume_patterns.py`、`wave_theory.py`、`kirin_detector.py`） |
| `modules/strategies/` | 30+ 战法识别（`core.py`、`base_strategies.py`、`compound_strategies.py`、`sell_signals.py`、`vectorized.py`），入口 `detect_all_strategies` |
| `modules/screener/` | 选股评分（`engine.py`、`criteria.py`、`scoring.py`、`market.py`、`workflow.py`） |
| `modules/simulator/` | 少女/少妇模拟器（`simulator.py`、`walk_forward.py`、`position_sizer.py`、`execution_engine.py` 等） |
| `modules/backtest/` | 单策略/组合回测（`single.py`、`portfolio.py`、`b1_b2_backtest.py`、`shaofu.py`、`_rust_bridge.py`） |
| `modules/verify/` | 少妇战法 v1.0 验收工程化（`pipeline.py`、`gates.py`、`walk_forward.py`、`portfolio_walk_forward.py`） |
| `modules/data_sync/` | 数据同步/限流（`rate_limiter.py`、`syncer.py`、`fetcher.py`、`indicator_cache.py`） |
| `modules/self_optimizer/` | Darwin 自优化管线（`param_registry.py`、`mutator.py`、`scorer.py`） |
| `api/` | FastAPI REST（`main.py`、`routes/`、`services/`、`models/`、`config.py`） |
| `frontend/` | React + Vite 看板（可选） |
| `rust/` | Rust 计算核 workspace + `scripts/`（`Dockerfile.test`） |
| `python/_core_compute/` | maturin python 源包桩（`_core_compute` 扩展的 import 壳） |
| `knowledge/` | 交易体系知识文档（29 篇顶层 + `macro/`、`reference/`、`strategies/` 子目录） |
| `references/research/` | 语料调研提炼文件（原始语料不入库） |
| `rules/` | 意图规则与决策框架 |
| `corpus/` | 语料采集与质检（`quality_check.py`、`dual_axis_review.py` 等） |
| `scripts/` | 薄壳工具脚本（业务逻辑在 modules/） |
| `tests/` | pytest 测试（~104 个 `test_*.py`） |
| `docs/` | 文档（`CHANGELOG.md`、`USER_GUIDE.md`、`CONFIG_GUIDE.md`、`CONTRIBUTING.md` 等） |
| `docs/adr/` | 架构决策记录（ADR）：决策与理由，避免后来者重新发明 |
| `docs/agents/` | 工程技能约定：issue tracker / triage 标签 / 领域文档消费规则 |
| `CONTEXT.md` | 领域词汇表（纯术语，不含实现细节） |
| `data/` | SQLite 数据库与报告（**gitignored，不入库**） |

## Development Commands

### 安装（pip 为准）

```bash
pip install -r requirements.txt        # 核心依赖
pip install -e ".[dev]"                # 注册 zt/zt-web/zt-monitor 命令 + 测试依赖
pip install -e ".[corpus]"             # 语料处理可选依赖（yt-dlp/faster-whisper）
```

> 本机开发用 gitignored 的 `.venv`；仓库里残留的 `.venv311/.venv312/.venv313` 是被忽略的旧环境。**Rust 加速路径**另需 `maturin develop --release`（见上文）。

### CLI

```bash
zt analyze 600487.SH --days 365 --json        # 分析单股
zt screen --strategy B1 --limit 20 --json     # 批量选股（策略别名见 cli_commands/strategy_alias.py）
zt diagnose 600487.SH --json                  # 持仓诊断
zt backtest shaofu 600487.SH --days 250 --json  # 少妇战法回测（Rust 桥优先）
zt simulate [codes] --days 250 --capital 100000 --json   # 模拟器
zt verify v1.0 --limit 50 --days 300 --walk-forward      # v1.0 五硬指标验收
zt workflow                                      # 每日五步工作流（等价 daily）
zt sync status                                   # 数据同步状态
zt monitor --json                                # 自选股监控
zt self-optimize run --target trading --rounds 3 # Darwin 自优化
zt trade add "口语化交易描述"                     # 记录交易
zt market timing --json                            # 市场择时指标（v4.3.0 新增）
```

所有命令支持 `--json`，宿主直接解析。16 个顶层子命令：`analyze / screen / score / workflow / diagnose / watchlist / sync / track / self-optimize / backtest / trade / daily / market / monitor / simulate / verify`。

### Web / 前端

```bash
pip install fastapi uvicorn pydantic-settings   # API 依赖不在 requirements.txt
zt-web                                             # 后端 http://localhost:8000（uvicorn）
cd frontend && npm install && npm run dev          # 前端 http://localhost:5173，/api 代理到 8000
npm run build                                      # 生产构建（tsc -b && vite build）
npm run lint                                       # ESLint
```

### 质量检查

```bash
ruff check modules tests
ruff format --check modules tests
mypy modules/ --ignore-missing-imports          # 非严格
python corpus/quality_check.py SKILL.md --strict   # SKILL.md 12 项质量门
python corpus/dual_axis_review.py SKILL.md --skip-llm  # 双轴评审（--skip-llm 跳过 LLM）
```

### 测试

```bash
python -m pytest tests/ -v                  # 全量（约 40s）
python -m pytest tests/test_indicators.py -v
python -m pytest tests/ -m slow -v          # 慢速端到端
RUN_REALDATA=true python -m pytest tests/test_indicators_realdata.py -v  # 真实数据（需 TUSHARE_TOKEN）
```

## Code Conventions & Common Patterns

- **语言**：中文文档字符串/注释；脚本文件头 `#!/usr/bin/env python3`。
- **DB 访问**：统一 `modules/database.py::get_connection()` 上下文管理器（WAL + 自动 commit/rollback）；`DB_PATH` 从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取。
- **环境变量加载**：`modules/__init__.py` 包首次 import 时一次性 `load_dotenv(override=False)`（支持 `ZETTARANC_ENV` 自定义路径）；子模块**不要**重复加载。
- **路径常量**：从 `modules/core/paths.py` 导入，不硬编码 252/250。
- **限流**：所有 Tushare API 调用必须带 `_rate_limit()`，控制 `TUSHARE_RPM`（默认 120 次/分）。
- **错误处理**：API 调用 try/except 包裹，记录 error log，返回空 DataFrame/None 而非抛异常中断。
- **DB-first 读**：K 线/指标先查 `daily_kline`/`indicator_cache`，没命中才调 API 并写回缓存。
- **缓存**：`indicator_cache` 为内存 + SQLite 双层（见 `modules/indicators/data_layer.py`）。
- **Rust 桥**：仅单股加速路径用 Rust（`bridge_shaofu_single`）。失败时静默 fallback 到 Python——**降级是静默的**，容易掩盖 Rust 回归；`ZETTARANC_BACKTEST_IMPL=python` 可强制走 Python。
- **Ruff**：`line-length=120`，`target-version=py312`，`select=F,E,W,UP`，`ignore=E501,F401,F403`；format 双引号 + 空格。
- **Mypy**：`python_version=3.12`，`ignore_missing_imports=true`，仅关键路径做类型检查（screener/cli/data_sync/indicators/core/strategies），非严格渐进式。
- **类型统一**：`PerformanceMetrics` / `MarketRegime` / `TRADING_DAYS_PER_YEAR` / 收益率字段 `annualized_return` / `equity_curve: list[float]` / `calculate_atr` 一律以 `modules/core` 为准。

## Important Files

| 文件 | 作用 |
|---|---|
| `pyproject.toml` | 构建（setuptools）+ 全部工具配置（ruff/mypy/pytest/maturin）；entry points：`zt`→`modules.cli:main`、`zt-web`→`api.main:start_web`、`zt-monitor`→`modules.monitor:main` |
| `SKILL.md` | 角色扮演协议（核心交付物，12 项质量门校验） |
| `skill.json` | Skill 元数据 |
| `modules/cli.py` + `modules/cli_commands/` | CLI 分发与 16 子命令实现（`cli_commands/` 为包：analyze / backtest / data / diagnose / portfolio / screen / simulate / strategy_alias / _helpers） |
| `modules/datasource.py` | 统一数据源 + CompositeDataSource（优先级链） |
| `modules/active_market_gate.py` | 活跃市值闸门判定（唯一实现）：GateAction / 阈值 / TradingGate port |
| `modules/datasource_resolution.py` | 数据源决议（唯一实现）：resolve_provider() 决定 auto 模式用哪个 provider |
| `modules/database.py` | SQLite 层 + `get_connection()` + `init_database()` |
| `modules/indicators/data_layer.py` | DB-first K 线读 + 指标缓存 + `analyze_stock()` 管线 |
| `modules/strategies/__init__.py` | `detect_all_strategies()` 战法折叠入口 |
| `modules/core/_rust_compat.py` | Rust/Python 切换 shim（`ZETTARANC_BACKTEST_IMPL`） |
| `modules/core/kline.py` | K 线读取 SQL 唯一来源（`read_kline_rows` / `read_kline_rows_batch` / `resolve_kline_limit`） |
| `modules/core/command_result.py` | 命令结果外壳唯一实现（异常 → 统一 JSON 外壳 + HTTP 状态码映射） |
| `modules/core/rate_limit.py` | 请求限流公共实现（间隔 + 60s 滑动窗口） |
| `modules/simulator/config.py` | 模拟器规范默认值与唯一装配点（CLI 与 API 共用） |
| `api/main.py` | FastAPI 入口 + `start_web()`（uvicorn 8000，9 个 router 挂 `/api/v1`） |
| `api/config.py` | pydantic-settings `Settings`（db_path / data_mode / cors / api_prefix） |
| `frontend/vite.config.ts` | vite 端口 5173 + `/api` 代理到 `http://localhost:8000` |
| `rust/Cargo.toml` | Rust workspace（6 crates） |
| `tests/conftest.py` | pytest fixtures + 数据工厂 |
| `.env.example` | 运行时环境变量模板 |
| `.pre-commit-config.yaml` | pre-commit 钩子（ruff/mypy/SKILL 质量门/merge-yaml-行尾检查） |
| `docs/CHANGELOG.md` | 版本与变更日志（v4.3.0 头） |

## Runtime / Tooling Preferences

- **Python**：`requires-python >=3.12`；CLI/测试跑在 3.12/3.13（CI release matrix），Rust PyO3 构建在 3.11（`rust/Dockerfile.test`）或 3.12（CI）。文档口径已于 v4.3.0 统一为 3.12+，以 `pyproject.toml` 的 `>=3.12` 为准。
- **包管理器**：**pip 为正**（`requirements.txt` 是已提交的依赖源；`requirements.txt` 比 `pyproject.toml` 多一个 `mootdx>=0.11.0`）。根目录 `uv.lock` 存在但被 `gitignore`（`/uv.lock`），且 pyproject 无 `[tool.uv]` 段——**非 canonical**，别依赖它。
- **Rust**：需要时用 maturin 构建；`rust-toolchain.toml` 锁 1.78.0，`cargo test --workspace --exclude zt_bindings`（bindings 由 PyO3 侧构建）。
- **前端**：Node/npm（非包管理器约束项）；frontend 依赖独立于 Python，API 依赖（fastapi/uvicorn/pydantic-settings）**不**在 `requirements.txt`。
- **环境变量**：`.env`（gitignored）经 python-dotenv 加载；敏感 key（TUSHARE/INDEVS/HITHINK/LLM/webhook）绝不硬编码。

## Testing & QA

- **框架**：pytest。配置见 `pyproject.toml [tool.pytest.ini_options]`：`testpaths=['tests']`、`python_files=['test_*.py']`、`addopts='-v --tb=short'`。
- **标记**：`@pytest.mark.slow`（慢速端到端，默认 CI 不跑）；`@pytest.mark.realdata`（真实数据，需 `RUN_REALDATA=true` + `TUSHARE_TOKEN` + `TUSHARE_API_URL`，默认 skip；`INDEVS_API_KEY` 另门控一个 live-API 文件）。
- **fixtures**（`tests/conftest.py`）：
  - `mock_env_for_tests`（autouse，剥离真实 env 并把 DATA_MODE 置 `websearch` + 临时 DB）
  - `temp_db`（init + drop）、`db_conn`（连接上下文）
  - `state_with_interrupted_run`、`mock_monthly_reviews_with_poor_strategy`
  - 数据工厂：`make_kline_row`、`make_daily_data`、`generate_uptrend_klines`、`generate_downtrend_klines`、`generate_b1_scenario`、`write_klines_to_db`、`write_stock_basic`
- **数据库隔离**：测试用临时 SQLite 文件，互相不干扰。
- **CI**（`.github/workflows/`）：
  - `rust-ci.yml`：PR/push 时跑 Rust（ubuntu/macos，Rust 1.78 + cargo fmt/clippy/test，`--exclude zt_bindings`）+ Python smoke（`maturin develop --release` 后 import `_core_compute`）。
  - `release.yml`：tag 驱动 `v*.*.*`，test（py3.12/3.13）→ build wheel（maturin）→ 装 wheel → 跑 `tests/test_rust_compat.py` + `tests/test_cli_uses_rust.py` → PyPI → GH Release → ClawHub。
- **Rust 接线测试**：`tests/test_rust_compat.py`（`pytest.importorskip('_core_compute')`，设 `ZETTARANC_BACKTEST_IMPL=rust` 测 choice 逻辑）；`tests/test_cli_uses_rust.py`（monkeypatch 假 rust 模块，断言 CLI 回测真走 Rust binding）。
- **无前端 JS 测试**；前端质量靠 `npm run lint` + `npm run build`（tsc -b）。

## Agent skills

### Issue tracker

本仓库的 issue 与 spec 走 GitHub Issues（`lululu811/zettaranc-skill`），用 `gh` CLI 读写。详见 `docs/agents/issue-tracker.md`。

### Triage labels

默认五角色词汇：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根目录一个 `CONTEXT.md` + `docs/adr/`。详见 `docs/agents/domain.md`。
