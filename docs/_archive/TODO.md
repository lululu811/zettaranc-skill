# 待优化项（TODO）

> 记录实测发现、尚未修复的问题。按优先级排列，每项包含：现象 / 影响 / 证据 / 建议方案。
> 修复一项即在文末「已处理」区追加记录，保持正文只留未决项。

**最后更新**：2026-09-12

---

## 📌 待发版：v4.3.1（代码已推送，尚未打 tag）

**当前状态**（2026-09-12）：

| 项 | 状态 |
|---|---|
| 代码推送到 `origin/main` | ✅ `d4c5d71` |
| 四处版本号 = 4.3.1 | ✅ 已提交 |
| `docs/CHANGELOG.md` v4.3.1 段 | ✅ 已写好 |
| **git tag `v4.3.1`** | ❌ **未打** |
| **发布到 PyPI / GitHub Release / ClawHub** | ❌ **未发** |

**发版时执行**（推送 tag 会触发 `release.yml` 自动发布，**不可逆**）：

```bash
# 前置检查
python scripts/check_version_consistency.py     # 四处版本号一致
pytest tests/ -q                                 # 测试通过

# 发版
git tag v4.3.1
git push origin v4.3.1        # ← 触发 release workflow
```

**注意事项**：

- 打 tag 前确认 PyPI 上 `4.3.1` 未被占用（release.yml 上传失败会导致流程中断）
- 若暂不发版期间又有新提交，那些提交会归入「未发布的 v4.3.1」——
  发版时应把 tag 打在**确认稳定**的那个 commit 上，而非当前 main 顶端
- tag 一旦推送，PyPI 上的版本号不可复用（删了也不能重传同名版本）

---

## P0 · SQLite 并发写锁冲突（当前正在发生）

### 现象

批量同步指标缓存（`zt sync sync --indicators`）时，约 **20%** 的股票报：

```
[database] get_connection 事务失败，触发回滚: database is locked
指标缓存同步失败 000001.SZ: database is locked
```

### 影响

- 指标缓存批量同步有稳定失败率（实测约 120/586 ≈ 20%）
- **不会损坏数据**（写入是 `INSERT OR REPLACE` 幂等），但需补跑才能补齐
- 补跑时已成功的股票会重算一遍，浪费时间

### 根因（2026-09-12 实测确认）

**默认锁等待超时 5 秒不够用。** 并发写入时锁等待会超过 5 秒，超时即失败。

| 环节 | 代码位置 | 事实 |
|---|---|---|
| 并发度 | `modules/data_sync/rate_limiter.py:14` | `_MAX_SYNC_WORKERS = 5` |
| 执行器 | `modules/data_sync/syncer.py:175` | `ThreadPoolExecutor(max_workers=5)` |
| 超时来源 | Python `sqlite3.connect()` | **默认 `timeout=5.0` 秒**，项目未覆盖 |

**关键实测**（独立测试库，5 线程 × 60 只 × 120 天，合成数据）：

| 配置 | 失败 | 中位耗时 | 最大耗时 |
|---|---|---|---|
| 默认（5s） | **7 / 60** | 403ms | **10959ms** |
| **busy_timeout=30s** | **0 / 60** | 401ms | **24120ms** |

→ 最大耗时 24 秒，证明**锁等待确实会远超 5 秒**，排队假设成立。
→ 把超时放宽到 30s 后**失败完全消失**。

**已排除的错误推断**（都是我之前判断错误，留档以免重犯）：

| 曾以为的根因 | 实测结果 |
|---|---|
| ❌「SQLite 默认 `busy_timeout=0` 不等待」 | Python sqlite3 默认 **5 秒**，实测等满 5.21s 才失败 |
| ❌「事务包住 120 天计算循环 → 持锁过久」 | 缩小事务后**反而更慢**（825ms vs 403ms），失败率未改善（8 vs 7） |
| ❌「WAL 自动 checkpoint 导致」 | 该轮实验因 patch 失效结论不可信；且 30s 超时已能完全消除失败 |

> **自查提醒**：曾因 `get_connection` 是 `@contextmanager`，
> patch 时直接对其返回值调 `.execute()`，实际操作的是
> `_GeneratorContextManager`，PRAGMA **静默失效**（异常被 try/except 吞掉），
> 导致「30s 无效」的假结论。验证 PRAGMA 类改动必须先断言
> `PRAGMA busy_timeout` 的实际返回值。

### 建议方案（已验证有效）

**方案 1（推荐，一行改动）：把 `busy_timeout` 提到 30 秒**

```python
# modules/database.py，get_db_connection / get_connection 初始化处
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA busy_timeout=30000;")   # ← 30 秒，实测可将失败率降到 0
```

注意：**必须验证 PRAGMA 真的生效**（读回 `PRAGMA busy_timeout` 断言），
否则容易得到「改了没用」的错误结论。

