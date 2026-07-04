# TODO

> Zettaranc Skill 待办清单
> 更新日期：2026-07-04
> 当前版本：v3.4.0
> 状态：✅ 已完成 / ⏳ 进行中 / 📋 待规划

---

## ✅ 已完成（v3.4.0 少女/少妇模拟器 v0.2）

- [x] A 股真实交易约束、成本模型、动态滑点、ATR 仓位、专业指标
- [x] **A 股交易约束层**：T+1、涨跌停（主板 ±10%、科创/创业板 ±20%、ST ±5%）、停牌、ST 过滤。
- [x] **真实成本模型**：佣金最低 5 元、印花税卖出单向、过户费双向。
- [x] **动态滑点**：基于 ATR 与流动性的自适应滑点，保留固定滑点兼容。
- [x] **ATR 仓位管理**：波动率仓位 + 单笔最大净值占比 + 现金利用率上限。
- [x] **专业回测指标**：年化收益、夏普、Calmar、索提诺、基准对比、胜率、盈亏比、最大连胜/连亏、回撤恢复时间。
- [x] **市场环境增强**：涨跌停家数比、成交额趋势。
- [x] **CLI `zt simulate`** 新增 `--benchmark/--cost-model/--slippage/--atr-sizing/--max-position-pct/--no-st` 等参数。

---

## ✅ 已完成（v3.3.2 DataSource 协议补完）

- [x] **修复 `BridgeDataSource` 全局配置污染**：
  - `BridgeDataSource(config=...)` 不再调用 `set_bridge_config` 修改全局状态。
  - `modules/bridge_client.py` 所有数据接口新增可选 `config` 参数，实例配置与全局配置分离。
- [x] **修复 `TushareDataSource.get_kline_dicts` 空日期字符串**：
  - `TushareClient.get_daily` / `TushareDataSource.get_daily` 的 `start_date` / `end_date` 改为可选参数。
  - 未指定日期时不向 Tushare SDK 传入空字符串。
- [x] **补全 `CompositeDataSource` 文档**：在类 docstring 中明确 bridge/SQLite 回退能力范围。
- [x] **增强 `screen_stocks` 并行安全**：不可 pickle 的 `datasource` 触发 warning 并主动回退串行模式。
- [x] **文档同步**：README / CHANGELOG / TODO 更新至 v3.3.2，`pyproject.toml` 版本号同步。
- [x] **验证**：772 passed / 11 skipped，ruff / mypy 零错误。

---

## ✅ 已完成（v3.3.1 SKILL.md 拆分 + 工程清理）

- [x] **SKILL.md 拆分（Phase 3 重校准）**：
  - 1534 行 → 598 行（-61%），三段大块 SOP 抽到 knowledge/
  - `knowledge/workflow.md`（393 行）：Step 1/1.5/2/3 完整工作流
  - `knowledge/harness.md`（510 行）：Harness 六大部分
  - `knowledge/improvement-system.md`（203 行）：跟踪池 + 复盘 + 优化闭环
  - 每个新文件含 Skill-Runtime 元数据头部
  - 心智模型 / 决策启发式 / 表达 DNA 全部保留在 SKILL.md
- [x] **P0 工程清理**：
  - 删除 `prompts/` 残留目录（6 个不相关 openclaw/playwright 文件）
  - 注册 `@pytest.mark.slow` 标记，消除 PytestUnknownMarkWarning
- [x] **运行时资源索引扩展**：3 个新 knowledge 文件进入 SKILL.md 运行时边界表
- [x] **质量门 + 测试验证**：12/12 通过，723 passed / 11 skipped 无回归

---

## ✅ 已完成（v3.3.1+ 数据层架构重构 — DataSource 协议 + 大模块拆分）

- [x] **统一 DataSource 协议**：新增 `modules/datasource.py`
  - 定义 `DataSource` Protocol（`typing.Protocol` + `@runtime_checkable`）
  - 实现 `TushareDataSource` / `BridgeDataSource` / `SqliteDataSource` / `CompositeDataSource`
  - `get_datasource()` 工厂支持 `auto` / `tushare` / `bridge` / `sqlite`
  - Composite `auto` 策略：bridge → SQLite 回退
