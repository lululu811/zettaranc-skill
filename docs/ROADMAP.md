# 产品路线图

> 最后更新：2026-07-18  
> 当前版本：v4.0.2（CLI ↔ Rust 桥 + 技术债清扫）

## 版本号规定

- **MAJOR**：不兼容 API 变更（心智模型重构、CLI 不兼容变更）
- **MINOR**：向后兼容的功能新增（新战法/指标/CLI 子命令/数据源）
- **PATCH**：bug 修复、技术债清理、内部重构

> 严格遵循语义化版本（Semantic Versioning）。技术债清理属于 PATCH，不是 MINOR。

---

## 2026-07-16 重排说明

本次按代码现状重排迭代路线，原因：

1. **版本号不一致是发布阻塞**：`pyproject.toml` / `skill.json` / `SKILL.md` / README badge 四处版本互相打架，ClawHub 上架与一切正式发布都受影响 → 最先修（v3.10.4）
2. **告警基础设施已存在**：`modules/monitor.py` + `modules/notifier.py` 已实现自选股信号扫描与飞书推送，监控告警是"收尾"而非"新建"，成本低价值直接 → 先于分钟级数据
3. **分钟级数据有外部依赖不确定**：Tushare 分钟线接口需要高权限 token，能否可用未验证 → 先 spike 再排期
4. **传播产物依赖功能稳定 + 版本一致** → 与 v3.11.x 并行推进
5. **原「v4.0.0 Web 看板增强」非破坏性变更**，按 semver 规则应为 MINOR → 重编号为 v3.13.0；v4.0.0 保留给真正 MAJOR 的自动化交易接口

---

## 近期（0–2 个月）

### v4.0.1 PyO3 运行时打通（PATCH）✅

**目标**：v4.0.0 留尾 —— 在 macOS 跑通 PyO3 + 加固算法测试

**已完成**（本轮）：
- [x] macOS Mach-O LINKEDIT 链接器 bug workaround（`fix_linkedit_alignment.py` + lld 22 配置 + build_macos.sh 一键脚本）
- [x] 3 个 PyO3 backtest bindings 落地（Task 15/18/20）：单策略/组合/网格搜索
- [x] 35 个 proptest 属性测试（5 个 crate × 8 个 invariant）
- [x] `cargo test --workspace --release` 59/59 通过（含 atr_golden byte-equal）
- [x] `pytest tests/test_rust_compat.py` 5/5 通过（之前 4/5 因 linker 失败）
- [x] Linux Docker fallback 文件就位

**向后兼容**：
- 默认行为：`_core_compute` 已能 dlopen，所有 binding 函数可用
- env-var `ZETTARANC_BACKTEST_IMPL=python` 仍可秒级回退
- 工具链 bump 到 Rust stable（lld 22 必需）

**待接入**（下一波）：
- [ ] 接入 CLI（`zt backtest` / `zt verify` / `zt screen`）触发 Rust 实现
- [ ] benchmark 实测（≥8× / ≥10× / ≥30× / ≥5×）
- [ ] python `_core_compute` 包管理（PyPI 发布？）

详见 `docs/superpowers/specs/2026-07-18-env-blocker-recovery.md`

### v3.10.4 技术债与文档收尾（PATCH）✅

**目标**：发布前止血——版本一致、文档追平、热点路径提速、错误处理有最小骨架

**功能清单**：
- [x] 版本号五处统一（pyproject / skill.json / SKILL.md×2 / README badge）+ 发布 Checklist（`docs/CONTRIBUTING.md`）
- [x] `docs/USER_GUIDE.md` 追平 v3.8–v3.10 功能
- [x] 性能优化：`precompute_market_contexts()` ~6.3x + `get_kline_dicts_batch()` ~2.2–2.4x（benchmark 指纹校验逐位一致）
- [x] 统一错误码最小版（`modules/core/errors.py`，试点 tushare_client / datasource）
- [x] 鲁班 P0 复核 + knowledge 索引修正

