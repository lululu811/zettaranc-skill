# 配置指南

> 所有配置项均通过 `.env` 文件管理，复制 `.env.example` 后按需修改。

---

## 核心配置

### 数据模式

```ini
DATA_MODE=jnb
```

| 值 | 说明 | 依赖 |
|---|------|------|
| `jnb` | 接入真实行情数据 | 配置 `TUSHARE_TOKEN` + `TUSHARE_API_URL` 数据最全；零配置时默认走 a-stock-data 免费源（v4.1.0 新增） |
| `websearch` | 纯 LLM 对话模式，不走行情接口 | 无需 Tushare 配置 |

---

## 数据层配置（仅 jnb 模式）

### Tushare API

```ini
TUSHARE_TOKEN=你的token
TUSHARE_API_URL=https://api.waditu.com/dataapi
TUSHARE_VERIFY_TOKEN_URL=
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `TUSHARE_TOKEN` | 否（jnb 建议） | Tushare Pro Token，在 https://tushare.pro/user/token 获取 |
| `TUSHARE_API_URL` | 否（jnb 建议） | 中转 API **基础路径**，见下方说明 |
| `TUSHARE_VERIFY_TOKEN_URL` | 否 | 实时行情验证地址，一般不需要 |

**注意**：如果 `DATA_MODE` 不是 `jnb`，这些配置可以为空，程序不会报错；jnb 模式下未配置 Token 时会自动回退 a-stock-data 免费数据源（腾讯/百度/东财/通达信，无需 API Key）。

#### `TUSHARE_API_URL` 的关键约束（易踩坑）

该变量是**基础路径**，不是完整端点。tushare SDK 会自动在其后追加 `/{接口名}`：

```python
# tushare/pro/client.py:42
res = requests.post(f"{self.__http_url}/{api_name}", json=req_params, ...)
#                      ↑ 示例：{TUSHARE_API_URL}/daily
```

| 地址 | 结果 | 原因 |
|------|------|------|
| `https://api.waditu.com/dataapi` | ✅ **推荐** | Tushare 官方运营中转，路径式，接受官方 token |
| `https://api.tushare.pro` | ❌ 404 | 官方端点只在**根路径**接受 POST（接口名放请求体），被追加 `/daily` 后 404 |
| `https://tt.xiaodefa.cn` | ❌ 40101 | 历史文档示例，需**该服务专用 token**，不接受官方 token |

> SDK 默认值本身也是路径式（`http://api.waditu.com/dataapi`），印证了这个语义。

**验证配置是否生效**：

```bash
zt sync status     # 配置错误会报 [CONFIG_MISSING]；正常则显示数据库统计
```

---

## 数据源优先级（`auto` 模式）

`DATA_MODE=jnb` 时，`CompositeDataSource` 按 token 感知自动降级，**配了 key 的源自动排在前面**：

| 优先级 | 数据源 | 启用条件 | 说明 |
|---|---|---|---|
| 1 | **hithink**（同花顺官方） | 配 `HITHINK_FINANCE_API_KEY` | v4.2.0 起，官方 A 股数据 |
| 2 | **indevs** | 配 `INDEVS_API_KEY` | Tushare Pro Replay API |
| 3 | **Tushare Pro** | 配 `TUSHARE_TOKEN` | 标准 Pro 接口 |
| 4 | **a-stock-data** | 无需 key | 免费源（腾讯/百度/东财/通达信） |
| 5 | **tushare-data-bridge** | 配 bridge 环境变量 | HTTP 缓存代理 |
| 6 | **本地 SQLite** | 库中有数据 | 离线兜底 |

```ini
# 同花顺官方金融数据服务（可选，优先级最高）
# Key 获取: https://fuyao.aicubes.cn/admin
HITHINK_FINANCE_API_KEY=sk-fuyao-xxxx
HITHINK_FINANCE_API_URL=https://fuyao.aicubes.cn

# Indevs Tushare Replay API（可选）
# 文档: https://ai-tool.indevs.in/quant/tushare-pro-catalog/
INDEVS_API_KEY=your_api_key
INDEVS_API_URL=https://ai-tool.indevs.in/tushare/pro
```

