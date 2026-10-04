# Repository Guidelines

> 本文件面向 AI 编程 Agent：是**功能指南**，不是架构全书。架构细节在 `docs/`，模块树在源码，这里只给入口、命令、约定、关键路径与注意事项。所有事实（版本、命令、路径）均对照仓库核实。

## Project Overview

**zettaranc-skill** = 「Z 哥（zettaranc/万千）思维框架蒸馏包」+「A 股真实数据量化工具」双轨项目。

- **核心交付物**：`SKILL.md`（Skill-Schema-V2 合规的角色扮演协议，被 Claude Code/Cursor 加载）——LLM 用 Z 哥角色生成点评/话术。
- **数据层**：Python 包 `modules/`，只负责**数据准备**（指标、信号、回测、评分），不做投资话术——这是刻意分层，避免「AI 味」。
- **可选层**：`api/`（FastAPI REST）+ `frontend/`（React 看板）+ `rust/`（Rust 加速计算核）。
- **当前版本**：`v4.2.0`（`pyproject.toml`、`SKILL.md`、`skill.json`、`docs/CHANGELOG.md` 顶端四处一致）。
- **许可证**：MIT。

## Architecture & Data Flow

### 双模式

| 模式 | 环境变量 | 说明 |
|---|---|---|
| JNB / 真实数据 | `DATA_MODE=jnb` | 走数据源取真实行情，可算指标/战法 |
| 普通小万 | `DATA_MODE=websearch` | 纯 LLM 对话，无事可查外部数据 |

### 数据源优先级（`modules/datasource.py` 的 `CompositeDataSource`）

`auto` 模式按 token 感知降级：

```
hithink（HITHINK_FINANCE_API_KEY 配置时最优先，v4.2.0）
  → Indevs（INDEVS_API_KEY，v3.8.1）
  → Tushare Pro（JNB 模式配置 TUSHARE_TOKEN）
  → a-stock-data（免费源，零配置默认，v4.1.0）
  → tushare-data-bridge（HTTP 缓存代理）
  → 本地 SQLite（data/stock_data.db，离线兜底）
```

约定：**DB 优先读 K 线**（先查 `daily_kline` 表，没有才调 API 并写回）。K 线读取统一走 `modules/indicators/data_layer.py::get_kline_data` 或 `modules/strategies/core.py::get_kline_data`。数据源缺 key 时**绝不编造价格/信号**，明确报告当前数据状态。

### 数据流链条

```
数据源 (CompositeDataSource)
  → indicators/data_layer.py      # get_kline_data + indicator_cache + analyze_stock() 30步管线 → IndicatorResult
  → strategies/__init__.py        # detect_all_strategies(ts_code, days) 折叠每日战法探测器 → 战法信号
  → screener/engine.py            # screen_stocks(criteria, ...) 并行选股
  → backtest/ + simulator/        # 单策略/组合回测/少女少妇模拟器 → 绩效结果
  → verify/pipeline.py            # 五项硬指标验收（v1.0）
  → CLI --json / Web API          # 宿主消费结构化数据
```

### Rust 加速桥（重要）

回测热路径有一层 Rust 计算核，经 PyO3 桥接进 Python：

```
modules/core/_rust_compat.py      # ZETTARANC_BACKTEST_IMPL=rust|python|auto（默认 rust）
modules/backtest/_rust_bridge.py  # is_rust_available() / try_call(name,...) → 失败业务层 fallback 到 Python
```

- Rust 侧为 Cargo workspace（`rust/Cargo.toml`，6 crates）：`core_types / indicators / backtest_engine / grid_search / screener / bindings`。`bindings` 用 pyo3（abi3-py312）+ pyo3-polars（polars 0.54）。
- 构建产物是 `_core_compute`（pyo3 扩展模块，`python/_core_compute/` 仅存 `__init__.py` 桩，`.so` 是 build artifact）。
- 构建：在 `rust/crates/bindings` 下 `maturin develop --release`（macOS 用 `rust/scripts/build_macos.sh`，Linux 兜底 `rust/Dockerfile.test` / `rust/scripts/build-linux.sh`）。
- **降级是静默的**：`auto` 模式导入失败就退回 Python，容易掩盖 Rust 回归。CI 有 `tests/test_rust_compat.py` + `tests/test_cli_uses_rust.py` 覆盖接线；`ZETTARANC_BACKTEST_IMPL=python` 可强制走 Python。
- 注意：`api/services/backtest_service.py` 目前直接用 Python 回测模块，**不走** Rust 桥。