**方案 2（可选，兜底）：写入失败退避重试**

对 `sqlite3.OperationalError` 且 message 含 `locked` 的情况重试 2-3 次。

**方案 3（不推荐）：缩小事务范围 / 降低并发度**

实测缩小事务无收益（更慢），降并发会牺牲吞吐。仅在前两案无效时考虑。

### 遗留待查

即便 30s 超时能让写入最终成功，**最大耗时仍达 24 秒**——说明高并发下
锁竞争非常激烈，吞吐受损。若后续要优化同步速度，可查：
WAL checkpoint 时机、`sync_log` 的额外写入争用、是否存在锁饥饿。

把 `_MAX_SYNC_WORKERS` 降到 2-3，或让「计算」并发、「写入」串行。
会牺牲一些吞吐，属兜底手段。

### 验证方式

```bash
zt sync sync --indicators --days 730 2>&1 | grep -c "database is locked"
# 目标：0（或接近 0）
```

### 备注

`sqlite3.connect()` 也支持 `timeout=` 参数（默认 5.0 秒），但本项目用 `PRAGMA` 显式配置更直观。需确认 `get_connection()` 是否传入了 `timeout`——若传了却仍报错，说明是别处的问题（如外部进程持锁）。

---

## P3 · 测试隔离规范（2026-09-12 实操教训）

**背景**：为验证 SQLite 写锁问题写了 `/tmp/zt_*.py` 系列脚本，用
`os.environ["DB_PATH"] = <tempfile>` + `init_database()` 建独立测试库，
涉及表：`daily_kline`（合成 K 线）、`indicator_cache`（指标）、`sync_log`。

**踩到的坑**：测试代码用了 `600000.SH ~ 600059.SH`，而这些是**真实股票**
（600000 浦发银行、600009 上海机场等）。若 `DB_PATH` 重定向失效，
`INSERT OR REPLACE` 会**静默覆盖真实数据**。

**规范建议**：

| 项 | 要求 |
|---|---|
| 测试代码 | 用明显非真实的前缀，如 `TEST0001.XX`、`900001.TST` |
| 测试日期 | 用真实交易日历不存在的日期（周末/节假日），便于事后区分 |
| 环境隔离 | 在 `import modules.*` **之前**设置 `DB_PATH`；`load_dotenv(override=False)` 不会覆盖已设值 |
| 清理 | 用 `try/finally` 保证 `shutil.rmtree`，否则异常退出会残留 |
| 验证 | 跑完必查生产库行数与数据特征，确认未污染 |

---

## P2 · `600487.SH` 指标缓存条数为 485 而非 120（历史遗留）

**现象**：生产库中 `600487.SH` 的 `indicator_cache` 有 485 条，其余 5561 只均为 120 条。

**原因**：非 bug。该股是环境搭建初期用免费源手动同步的，当时走了不同窗口
（`sync_daily_and_compute`），与后来批量同步的 `days=120` 不一致。

**影响**：无功能影响，但会让「条数应等于窗口」这类断言误报。

**建议**：若要求数据窗口统一，可单独对该股重跑 `sync_indicator_cache(days=120)`；
或接受现状（测试已改为校验「缓存条数 ≤ K 线条数」这一真正的不变量）。

---

## P2 · 指标缓存缺少「同步窗口」标记

**现象**：`indicator_cache` 无字段记录本次缓存是按多少天窗口（`days`）算出的。

**影响**：无法判断某只股票的缓存是否按当前期望窗口生成；混合窗口时（见上条）
只能靠条数间接推断。

**建议**：增加 `sync_days INTEGER` 与 `synced_at TEXT` 字段，便于缓存有效性判断
与增量更新决策。

---

## P1 · `daily_kline` 无数据来源标记

**现象**：无论数据来自 hithink / Tushare / Indevs / 免费源，都写入同一张 `daily_kline` 表，且**无 `source` 字段**。

**影响**：
- 事后无法区分某条 K 线来自哪个源
- 不同源的数据质量/口径不同（如复权方式），混在一张表里无法对账
- 排查数据异常时缺少关键信息

**证据**：`modules/datasource.py:986` 的 `save_klines(data)` 调用，写入时不携带来源信息。

**建议**：`daily_kline` 增加 `source TEXT` 字段，写回时传入当前生效数据源的 `name`。需同步更新 `save_klines()` 签名与所有调用点（约 20 处取数路径）。

---

## P1 · `zt sync` 强制绑定 Tushare 且无兜底

**现象**：`cmd_sync` 用 `get_datasource("tushare")`，该函数**直接构造 `TushareDataSource()`，没有任何降级**（`modules/datasource.py:1118-1119`）。JNB 模式缺 `TUSHARE_TOKEN` 或 `TUSHARE_API_URL` 时**直接抛 `CONFIG_MISSING` 崩溃**。