- [x] **拆分 `modules/data_sync.py`（1181 行）→ `modules/data_sync/` 包**：
  - `rate_limiter.py` / `indicator_cache.py` / `fetcher.py` / `syncer.py` / `cli.py` / `__main__.py`
  - `DataSyncer` 支持 `datasource` 依赖注入，默认 `get_datasource("tushare")`
  - 保留 `modules/data_sync.py` shim，公共导入 100% 兼容
- [x] **拆分 `modules/screener.py`（1161 行）→ `modules/screener/` 包**：
  - `models.py` / `data.py` / `criteria.py` / `scoring.py` / `engine.py` / `market.py` / `format.py` / `workflow.py` / `cli.py`
  - `get_all_stocks()` / `get_recent_klines()` 支持 `datasource` 注入，默认 `get_datasource()`
  - 保留 `modules/screener.py` shim，公共导入 100% 兼容
- [x] **调用方对齐**：`modules/cli.py` 的 `cmd_sync` 显式注入 `TushareDataSource`
- [x] **修复 pre-existing bug**：`api/routes/system.py` 错误调用 `compute_indicators` → 改为 `sync_indicator_cache`
- [x] **测试覆盖**：新增 `tests/test_datasource.py`、`tests/test_data_sync.py`、`tests/test_screener_data.py`
- [x] **验证**：764 passed / 11 skipped，ruff / mypy 零错误

---

## ✅ 已完成（v3.3.0 Skill-Schema-V2 合规改造）

### Schema 对齐（V2 三表面 + 安全边界）
- [x] YAML frontmatter description 改为路由触发器格式（Load when / Do NOT load / Risk level）
- [x] 新增 路由声明（Routing Surface）：触发条件表格 + 不加载场景 + 优先级规则
- [x] 新增 契约（Contract Surface）：输入契约（5 类输入）、输出契约（5 类任务验收标准）、边界与限制
- [x] 新增 运行时资源索引（Runtime Boundary）：12 知识文件加载时机 + 6 工具链调用条件 + 5 失败退路
- [x] 新增 安全边界（Safety Surface）：高风险动作规则 + 人类确认点（3 个必须停下来的场景）+ 禁区（6 条绝对红线）+ 版本追踪
- [x] 质量门升级：新增 4 项 V2 表面检查（路由/契约/运行时/安全），12/12 全通过