> **数据缺失时的行为**：任一数据源缺 key 或调用失败时，程序按上表继续降级，**不会编造价格或信号**，而是明确报告当前数据状态。

---

## 回测实现切换（Rust ↔ Python）

回测热路径有一层 Rust 计算核（`rust/` workspace，PyO3 桥接）。通过环境变量控制：

```ini
ZETTARANC_BACKTEST_IMPL=rust
```

| 值 | 行为 |
|---|---|
| `rust`（默认） | 强制走 Rust 计算核，导入失败会报错 |
| `python` | 强制走纯 Python 实现，用于排查 Rust 回归 |
| `auto` | Rust 可用则用 Rust，否则静默回退 Python |

> ⚠️ `auto` 的降级是**静默的**，容易掩盖 Rust 侧回归。怀疑回测结果异常时，先用 `ZETTARANC_BACKTEST_IMPL=python` 对比。Rust 核需另行构建：`cd rust/crates/bindings && maturin develop --release`。

---

## LLM 配置（可选）

```ini
LLM_API_KEY=你的API密钥
LLM_BASE_URL=https://api.minimaxi.com/v1/chat/completions
LLM_MODEL=MiniMax-M3
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | **否** | 未配置时，系统只做意图识别+知识库检索，不生成回答 |
| `LLM_BASE_URL` | 否（有 Key 时填） | OpenAI 兼容格式的 API 地址 |
| `LLM_MODEL` | 否（有 Key 时填） | 模型名称，默认 `MiniMax-M3` |

**支持的 LLM 提供商**：目前支持 OpenAI 兼容格式的 API（MiniMax、OpenRouter、通义千问等）。

---

## 向量知识库配置（可选，默认关闭）

```ini
# KB_ENABLED=true  # 取消注释以启用
# KB_API_URL=http://localhost:8000
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KB_ENABLED` | `false` | 设为 `true` 开启向量知识库检索 |
| `KB_API_URL` | `http://localhost:8000` | 知识库 API 地址（参考 knowledge-base 项目） |

**知识库依赖**：
- Qdrant 向量数据库（localhost:6333）
- Ollama Embedding 模型（localhost:11434）
- FastAPI 知识库服务（localhost:8000）

**未开启知识库时的行为**：
- 意图识别 ✅ 正常
- 角色框架 ✅ 正常（career/life 用本地 prompt 文件）
- LLM 生成 ✅ 正常（配置了 Key 的话）
- 知识库检索 ❌ 跳过（不影响其他功能）

---

## 数据库配置

```ini
DATA_DIR=data
DB_PATH=data/stock_data.db
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATA_DIR` | `data` | 数据目录 |
| `DB_PATH` | `data/stock_data.db` | SQLite 数据库路径，支持绝对/相对路径 |

---

## 配置示例

### 最小配置（纯对话，无需任何外部服务）

```ini
DATA_MODE=websearch
```

### 股票分析模式（推荐：同花顺官方数据源）

```ini
DATA_MODE=jnb
HITHINK_FINANCE_API_KEY=sk-fuyao-xxxx
```

### 股票分析模式（Tushare）

```ini
DATA_MODE=jnb
TUSHARE_TOKEN=你的token
TUSHARE_API_URL=https://api.waditu.com/dataapi
```

### 完整模式（股票 + LLM + 知识库 + Rust 回测）

```ini
DATA_MODE=jnb
TUSHARE_TOKEN=你的token
TUSHARE_API_URL=https://api.waditu.com/dataapi
HITHINK_FINANCE_API_KEY=sk-fuyao-xxxx
LLM_API_KEY=sk-cp-...ULLC
LLM_BASE_URL=https://api.minimaxi.com/v1/chat/completions
LLM_MODEL=MiniMax-M3
KB_ENABLED=true
KB_API_URL=http://localhost:8000
ZETTARANC_BACKTEST_IMPL=rust
```