**影响**：
- 零配置 / 免费源用户无法使用批量同步（只能靠被动写回攒数据）
- 配了 hithink / Indevs 的用户，`zt sync` 仍只试 Tushare

**证据**：`modules/cli.py:481`、`modules/cli.py:499`；对比 `syncer.py:60-62` 存在「回退免费源」逻辑，但只在**不传 datasource** 时生效，CLI 传入显式源绕过了它。

**建议**：改为 `get_datasource("auto")` 或 `get_datasource(os.getenv("DATA_PREFERRED", "auto"))`，让批量同步也能享受多源降级。

---

## P2 · `SqliteDataSource` 的「离线兜底」名不副实

**现象**：`SqliteDataSource` 有 **8 个取数方法直接 `return None`**（`get_daily` / `get_index_daily` / `get_realtime_quote` / `get_moneyflow` / `get_daily_basic` / `get_stk_factor` / `get_stock_basic` / `get_trade_cal`），仅 `get_stock_list`、`get_kline_dicts`、`get_kline_dicts_batch` 真正实现。

**影响**：断网时只有 K 线能读到本地缓存，资金流/财务/基础信息全部拿不到。

**缓解**：项目真正的离线 K 线读取走 `indicators/data_layer.py::get_kline_data` 的 DB-first 机制，**不依赖** `SqliteDataSource`，所以日常分析不受影响。

**建议**：如需完整离线能力，把这 8 个方法接上已落库的表（`moneyflow` / `financial_data` / `stock_basic` 均已存在）。优先级低——除非有明确离线使用场景。

---

## ~~P2 · 版本号四处不一致~~ ✅ 已解决（2026-09-12 → v4.3.1）

**原现象**：`pyproject.toml` 为 4.3.0，`SKILL.md` 为 4.2.0，四处失配。

**已处理**：
- 四处统一至 **4.3.1**（`pyproject.toml` / `skill.json` / `SKILL.md` / `docs/CHANGELOG.md`）
- 新增 `scripts/check_version_consistency.py`：比对四处，不一致退出码 1
- 已挂 `.pre-commit-config.yaml`，在任一版本载体改动时自动拦截

**验证**：人为改为 4.2.0 后脚本正确报 `[FAIL]` 并退出码 1，恢复后 `[OK]`。

---

## P2 · Rust 静默降级 + 双实现无对拍测试

**现象**：`ZETTARANC_BACKTEST_IMPL=auto` 时，`_core_compute` 导入失败会**静默**回退 Python 实现。Rust 侧 3,740 行与 Python 实现是同语义双实现。

**影响**：
- 可能长期跑在 Python 实现上而无人知晓
- 改一处忘另一处的回归风险被隐藏

**建议**（按用户确认：Rust 为生产刚需、环境均已编译）：
1. 默认值改为 `rust`（失败即报错，fail-loud）
2. 加**对拍测试**：同一输入，Rust 与 Python 实现产出必须一致，纳入 CI
3. 对拍稳定后再评估是否收敛为单一实现（独立决策，不在此列）

---

## P3 · 工程化细节

| 项 | 现状 | 建议 |
|---|---|---|
| API 依赖缺失 | `fastapi` / `uvicorn` / `pydantic-settings` 不在 `requirements.txt` | 加入 extras 或单独说明 |
| `uv.lock` 非 canonical | 被 gitignore，pyproject 无 `[tool.uv]` 段 | 明确「pip 为准」或补全 uv 配置 |
| 前端无测试 | 仅 `npm run lint` + `tsc -b` | 加最小冒烟测试 |
| `uv` 与 pip 混用风险 | AGENTS.md 声明 pip 为正，但环境内有 uv | 保持 pip，避免生成 `uv.lock` |

---

## 已处理

| 日期 | 问题 | 处理 |
|---|---|---|
| 2026-09-12 | `TUSHARE_API_URL` 文档示例 `tt.xiaodefa.cn` 已失效（需专用 token，不受理官方 token），且未说明「基础路径 + SDK 追加 `/{接口名}`」约束 | 修正 `.env.example`、`docs/CONFIG_GUIDE.md`、`docs/USER_GUIDE.md`、`README.md`、`SKILL.md`、`modules/tushare_client.py`（含报错信息改进），推荐 `https://api.waditu.com/dataapi` |
| 2026-09-12 | 文档中「Tushare Token 为 56 位」的描述无依据（实测长度不固定） | 移除各处位数描述 |
| 2026-09-12 | 数据库表结构无统一文档 | 新增 `docs/DATABASE_SCHEMA.md`（15 表 / 27 索引完整字段说明） |
| 2026-09-12 | 项目架构无可视化说明 | 新增 `docs/architecture.html` |

---

## 附：本次环境搭建记录

- 虚拟环境：`.venv`（Python 3.12.12，miniforge3）
- 全市场 K 线同步：5,562 只 / 2,621,947 条 ✅
- 指标缓存：预计算进行中（受 P0 问题影响）