### 单一事实来源

- `MarketRegime` 枚举 → `modules/core/market_context.py`（STRONG/NEUTRAL/WEAK）。
- `PerformanceMetrics`（20 字段）→ `modules/core/metrics.py`；`TRADING_DAYS_PER_YEAR=252` 也在此。
- 路径常量（`DATA_DIR/REGISTRY_DIR/REPORTS_DIR`）→ `modules/core/paths.py`。
- ATR → `modules/core/atr.py`。
- 错误 → `modules/core/errors.py`（`ZettarancError` 基类 + 统一错误码）。
- 选股策略中文别名（16 个）→ `modules/screener/aliases.py` 的 `STRATEGY_ALIAS` / `STRATEGY_DESCRIPTIONS`；`modules/cli.py` 与 `api/services/screen_service.py` 都从这里导入（前端 `frontend/src/lib/constants.ts::STRATEGIES` 是镜像列表，按 criteria 去重后 14 项）。
- **不要**在新代码里另立第二套 `MarketRegime`/`PerformanceMetrics`/ATR/路径常量/策略别名；一律从 `modules/core`、`modules/screener/aliases.py` 导入。

## Key Directories

| 目录 | 用途 |
|---|---|
| `modules/` | Python 数据层与业务逻辑（核心） |
| `modules/core/` | 公共：metrics / market_context / walk_forward / atr / paths / errors / net / `_rust_compat.py` |
| `modules/indicators/` | 60+ 技术指标 + 价格形态（`data_layer.py`、`core.py`（KDJ/BBI/…）、`price_patterns/`、`volume_patterns.py`、`wave_theory.py`、`kirin_detector.py`） |
| `modules/strategies/` | 30+ 战法识别（`core.py`、`base_strategies.py`、`compound_strategies.py`、`sell_signals.py`、`vectorized.py`），入口 `detect_all_strategies` |
| `modules/screener/` | 选股评分（`engine.py`、`criteria.py`、`scoring.py`、`market.py`、`workflow.py`） |
| `modules/simulator/` | 少女/少妇模拟器（`simulator.py`、`walk_forward.py`、`position_sizer.py`、`execution_engine.py` 等） |
| `modules/backtest/` | 单策略/组合回测（`single.py`、`portfolio.py`、`b1_b2.py`、`_rust_bridge.py`） |
| `modules/verify/` | 少妇战法 v1.0 验收工程化（`pipeline.py`、`gates.py`、`walk_forward.py`、`portfolio_walk_forward.py`） |
| `modules/data_sync/` | 数据同步/限流（`rate_limiter.py`、`syncer.py`、`fetcher.py`、`indicator_cache.py`） |
| `modules/self_optimizer/` | Darwin 自优化管线（`param_registry.py`、`mutator.py`、`scorer.py`） |
| `api/` | FastAPI REST（`main.py`、`routes/`、`services/`、`models/`、`config.py`） |
| `frontend/` | React + Vite 看板（可选，浅色玻璃拟态主题，端口 5173） |
| `frontend-legacy/` | 改版前的深色终端版前端快照（端口 5174，`/api` 同样代理 8000），用于并排对照 |
| `rust/` | Rust 计算核 workspace + `scripts/`（`Dockerfile.test`） |
| `python/_core_compute/` | maturin python 源包桩（`_core_compute` 扩展的 import 壳） |
| `knowledge/` | 交易体系知识文档（29 篇顶层 + `macro/`、`reference/`、`strategies/` 子目录） |
| `references/research/` | 语料调研提炼文件（原始语料不入库） |
| `rules/` | 意图规则与决策框架 |
| `corpus/` | 语料采集与质检（`quality_check.py`、`dual_axis_review.py` 等） |
| `scripts/` | 薄壳工具脚本（业务逻辑在 modules/） |
| `tests/` | pytest 测试（~104 个 `test_*.py`） |
| `docs/` | 文档（`CHANGELOG.md`、`USER_GUIDE.md`、`CONFIG_GUIDE.md`、`CONTRIBUTING.md` 等） |
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
zt screen --strategy B1 --limit 20 --json     # 批量选股（策略别名见 cli_commands.py）
zt diagnose 600487.SH --json                  # 持仓诊断
zt backtest shaofu 600487.SH --days 250 --json  # 少妇战法回测（Rust 桥优先）
zt simulate [codes] --days 250 --capital 100000 --json   # 模拟器
zt verify v1.0 --limit 50 --days 300 --walk-forward      # v1.0 五硬指标验收
zt workflow                                      # 每日五步工作流（等价 daily）
zt sync status                                   # 数据同步状态
zt monitor --json                                # 自选股监控
zt self-optimize run --target trading --rounds 3 # Darwin 自优化
zt trade add "口语化交易描述"                     # 记录交易
```

所有命令支持 `--json`，宿主直接解析。15 个顶层子命令：`analyze / screen / score / workflow / diagnose / watchlist / sync / track / self-optimize / backtest / trade / daily / monitor / simulate / verify`。

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
- **Rust 桥**：业务层用 `result = try_call(...); if result is not None: use_it() else: python_fallback(...)` 模式/语义（不要用 `or` 判断，Rust 成功返回 falsy 值会被误判）；可选实现经 `ZETTARANC_BACKTEST_IMPL` 切换，默认 `rust`。
- **Ruff**：`line-length=120`，`target-version=py312`，`select=F,E,W,UP`，`ignore=E501,F401,F403`；format 双引号 + 空格。
- **Mypy**：`python_version=3.12`，`ignore_missing_imports=true`，仅关键路径做类型检查（screener/cli/data_sync/indicators/core/strategies），非严格渐进式。
- **类型统一**：`PerformanceMetrics` / `MarketRegime` / `TRADING_DAYS_PER_YEAR` / 收益率字段 `annualized_return` / `equity_curve: list[float]` / `calculate_atr` 一律以 `modules/core` 为准。

## Important Files

| 文件 | 作用 |
|---|---|
| `pyproject.toml` | 构建（setuptools）+ 全部工具配置（ruff/mypy/pytest/maturin）；entry points：`zt`→`modules.cli:main`、`zt-web`→`api.main:start_web`、`zt-monitor`→`modules.monitor:main` |
| `SKILL.md` | 角色扮演协议（核心交付物，12 项质量门校验） |
| `skill.json` | Skill 元数据 |
| `modules/cli.py` + `modules/cli_commands.py` | CLI 分发与 15 子命令实现 |
| `modules/datasource.py` | 统一数据源 + CompositeDataSource（优先级链） |
| `modules/database.py` | SQLite 层 + `get_connection()` + `init_database()` |
| `modules/indicators/data_layer.py` | DB-first K 线读 + 指标缓存 + `analyze_stock()` 管线 |
| `modules/strategies/__init__.py` | `detect_all_strategies()` 战法折叠入口 |
| `modules/core/_rust_compat.py` | Rust/Python 切换 shim（`ZETTARANC_BACKTEST_IMPL`） |
| `api/main.py` | FastAPI 入口 + `start_web()`（uvicorn 8000，9 个 router 挂 `/api/v1`） |
| `api/config.py` | pydantic-settings `Settings`（db_path / data_mode / cors / api_prefix） |
| `frontend/vite.config.ts` | vite 端口 5173 + `/api` 代理到 `http://localhost:8000`（`frontend-legacy/vite.config.ts` 为 5174） |
| `rust/Cargo.toml` | Rust workspace（6 crates） |
| `tests/conftest.py` | pytest fixtures + 数据工厂 |
| `.env.example` | 运行时环境变量模板 |
| `.pre-commit-config.yaml` | pre-commit 钩子（ruff/mypy/SKILL 质量门/merge-yaml-行尾检查） |
| `docs/CHANGELOG.md` | 版本与变更日志（v4.2.0 头） |

## Runtime / Tooling Preferences

- **Python**：`requires-python >=3.12`；CLI/测试跑在 3.12/3.13（CI release matrix），Rust PyO3 构建在 3.11（`rust/Dockerfile.test`）或 3.12（CI）。**文档里仍残留「Python 3.10+」的过时说法**——以 `pyproject.toml` 的 `>=3.12` 为准。
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