**实际工期**：1 天

---

### v3.11.0 监控告警闭环（MINOR）

**目标**：在现有 monitor/notifier 基础上收尾告警能力

**功能清单**：
- [ ] 止损/止盈触发告警（`trade_records` 持仓成本 + 最新价比对）
- [ ] 市场环境变化告警（regime 切换检测，STRONG → WEAK 等）
- [ ] 告警频率控制（冷却窗口 + 按级别去重）
- [ ] 邮件推送通道（`notifier.py` 扩展 SMTP）
- [ ] 自选股 B1/B2 信号监控（已有，补测试与文档）

**预计工期**：1 周

---

### v3.11.1 数据质量检查（MINOR）

**目标**：自动检测数据缺失、异常值

**功能清单**：
- [ ] 交易日数据缺失检测
- [ ] 价格跳变/成交量异常检测
- [ ] 自动重新拉取修复

**预计工期**：1 周

---

### 里程碑 M1：传播产物（与 v3.11.x 并行，非版本发布）

**目标**：把"独一份"的内在优势变成"看得见"的传播资产（鲁班打磨报告方案 B）

**功能清单**：
- [ ] 3 个展示产物：`zt analyze` 输出、`zt screen` 结果、`zt backtest` 资金曲线（GIF/截图，入 `assets/`）
- [ ] 一张可截图分享的「结果卡片」
- [ ] `test-prompts.json`（10 个典型场景，降低新用户开口成本）
- [ ] README 首屏重排：钩子 → 30 秒 websearch 体验 → 效果截图 → 完整安装

**预计工期**：3–5 天

---

## 中期（3–6 个月）

### v3.12.0 分钟级实时数据（MINOR）

**目标**：接入分钟级 K 线（1/5/15/30/60 分钟）

**前置 spike（2 天）**：
- [ ] 验证 Tushare 分钟线接口在当前 token 权限下是否可用
- [ ] 验证 Indevs Replay API 是否支持分钟级
- [ ] 结论不可行则降级为"盘中快照轮询"方案或取消（标注 ❌ 并说明原因）

**功能清单**：
- [ ] `minute_kline` 表设计 + 5 种分钟级别数据写入 DB
- [ ] 盘中信号检测

**预计工期**：spike 2 天 + 1–2 周

---

### 里程碑 M2：生态上架（非版本发布）

**功能清单**：
- [ ] ClawHub / skills.sh 上架（`skill.json` 元数据已随 v3.10.4 修正）
- [ ] 社区入口：issue 模板、联系方式

**预计工期**：2–3 天

---

### v3.13.0 Web 看板增强（MINOR，原"v4.0.0"重编号）

**目标**：`frontend/` 增加完整功能

**功能清单**：
- [ ] 策略回测可视化（资金曲线、交易记录）
- [ ] 持仓管理（当前持仓、历史交易）
- [ ] 信号实时推送
- [ ] 自定义策略参数 + 市场环境展示

**预计工期**：3–4 周

---

## 长期（6–12 个月）

### v4.0.0 自动化交易接口（MAJOR，合规前置）

**功能清单**：
- [ ] 券商 API 对接
- [ ] 风控检查（仓位、资金、黑名单）
- [ ] 下单前确认 + 交易日志

**风险提示**：⚠️ 需合规审查 · ⚠️ 需用户授权 · ⚠️ 需资金安全保障

**预计工期**：4–6 周

---

### v4.1.0 策略市场

**功能清单**：
- [ ] 策略上传/分享/评分/排名
- [ ] 一键导入 + 回测对比

**预计工期**：3–4 周

---

## 技术债务

> 最后盘点：2026-07-18（v4.0.1 release 后）  
> 数据基线：脚本扫描 `modules/` 全部 `.py` + `cargo build --workspace --release` warning 统计

### 🔴 高优先级（影响运行时 / 当前已积累）

