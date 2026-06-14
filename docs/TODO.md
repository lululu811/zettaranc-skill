# TODO

> Zettaranc Skill 待办清单
> 更新日期：2026-06-07
> 当前版本：v3.1.0
> 状态：✅ 已完成 / ⏳ 进行中 / 📋 待规划

---

## ✅ 已完成（v3.0.0 编排模式）

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
| **v4.0.0** | 少妇模拟器完整版（自动择时+选股+买入+卖出闭环回测） | 🎯 长期目标 |

---

## 下一迭代候选（v3.2.0 候选）

- CI 观察期 4 个 job 改为 required（lint / quality-gate / e2e-realdata / pre-commit）
- 真实数据 diff 阈值收紧到 2%
- SKILL.md 拆分（32K 字 → 6 心智模型独立文件 + 30 启发式索引）
- 活跃市值 +4%/-2.3% 量化层（需指南针数据源）
- P3 指标集成到 screener（蜈蚣图作为风险扣分项、沙漏评分作为选股加分项）
