# 数据库表结构说明（SQLite）

> 本文件描述 `data/stock_data.db` 的物理表结构，是**存储层字典**。
> 业务指标含义（J 值、白线/黄线、砖形图等）另见 `knowledge/data_dictionary.md` 与 `knowledge/indicators.md`。

| 项目 | 值 |
|---|---|
| 数据库 | SQLite（WAL 模式） |
| 默认路径 | `data/stock_data.db`（可由环境变量 `DB_PATH` 覆盖） |
| 表数量 | **15** |
| 索引数量 | **27** |
| 建表入口 | `modules/database.py::init_database()`（含 `init_tracking_tables()`） |
| 连接约定 | 统一走 `get_connection()` 上下文管理器（WAL + 自动 commit/rollback） |
| 同步日志 | `sync_log` 表记录增量断点 |

**注意**：`daily_kline` 表**不记录数据来源**——无论数据来自 hithink / Tushare / 免费源，都写入同一张表且无 `source` 字段，事后无法区分来源。

---

## 目录

| 分组 | 表 |
|---|---|
| [一、行情数据](#一行情数据表) | `daily_kline`、`moneyflow`、`financial_data`、`stock_basic` |
| [二、缓存与衍生数据](#二缓存与衍生数据表) | `indicator_cache`、`tushare_indicator_cache` |
| [三、业务记录](#三业务记录表) | `watchlist`、`trade_records`、`trade_signals` |
| [四、自我改进系统](#四自我改进系统表) | `tracking_pool_self`、`tracking_records_self`、`monthly_reviews_self`、`strategy_performance_self` |
| [五、运维日志](#五运维日志表) | `sync_log`、`llm_response_log` |
| [六、数据流向](#六数据流向) | — |

---

## 一、行情数据表

### 1.1 `daily_kline` — 日 K 线（核心表）

**用途**：存储个股/指数日线 OHLCV，是全系统最核心的表。所有分析、选股、回测、监控的数据起点。

**写入时机**：
- 主动：`zt sync sync`（增量，依据 `sync_log.last_date`）
- 被动：任意取数路径 DB-first miss 后写回（`CompositeDataSource.get_kline_dicts` → `save_klines`）

**字段（13）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码，如 `600487.SH` |
| `trade_date` | TEXT | NOT NULL | 交易日，格式 `YYYYMMDD` |
| `open` | REAL | | 开盘价 |
| `high` | REAL | | 最高价 |
| `low` | REAL | | 最低价 |
| `close` | REAL | | 收盘价 |
| `vol` | REAL | | 成交量（手） |
| `amount` | REAL | | 成交额（千元） |
| `pct_chg` | REAL | | 涨跌幅（%） |
| `vol_ratio` | REAL | | 量比；同步时写入 `None`，由指标计算模块在读取侧计算 |
| `is_limit_up` | INTEGER | | 涨停标记；同步时本地按涨跌幅阈值计算（阈值随板块不同） |
| `is_limit_down` | INTEGER | | 跌停标记，同上 |

**索引**

| 索引名 | 字段 | 用途 |
|---|---|---|
| `idx_kline_code_date` | (ts_code, trade_date) | 单股按日期取 K 线（主查询路径） |
| `idx_kline_date_agg` | (trade_date, pct_chg, amount) | 全市场某日聚合统计 |

**要点**
- 写入用 `INSERT OR REPLACE`，重复同步幂等
- `is_limit_up/down` 非数据源原始字段，是本地计算值
- 涨跌停阈值走 `environment_weights`（主板/创业板/科创板不同），由测试保证不硬编码 ±9.5%

---

### 1.2 `moneyflow` — 资金流向

**用途**：记录主力资金四档流入流出，用于判断资金动向（大单/特大单净流入）。

**写入时机**：`sync_moneyflow()`（`fetch_moneyflow`）

**字段（13）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `trade_date` | TEXT | NOT NULL | 交易日 |
| `buy_sm_amount` | REAL | | 小单买入额 |
| `buy_md_amount` | REAL | | 中单买入额 |
| `buy_lg_amount` | REAL | | 大单买入额 |
| `buy_elg_amount` | REAL | | 特大单买入额 |
| `sell_sm_amount` | REAL | | 小单卖出额 |
| `sell_md_amount` | REAL | | 中单卖出额 |
| `sell_lg_amount` | REAL | | 大单卖出额 |
| `sell_elg_amount` | REAL | | 特大单卖出额 |
| `net_mf` | REAL | | 净流入额 |
| `pct_mf` | REAL | | 净流入占比 |

**索引**：`idx_mf_code_date (ts_code, trade_date)`

---

### 1.3 `financial_data` — 财务与估值数据

**用途**：存储财报主要科目与估值指标，用于基本面过滤。

**写入时机**：`sync_daily_basic()` / `sync_all_daily_basic()`

**字段（13）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `ann_date` | TEXT | NOT NULL | 公告日期 `YYYYMMDD` |
| `end_date` | TEXT | NOT NULL | 报告期 `YYYYMMDD` |
| `report_type` | INTEGER | | 报告类型 |
| `revenue` | REAL | | 营业收入 |
| `net_profit` | REAL | | 净利润 |
| `total_assets` | REAL | | 总资产 |
| `total_liab` | REAL | | 总负债 |
| `equity` | REAL | | 股东权益 |
| `pe` | REAL | | 市盈率 |
| `pb` | REAL | | 市净率 |
| `ps` | REAL | | 市销率 |

**索引**：`idx_fin_code_date (ts_code, end_date)`

---

### 1.4 `stock_basic` — 股票基础信息

**用途**：股票列表与静态属性。**决定批量同步的范围**——`zt sync sync` 无参执行时会先刷新此表，再按此表逐只同步 K 线。

**写入时机**：`sync_stock_basic()`（`zt sync sync` 批量模式的第一步）

**字段（7）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `ts_code` | TEXT | PK | 股票代码 |
| `name` | TEXT | | 股票名称 |
| `area` | TEXT | | 地域 |
| `industry` | TEXT | | 所属行业 |
| `market` | TEXT | | 市场类型（主板/创业板/科创板等） |
| `list_date` | TEXT | | 上市日期 |
| `is_hs` | TEXT | | 是否沪深港通标的（S/H/N） |

**索引**：仅主键（无额外索引）

---

## 二、缓存与衍生数据表

### 2.1 `indicator_cache` — 本项目自算技术指标缓存（**最大表，64 字段**）

**用途**：缓存 `analyze_stock()` 30 步指标管线的完整输出，避免重复计算。缓存为**内存 + SQLite 双层**。

**写入时机**：`analyze_stock()` 执行后（`_save_indicator_cache`）；`zt sync sync --indicators` 批量预计算

**主键**：复合主键 `(ts_code, trade_date)`

**字段（64）**

| 分类 | 字段 | 说明 |
|---|---|---|
| **基础行情** | `close` `open` `high` `low` `vol` `pct_chg` | 原始 OHLCV 与涨跌幅 |
| **KDJ** | `k` `d` `j` | KDJ 三条线 |
| **MACD** | `dif` `dea` `macd_hist` | MACD |
| **均线** | `bbi` `ma5` `ma10` `ma20` `ma60` | BBI 与多周期均线 |
| **RSI / WR** | `rsi6` `rsi12` `rsi24` `wr5` `wr10` | 相对强弱 / 威廉指标 |
| **BOLL** | `boll_mid` `boll_upper` `boll_lower` `boll_width` `boll_position` | 布林带（含带宽与位置） |
| **量能** | `vol_ratio` | 量比 |
| **Z 哥特色** | `zg_white` `dg_yellow` | **白线 / 大哥线**（本项目核心指标） |
| | `is_gold_cross` `is_dead_cross` | 金叉 / 死叉 |
| **RSL** | `rsl_short` `rsl_long` | 相对强度（短/长） |
| **针状** | `is_needle_20` | 20 日针状标记 |
| **砖形图** | `brick_value` `brick_trend` `brick_count` `brick_trend_up` | 砖形图数值、趋势、计数 |
| **量价形态** | `is_fanbao` | 翻包 |
| | `is_beidou` | 北斗 |
| | `is_suoliang` | 缩量 |
| | `is_jiayin_zhenyang` | 假阴真阳 |
| | `is_jiayang_zhenyin` | 假阳真阴 |
| | `is_fangliang_yinxian` | 放量阴线 |
| **卖出评分** | `sell_score` `sell_reason` | 卖出评分与理由 |
| **信号** | `signal` `signal_desc` | 信号类型与描述 |
| **前高前低** | `prev_high` `prev_low` | 前期高低点 |
| **DMI** | `dmi_plus` `dmi_minus` `adx` | 趋向指标 |
| **资金流** | `net_lg_mf` `net_elg_mf` | 大单 / 特大单净流入 |
| **历史锚点** | `last_b1_date` `last_b1_price` | 最近一次 B1 信号日期与价格 |
| | `last_yidong_date` | 最近一次异动日期 |
| **市场环境** | `market_pct_chg` `market_dir` | 当日大盘涨跌幅与方向 |
| **时间戳** | `updated_at` | 缓存更新时间 |

**索引**

| 索引名 | 字段 | 用途 |
|---|---|---|
| `idx_ind_date` | (trade_date) | 按日期批量查询 |
| `idx_ind_signal` | (signal) | 按信号类型筛选（选股热路径） |
| `idx_ind_brick` | (brick_trend, brick_count) | 砖形图形态筛选 |
| `idx_ind_yidong` | (last_yidong_date) | 异动日期检索 |

---

### 2.2 `tushare_indicator_cache` — Tushare 官方指标缓存

**用途**：存储 **Tushare 服务端计算的**技术指标，作为**对拍基准**——用于验证本项目自算指标与官方口径是否一致（diff 验证）。

**写入时机**：`zt sync stk-factor`（`sync_stk_factor` / `sync_all_stk_factor`）

**主键**：复合主键 `(ts_code, trade_date)`

**字段（17）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | TEXT (PK) | 股票代码 |
| `trade_date` | TEXT (PK) | 交易日 |
| `close` | REAL | 收盘价 |
| `macd_dif` `macd_dea` `macd` | REAL | MACD 三条 |
| `kdj_k` `kdj_d` `kdj_j` | REAL | KDJ 三条 |
| `rsi_6` `rsi_12` `rsi_24` | REAL | RSI 多周期 |
| `boll_upper` `boll_mid` `boll_lower` | REAL | 布林带 |
| `cci` | REAL | CCI 顺势指标 |
| `created_at` | TEXT | 写入时间 |

**索引**：`idx_tushare_ind_date (ts_code, trade_date)`

> **与 `indicator_cache` 的区别**：本表存外部权威值（17 字段，仅通用指标），
> `indicator_cache` 存本地自算值（64 字段，含 Z 哥特色指标）。二者重叠部分可用于对拍。

---

## 三、业务记录表

### 3.1 `watchlist` — 自选股

**用途**：自选股清单。**决定 `zt monitor` 的扫描范围**。

**写入时机**：`zt watchlist add/remove`；API `POST /watchlist/`

**字段（8）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `name` | TEXT | | 股票名称 |
| `tags` | TEXT | | 标签（逗号分隔，支持分组） |
| `added_date` | TEXT | | 添加日期 |
| `alert_enabled` | INTEGER | | 是否启用预警 |
| `notes` | TEXT | | 备注 |
| `updated_at` | TEXT | | 更新时间 |

**索引**：`idx_watchlist_tags (tags)`

---

### 3.2 `trade_records` — 交易记录

**用途**：记录真实买卖交易，支撑 `zt trade list/review/stats` 与复盘点评。

**写入时机**：`zt trade add "口语化描述"`（经 `trade_parser` 解析）；API `POST /trade/`

**字段（15）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `trade_date` | TEXT | NOT NULL | 交易日期 |
| `action` | TEXT | NOT NULL | 买入 / 卖出 |
| `price` | REAL | NOT NULL | 成交价 |
| `quantity` | INTEGER | NOT NULL | 数量（股） |
| `amount` | REAL | NOT NULL | 成交金额 |
| `reason` | TEXT | | 交易理由 |
| `signal_type` | TEXT | | 触发的战法信号类型 |
| `zg_review` | TEXT | | **Z 哥点评**（复盘时生成） |
| `broker` | TEXT | | 券商 |
| `fee` | REAL | | 手续费 |
| `tags` | TEXT | | 标签 |
| `notes` | TEXT | | 备注 |
| `created_at` | TEXT | | 创建时间 |

**索引**

| 索引名 | 字段 |
|---|---|
| `idx_trade_code_date` | (ts_code, trade_date) |
| `idx_trade_action` | (action, trade_date) |

---

### 3.3 `trade_signals` — 信号记录

**用途**：记录历史产生的战法信号，用于信号跟踪与后续统计（如命中率）。

**写入时机**：信号检测流程；API 扫描

**字段（8）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `signal_date` | TEXT | NOT NULL | 信号日期 |
| `signal_type` | TEXT | | 信号类型（B1/B2/S1 等） |
| `signal_score` | REAL | | 信号评分 |
| `signal_price` | REAL | | 信号触发时价格 |
| `processed` | INTEGER | | 是否已处理 |
| `created_at` | TEXT | | 创建时间 |

**索引**：`idx_signal_code_date (ts_code, signal_date)`、`idx_signal_type (signal_type, signal_date)`

---

## 四、自我改进系统表

> 这一组表（`*_self` 后缀）构成项目的 **Darwin 自优化闭环**：跟踪 → 记录 → 复盘 → 调参。
> 建表 DDL 另存于 `modules/tracking_tables.sql`，由 `init_tracking_tables()` 执行。

### 4.1 `tracking_pool_self` — 跟踪池

**用途**：被主动跟踪的股票池及其跟踪状态。

**字段（11）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 股票代码 |
| `name` | TEXT | | 股票名称 |
| `add_date` | TEXT | NOT NULL | 加入日期 |
| `remove_date` | TEXT | | 移出日期 |
| `status` | TEXT | | 状态（如 active） |
| `track_reason` | TEXT | | 跟踪理由 |
| `strategy_tags` | TEXT | | 策略标签 |
| `notes` | TEXT | | 备注 |
| `created_at` / `updated_at` | TEXT | | 创建 / 更新时间 |

**索引**：`idx_tracking_pool_self_code (ts_code)`、`..._status (status)`、`..._add_date (add_date)`

---

### 4.2 `tracking_records_self` — 逐日跟踪快照（34 字段）

**用途**：对跟踪池内股票**每日**保存一份「行情 + 全套指标 + 形态 + 判定」快照，为月度复盘提供原始数据。

**字段（34）**

| 分类 | 字段 | 说明 |
|---|---|---|
| **行情** | `ts_code` `trade_date` `open` `high` `low` `close` `vol` `pct_chg` `amount` | 当日 OHLCV |
| **指标** | `j_value` `k_value` `d_value` | KDJ |
| | `bbi` | BBI |
| | `macd_dif` `macd_dea` `macd_hist` | MACD |
| | `rsi_6` `wr_6` | RSI / WR |
| | `boll_upper` `boll_mid` `boll_lower` | BOLL |
| | `vol_ratio` | 量比 |
| **形态** | `is_brick_red` `is_brick_green` `brick_count` | 砖形图 |
| | `is_n_structure` | N 形结构 |
| | `is_double_gun` | 双枪 |
| **判定** | `signal_type` `signal_score` `signal_reason` | 信号类型 / 评分 / 理由 |
| | `stage` `stage_confidence` | 所处阶段（如麒麟会四阶段）与置信度 |
| **元数据** | `id` (PK)、`created_at` | |

**索引**：`..._code (ts_code)`、`..._date (trade_date)`、`..._signal (signal_type)`

---

### 4.3 `monthly_reviews_self` — 月度复盘

**用途**：按月汇总跟踪结果，生成复盘结论与经验教训。

**字段（20）**

| 分类 | 字段 | 说明 |
|---|---|---|
| **主键/维度** | `id` (PK)、`review_month`、`ts_code` | 复盘月份 + 股票 |
| **期初** | `start_price` `start_j_value` `start_signal` | 月初价格 / J 值 / 信号 |
| **期末** | `end_price` `end_j_value` `end_signal` | 月末价格 / J 值 / 信号 |
| **绩效** | `monthly_return` `max_drawdown` `max_gain` | 月收益 / 最大回撤 / 最大涨幅 |
| **信号统计** | `buy_signals_count` `sell_signals_count` | 买卖信号数 |
| | `correct_buy_signals` `correct_sell_signals` | 正确信号数 |
| **文本结论** | `review_summary` | 复盘总结 |
| | `lessons_learned` | 经验教训 |
| | `strategy_adjustments` | 策略调整建议 |
| **元数据** | `created_at` | |

**索引**：`..._month (review_month)`、`..._code (ts_code)`

---

### 4.4 `strategy_performance_self` — 策略绩效

**用途**：按月、按策略名统计信号准确率与收益表现，驱动 `self_optimizer` 的参数调整决策。

**字段（17）**

| 分类 | 字段 | 说明 |
|---|---|---|
| **维度** | `id` (PK)、`strategy_name`、`review_month` | 策略名 + 月份 |
| **信号统计** | `total_signals` `correct_signals` `accuracy_rate` | 总数 / 正确数 / 准确率 |
| **收益** | `avg_return` `max_return` `min_return` | 平均 / 最大 / 最小收益 |
| | `win_rate` | 胜率 |
| **风险** | `avg_drawdown` `max_drawdown` | 平均 / 最大回撤 |
| | `sharpe_ratio` | 夏普比率 |
| **文本** | `strengths` `weaknesses` `adjustments` | 优势 / 不足 / 调整建议 |
| **元数据** | `created_at` | |

**索引**：`..._name (strategy_name)`、`..._month (review_month)`

---

## 五、运维日志表

### 5.1 `sync_log` — 数据同步日志

**用途**：**增量同步的断点依据**。`sync_daily_kline` 读取本表 `last_date`，从其次日开始同步；同步失败也记录一条 status=failed。

**写入时机**：每次 `sync_*` 操作（成功或失败）

**字段（7）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `data_type` | TEXT | NOT NULL | 数据类型（daily_kline / stk_factor 等） |
| `ts_code` | TEXT | | 股票代码 |
| `last_date` | TEXT | | 最后同步日期 |
| `status` | TEXT | | success / failed |
| `message` | TEXT | | 失败信息或其他说明 |
| `created_at` | TEXT | | 记录时间 |

**索引**：无额外索引（按 `data_type` + `ts_code` 查询）

---

### 5.2 `llm_response_log` — LLM 调用日志

**用途**：记录每次 LLM 调用的耗时与成败，用于可观测性与成本统计。

**写入时机**：`record_llm_response()`；统计接口 `get_llm_response_stats()`

**字段（8）**

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK | 自增主键 |
| `ts_code` | TEXT | NOT NULL | 关联股票代码 |
| `request_date` | TEXT | NOT NULL | 请求日期 |
| `model` | TEXT | NOT NULL | 模型名称 |
| `response_time_ms` | REAL | NOT NULL | 响应耗时（毫秒） |
| `success` | INTEGER | | 是否成功 |
| `error_message` | TEXT | | 错误信息 |
| `created_at` | TEXT | | 创建时间 |

**索引**：`idx_llm_log_code_date (ts_code, request_date)`、`idx_llm_log_date (request_date)`、`idx_llm_log_model (model, request_date)`

---

## 六、数据流向

```
外部行情源（hithink / Tushare / Indevs / 免费源 / bridge）
        │
        │ ① zt sync（主动批量，绑定 Tushare 源）
        │ ② DB-first miss 写回（被动，任意源）
        ▼
   ┌─────────────────────────────────────────┐
   │  daily_kline      moneyflow             │
   │  financial_data   stock_basic           │  ← 原始数据层
   └─────────────────────────────────────────┘
        │
        │ analyze_stock() 30 步管线
        ▼
   ┌─────────────────────────────────────────┐
   │  indicator_cache（64 字段，本地自算）      │  ← 衍生缓存层
   │  tushare_indicator_cache（官方值，对拍）   │
   └─────────────────────────────────────────┘
        │
        ├──► strategies.detect_all_strategies() ──► trade_signals
        ├──► screener / backtest / simulator（内存计算，不落库）
        └──► 自我改进闭环
                 tracking_pool_self → tracking_records_self
                        → monthly_reviews_self → strategy_performance_self
                        → self_optimizer（参数调整）

   运维旁路：sync_log（同步断点）  llm_response_log（LLM 调用）
```

### 表与命令对照

| 表 | 写入命令 / 触发点 |
|---|---|
| `daily_kline` | `zt sync sync`；任意分析/选股/监控的取数 miss |
| `moneyflow` | `sync_moneyflow()` |
| `financial_data` | `sync_daily_basic()` |
| `stock_basic` | `sync_stock_basic()` |
| `indicator_cache` | `analyze_stock()` 自动写；`zt sync sync --indicators` 批量 |
| `tushare_indicator_cache` | `zt sync stk-factor` |
| `watchlist` | `zt watchlist add`；API `POST /watchlist/` |
| `trade_records` | `zt trade add`；API `POST /trade/` |
| `trade_signals` | 信号检测流程 |
| `tracking_*_self` | `zt track` 系列 |
| `monthly_reviews_self` | 月度复盘生成 |
| `strategy_performance_self` | 绩效统计 |
| `sync_log` | 每次同步自动写 |
| `llm_response_log` | 每次 LLM 调用自动写 |

---

## 附：查询示例

```bash
# 查看所有表
sqlite3 data/stock_data.db ".tables"

# 查看表结构
sqlite3 data/stock_data.db "PRAGMA table_info(daily_kline);"

# 统计各表行数
sqlite3 data/stock_data.db "SELECT name FROM sqlite_master WHERE type='table';" | \
  while read t; do echo -n "$t: "; sqlite3 data/stock_data.db "SELECT COUNT(*) FROM $t;"; done
```

Python 方式（推荐，自动应用 WAL 与项目约定）：

```python
from modules.database import get_connection

with get_connection() as conn:
    rows = conn.execute("SELECT COUNT(*) FROM daily_kline").fetchone()
    print(rows[0])
```