| # | ID | 项目 | 量化 | 影响 | 估算 |
|---|---|---|---|---|---|
| H1 | cli-rust | **CLI 接入 Rust 实现** | 5 个 binding 可调，但 `zt backtest/screen/verify` 仍走 Python | 用户跑命令拿不到 Rust 加速 | 1-2 天 |
| H2 | rust-warnings | **Rust backtest_engine 8 个 dead-code warning** | `cash`/`held_days`/`total_pnl` 等 assignment 不读 | 掩盖逻辑 bug + review 噪音 | 半天 |
| H3 | silent-except | **120 静默 except + 107 magic number 集中 5 文件** | `data_sync/syncer.py`(8) `tracking_manager.py`(7) `simulator/narrator.py`(7) `tracking_syncer.py`(6) `review_generator.py`(6) | 失败排查困难 + 配置漂移 | 1-2 天 |

### 🟡 中优先级（ROADMAP ⏳ 项 + 仍可推）

| # | ID | 项目 | 量化 | 估算 |
|---|---|---|---|---|
| M1 | error-code | **统一错误码扩张** | 7 模块已试点（v3.10.4：`tushare/datasource/cli/data_sync/position_manager/self_optimizer/verify`），剩 ~15 模块 | 1-2 天 |
| M2 | none-silent | **`return None` 收敛** | 193 处，集中在 `indevs_client` (84-201) / `tushare_client` / `datasource` / `strategies/sell_signals` / `loop_engine` | 1-2 天 |
| M3 | pyo3-upgrade | **PyO3 0.22 → 0.23** | 解锁 Python 3.14 + 减少 silent import 风险 | 1 天 |
| M4 | except-narrow | **`except Exception` 不带 raise 收敛** | 121 处 | 1 天 |
| M5 | type-annot | **mypy 启用 + 函数返回注解补缺** | 当前 528/563 (93%) 已有 → 全量 + mypy strict | 2-3 天 |

### 🟢 低优先级（结构性 / 改进型）

| # | ID | 项目 | 备注 |
|---|---|---|---|
| L1 | cdylib-test | Cargo `[[test]]` 不能链 cdylib | 需 maturin-driven 集成测试；现用 byte-equal golden test workaround |
| L2 | py-upgrade | Python 3.10 → 3.12 | classifier 已声明 |
| L3 | pandas-upgrade | pandas 版本升级 | DataFrame 行为兼容风险 |
| L4 | ci-deploy | CI/CD 自动化部署 | 现仅 Lint+test |
| L5 | doc-coverage | Docstring 覆盖率 80% → 90% | 缺 109/563 public 函数 |
| L6 | magic-lit | 重复 magic literal（0.05/0.10/0.20 等）107 处 | 提取到 `modules/constants.py` |

### 🌐 跨平台 / 兼容性

| # | ID | 项目 | 状态 |
|---|---|---|---|
| C1 | macos-linkedit | macOS LINKEDIT 链接器 bug | ✅ 已用 post-build workaround（fix_linkedit_alignment.py + lld 22）解决 |
| C2 | linux-docker | Linux Docker fallback | ✅ `rust/Dockerfile.test` + `rust/scripts/build-linux.sh` |
| C3 | windows | Windows 验证 | 未验证；未列入测试 |

### ✅ 已偿还（历史归档）