### 知识文件补完
- [x] 23 个 knowledge/*.md 添加 Skill-Runtime 元数据头部（加载时机 + 用途 + 大小）

---

## ✅ 已完成（v3.2.0 P3 指标接入 screener + 数据层整合）

### 编排模式与角色扩展
- [x] 用户问题自动路由到对应模块（股票/投资、人生/职业决策、创业/商业判断）
- [x] 核心心智模型扩展 +3（人生四圈框架、职业发展四层模型、时代主线判断）
- [x] 知识文件扩展 +3（life-decision.md、career-development.md、business-judgment.md）
- [x] 决策启发式扩展 +14 条（人生/职业决策 +10、创业/商业判断 +4）
- [x] 蒸馏流程执行：采集 499 个语料文件，提取 9 个核心模型，三重验证通过
- [x] 路由逻辑测试用例 +15 个

---

## ✅ 已完成（v2.10.0 工程质量）

### CLI 修复与统一入口
- [x] 修 3 个必修 CLI bug（cmd_screen 字段错位 / cmd_watchlist scan key 不匹配 / 11 种 strategy 中文别名映射）
- [x] 6 业务脚本薄壳化（3623 → 203 行，-94%）
- [x] 5 个独立 main() 合并到 zt 统一入口（7 个顶层命令 + 9 个子动作）
- [x] 6 语料脚本迁 `corpus/`

### CI 与质量护栏
- [x] 5 个 CI job（test / lint / quality-gate / e2e-realdata / pre-commit）
- [x] SKILL.md 质量门接 CI（`corpus/quality_check.py --json --strict`）
- [x] pre-commit 钩子（ruff + mypy + 质量门 + 标准文件检查）
- [x] 真实数据回归（600519.SH × MACD/KDJ/RSI vs stk_factor）
- [x] 限流升级 multiprocessing 安全（token bucket + 滑动窗口）

### 测试覆盖
- [x] 测试从 264 → 367 passed, 10 skipped
- [x] 新增 5 个测试文件（cli_screen / cli_subparser / data_sync_extensions / rate_limiter / indicators_realdata / quality_check）
- [x] trade_parser（53）、tushare_client（27）、report（54）三模块从零覆盖

### 代码审查
- [x] 源码 bug 修复（`_fmt_opt` 缺 `sign` 参数 + `render_assessment` f-string 语法错误）
- [x] 移除 `zettaranc_voice.py`（-492 行），常量迁移至 `trade_reviewer.py`
- [x] 死代码清零 + NameError 修复 + 硬编码路径清零

---

## ✅ 已完成（v2.9.0 性能与架构优化）

### 性能极限优化
- [x] 指标计算向量化（60x 提速）：Pandas 原生重写 MACD/KDJ/BBI，与通达信精度一致
- [x] SQLite 写入加速（10x-50x）：`executemany` 批量插入替换 `iterrows` 单行插入
- [x] 多线程并发拉取：`ThreadPoolExecutor`（5 并发）+ 线程安全限流锁
- [x] SQLite WAL 模式：解决并发 `Database is locked` 问题

### 策略智能升级（MDC 2.0）
- [x] 多维验证体系：资金流 + 布林带 + DMI 动能加分/权重机制
- [x] 麒麟阶段背景校验：B1/B2 根据吸筹/拉升/派发阶段动态调整置信度
- [x] 资金流深度对齐：S1/长安战法校验主力大单净流入/流出比例
- [x] DMI 趋势过滤：ADX 高位动能竭尽 + DI 趋势金叉验证

### 架构解耦
- [x] `strategies.py`（1700 行）→ `strategies/` 包（6 子模块：core/base/compound/kirin/sell/vectorized）
- [x] 向后兼容：`__init__.py` 保留 API，264 用例 100% 通过

---

## ✅ 已完成（v2.8.0 意图识别编排层）

- [x] 意图识别规则引擎（rules/intent_rules.yaml）
- [x] 四意图路由：stock / career / life / chat
- [x] 向量知识库适配器（modules/knowledge_retriever.py，Qdrant RAG，默认关闭）
- [x] LLM 生成层（MiniMax / OpenAI 兼容，可选）
- [x] Z哥职业决策框架（rules/career_prompt.md）
- [x] Z哥人生决策框架（rules/life_prompt.md）
- [x] 交互式聊天界面（modules/intent_chat.py）
- [x] 配置指南文档（docs/CONFIG_GUIDE.md）

---

## ✅ 已完成（v3.1.0 P3 指标补完）

- [x] **蜈蚣图识别** — `detect_centipede_pattern()` in `modules/indicators/price_patterns.py`
  - 5 因子评分（长上影/长下影/十字星/量能无规律/价格无趋势），≥60 分判定为蜈蚣图
- [x] **牛绳理论量化** — `detect_bull_rope()` in `modules/indicators/price_patterns.py`
  - 基于白线/黄线关系判定：牵牛/牛绳断/金叉/死叉 + 缺口百分比 + 白线趋势
- [x] **量比战法引擎** — `detect_volume_ratio_strategy()` in `modules/indicators/volume_patterns.py`
  - 6 种场景判定（攻击日/出货日/单向拉升/正常震荡/弱势日/超级攻击）
- [x] **沙漏评分 V9** — `calculate_sandglass_score()` in `modules/indicators/price_patterns.py`
  - 5 因子评分（缩量收敛/枢轴邻近/量能斜率/均线结构/事件风险），≥80 分为完美图形

> 测试：523 passed, 10 skipped（新增 ~156 用例）

---

## ✅ 已完成（v3.2.0 P3 指标接入 screener + 数据层整合）

### P3 指标深度接入评分体系
- [x] **量比战法融入 `score_volume_pattern`**：6 场景判定（超级攻击+30/攻击日+25/单向拉升+18/出货日-25/弱势日-15/震荡吸筹+5），降级回简单量比计算
- [x] **沙漏评分融入 `score_b1_opportunity`**：3 因子增强（缩量收敛+10/+5、枢轴邻近+8/+4、完美图形+15/良好+5）
- [x] **CLI choices 补全**：`bull_rope` / `sandglass_perfect` / `volume_ratio_super` 正式可用
- [x] 新增 `tests/test_screener_p3.py`：14 个用例（量比 6 场景 + 沙漏 B1 + 注册表验证）
- [x] 测试：36 passed（原有 22 + 新增 14），0 破坏

### 数据层整合（skill ↔ tushare-data-bridge）
- [x] **新增 `modules/bridge_client.py`**：封装 bridge HTTP API（5 个端点）
  - 3 种运行模式：`auto` / `always` / `never`（`TUSHARE_BRIDGE_ENABLED` 控制）
  - 降级网关：bridge 不通时自动回退到本地 SQLite
- [x] **改造 `modules/screener.py` 数据接入层**：`get_all_stocks()` / `get_recent_klines()` 优先 bridge，失败回退本地
- [x] 新增 `tests/test_bridge_client.py`：20 个用例（配置/健康检查/GET/POST/降级网关）
- [x] 测试：56 passed（screener 36 + bridge 20），0 破坏

---

## ✅ 已完成（v3.3.2 DataSource 协议补完）

- [x] **修复 `BridgeDataSource` 全局配置污染**：
  - `BridgeDataSource(config=...)` 不再调用 `set_bridge_config` 修改全局状态。
  - `modules/bridge_client.py` 所有数据接口新增可选 `config` 参数，实例配置与全局配置分离。
- [x] **修复 `TushareDataSource.get_kline_dicts` 空日期字符串**：
  - `TushareClient.get_daily` / `TushareDataSource.get_daily` 的 `start_date` / `end_date` 改为可选参数。
  - 未指定日期时不向 Tushare SDK 传入空字符串。
- [x] **补全 `CompositeDataSource` 文档**：在类 docstring 中明确 bridge/SQLite 回退能力范围。
- [x] **增强 `screen_stocks` 并行安全**：不可 pickle 的 `datasource` 触发 warning 并主动回退串行模式。
- [x] **文档同步**：README / CHANGELOG / TODO 更新至 v3.3.2，pyproject.toml 版本号同步。
- [x] **验证**：772 passed / 11 skipped，ruff / mypy 零错误。

---

## 📋 待实现

（暂无）

---

## ⏳ 进行中

（暂无）

---

## 版本路线图

| 版本 | 主题 | 状态 |
|------|------|------|
| **v2.4.0** | CLI 工具 + 回测框架 + 递推修复 | ✅ 已完成 |
| **v2.5.0** | P0/P1 指标补全 + 工程化补完 | ✅ 已完成 |
| **v2.6.0** | P2 核心模块（三波理论/麒麟会） | ✅ 已完成 |
| **v2.7.0** | 数据层充实 + SAT/UAT 测试 + 使用手册 | ✅ 已完成 |
| **v2.8.0** | 意图识别编排层 + RAG + 可选 LLM | ✅ 已完成 |
| **v2.9.0** | 性能极限优化（60x/多线程/WAL）+ MDC 2.0 + 架构解耦 | ✅ 已完成 |
| **v2.10.0** | CLI 修复 + 脚本薄壳化 + 5 CI job + 501 测试 + 代码审查 | ✅ 已完成 |
| **v3.0.0** | 编排模式 + 人生/创业蒸馏 + 双维度扩展 | ✅ 已完成 |
| **v3.1.0** | P3 指标补完（蜈蚣图/牛绳理论/量比战法/沙漏 V9） | ✅ 已完成 |
| **v3.2.0** | P3 指标接入 screener + bridge 数据层整合 | ✅ 已完成 |
| **v3.3.0** | Skill-Schema-V2 合规改造 | ✅ 已完成 |
| **v3.3.1** | SKILL.md 拆分 + 工程清理 | ✅ 已完成 |
| **v3.3.2** | DataSource 协议补完 | ✅ 已完成 |
| **v3.4.0** | 少女/少妇模拟器 v0.2（A股真实约束） | ✅ 已完成 |
| **v4.0.0** | 少妇模拟器完整版（自动择时+选股+买入+卖出闭环回测） | 🎯 长期目标 |