| # | ID | 完成 |
|---|---|---|
| ~~D1~~ | 文档完善 | ✅ v3.10.4（USER_GUIDE 追平、发布 Checklist） |
| ~~D2~~ | 性能优化 | ✅ v3.10.4（`precompute_market_contexts` ~6.3×、`get_kline_dicts_batch` ~2.2–2.4×） |
| ~~D3~~ | Rust 内核迁移 | ✅ v4.0.0（5 个算法 crate + 22 测试）+ v4.0.1（PyO3 runtime 打通 + 59 测试） |
| ~~D4~~ | macOS LINKEDIT | ✅ v4.0.1（post-build workaround） |
| ~~H1~~ | CLI 接 Rust | ✅ v4.0.2（`modules/backtest/_rust_bridge.py` + `compute_func` helper，16 个新测试） |
| ~~H2~~ | Rust dead-code 清理 | ✅ v4.0.2（`zt_backtest_engine` 8 warnings → 0） |
| ~~H3~~ | 静默 except 收敛 | ✅ v4.0.2（5 hot files 33+ 处 except narrow + 25 个新测试） |
| ~~M1~~ | 错误码扩张 | ✅ v4.0.2（5 模块：indevs / llm / screener / simulator / backtest，加 11 个 ErrorCode） |
| ~~M2~~ | return None 收敛 | ✅ v4.0.2（24 处 raise 化 + 9 处 Optional 保留"已审视"） |
| ~~L5~~ | docstring 覆盖率 | ✅ v4.0.2（80.6% → **100%**，109 个新 docstring，跨 17 文件） |
| ~~L6~~ | magic literal 提取 | ✅ v4.0.2（`modules/constants.py` 28 个命名常量，55 处替换；剩余 53 处为战法语义/形态评分/数学常数，已逐一审视） |

---

## 历史阶段归档

### 阶段一：多策略融合（v3.10.x）✅ 已全部完成

- **v3.10.0 多策略融合引擎** ✅：`PortfolioBacktestEngine` 从 B1-only 改造为 B1 + B2 + SB1 + 长安并行检测
- **v3.10.1 动态止损策略** ✅：固定百分比止损 → ATR 动态止损 + 移动止损（`core/atr.py`）
- **v3.10.2 市场环境自适应参数** ✅：Walk-forward IS/OOS 网格搜索自动寻优（81 组合）
- **v3.10.3 验收补齐** ✅：`regime_strategy_weights` 环境动态调权 + `StrategyStats` 策略贡献度统计

---

## 版本发布记录

### v3.10.4 (2026-07-16) ✅
- 技术债与文档收尾：版本号五处统一、USER_GUIDE 追平（1388 行）、precompute_market_contexts ~6.3x + get_kline_dicts_batch ~2.2–2.4x、统一错误码最小版、鲁班 P0 复核
- 12 个新测试，全量 1179 passed

### v3.10.3 (2026-07-15) ✅
- 多策略融合引擎验收补齐：regime_strategy_weights 按环境动态调权
- LoopTrade.strategy_source 记录触发策略（支持多策略共振）
- StrategyStats + PortfolioBacktestResult.strategy_stats 贡献度统计
- 13 个新测试，全量 1167 passed

### v3.10.2 (2026-07-11) ✅
- 组合回测 IS/OOS 自动寻优（grid search 81 组合）

### v3.10.1 (2026-07-11) ✅
- ATR 动态止损 + 移动止损（trailing stop）

### v3.10.0 (2026-07-11) ✅
- 多策略融合引擎（B1/B2/SB1/长安 并行检测 + 综合评分排序）

### v3.9.0 (2026-07-11) ✅
- 技术债清理（地基工程）
- 统一 PerformanceMetrics / MarketRegime / 常量 / 路径
- 修复 backtest 架构问题
- 测试 1097 passed, 15 skipped

### v3.8.2 (2026-07-11) ✅
- 数据层 DB 优先读取架构改造

### v3.8.1 (2026-07-11) ✅
- Indevs Tushare Replay API 数据源接入

### v3.8.0 (2026-07-11) ✅
- 市场环境自适应择时（最小可用版）

### v3.7.7 (2026-07-11) ✅
- 组合级 Walk-forward 真切片

### v3.7.6 (2026-07-11) ✅
- 多指标分组选股池 + 组合回测引擎

---

## 维护说明

1. **更新频率**：每完成一个版本，更新「版本发布记录」
2. **状态更新**：开始开发时 ⏳ → 🚧；完成时 → ✅
3. **优先级调整**：根据用户反馈和市场变化调整
4. **新增需求**：在对应阶段添加，标注 ⏳
5. **取消功能**：标注 ❌ 并说明原因

---

> 💡 **提示**：这份路线图是活文档，会随着项目进展不断更新。
