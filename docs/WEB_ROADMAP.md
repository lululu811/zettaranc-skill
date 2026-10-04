# zettaranc-skill → Web 应用 改造规划

> 目标：把现有的 CLI / Agent Skill 改造成**纯开源、可本地部署、支持多知识库 + 多 LLM 的个股问答 Web 应用**。
>
> 版本：v1.0 规划 ｜ 2026-09-06 ｜ 基于当前仓库状态（v4.3.1-pre-slim, 518 tracked files）

---

## 0. 现状盘点：你手上已经有什么

这一节很重要 —— 改造不是从零开始，你已有的资产比缺口大得多。

### 0.1 已有资产（可直接复用）

| 层 | 资产 | 状态 | 规模 |
|---|---|---|---|
| **数据层** | `data/stock_data.db` SQLite | ✅ 完整可用 | daily_kline **179,654** 行 / stock_basic **5,525** 只 / moneyflow **207,361** 行 / indicator_cache **26,400** 行 |
| **算法层** | `modules/` 38 个模块 | ✅ 成熟 | a_stock_data_client、datasource（48KB）、backtest_six_step、indicators/、core/、market_regime、position_manager… |
| **API 层** | `api/` FastAPI | ✅ 9 个路由域 | stock / screen / watchlist / diagnosis / backtest / simulator / trade / system / commentary |
| **前端** | `frontend/` React 19 + TS | ✅ 7 个页面 | Dashboard / StockAnalysis / Screener / Watchlist / Trades / Backtest / Simulator / Settings |
| **前端栈** | Vite 8 + Tailwind 4 + ECharts 6 | ✅ 现代 | zustand + react-query + react-router 7，已有 lazy 分包 |
| **知识文件** | `knowledge/*.md` | ⚠️ 裸 Markdown | 29 个文件（trading-core、indicators、sell-discipline、life-decision…） |
| **人格体系** | `SKILL.md` + `rules/` + `corpus/` | ✅ 成熟 | 200 万字语料蒸馏，Z 哥口吻、44 条启发式、四圈框架 |
| **意图路由** | `modules/intent_router.py` | ⚠️ 实验性 | 规则匹配（<1ms 零 token）+ YAML 规则库 |
| **LLM 调用** | `modules/llm_providers.py` | ❌ 需重构 | 只有 `MiniMaxProvider` 一个类，硬编码 OpenAI 兼容格式 |
| **开源卫生** | `.gitignore` + LICENSE(MIT) + remote | ✅ 基本就绪 | .env / *.db / references/sources/ 均未入库 |

### 0.2 四个缺口（本次改造的全部工作量）

| # | 缺口 | 现状 | 影响 |
|---|---|---|---|
| **G1** | **无向量检索** | `knowledge/*.md` 是纯文本，无索引、无 embedding；`KnowledgeRetriever` 依赖**外部** `KB_API_URL` 服务且默认关闭（`KB_ENABLED=false`） | 知识库等于不存在 |
| **G2** | **LLM 不可配置** | 只有 MiniMax 一家，硬编码 `DEFAULT_BASE_URL` / `DEFAULT_MODEL` | 违背"可配置多 LLM" |
| **G3** | **无问答/会话层** | 9 个路由里没有 chat/ask；`llm_response_log` 表已建但 **0 行** | 核心场景缺失 |
| **G4** | **无一键本地部署** | 需手动 `uvicorn` + `npm run dev` 双进程 | 违背"先部署在本地" |

### 0.3 一个战略判断

Banapeak（昨天解构的竞品）走的是**「非 AI、纯确定性算法」**路线，反复声明"不是大模型生成的建议"。

**你恰恰应该走相反的路，而且这条路更有壁垒：**

```
                  Banapeak                    zettaranc Web
事实来源          算法算给你看                 算法算给你看（你已有，更强）
表达方式          固定模板                     Z 格人格化表达（你有 200 万字语料）
依据可溯          因子明细展开                 ★ 引用溯源到具体知识段落
```

**核心差异化 =「算法负责事实、LLM 负责表达、知识库负责依据、每一句都可溯源」。**

你的算法层比 Banapeak 更厚（有真回测、有 moneyflow、有 26,400 条指标缓存），人格层是它完全没有的。**但前提是把「溯源」做扎实** —— 每一个 LLM 结论都要能点开看到引自 `knowledge/trading-core.md` 的哪一段、来自哪个指标的哪个数值。这是 RAG 产品在金融领域可信度的生死线。

---

## 1. 目标定义

### 1.1 产品一句话

> **本地运行、自带 A 股全市场数据、可挂载任意知识库、可切换任意 LLM 的 Z 哥视角个股问答工作台。**

### 1.2 三条硬约束（来自你的要求）

| 约束 | 落地要求 |
|---|---|
| **纯开源** | MIT 保持不变；所有依赖必须可免费获取；不得内置任何需要付费才能跑通的核心路径；语料版权需明确边界 |
| **先本地部署** | 单命令启动（`docker compose up` 或 `./dev.sh`）；**零强制云服务**；断网可跑（除 LLM 调用外） |
| **多知识库 + 多 LLM** | 二者都是**运行时可配置的一等公民**，不是改代码/改 .env 才能换 |

### 1.3 非目标（明确不做）

- 不做多用户 / 登录鉴权（本地单机优先，鉴权留到 v2）
- 不做云端托管
- 不做荐股 / 代客交易（沿用 SKILL.md 既有边界）
- 不重做现有 7 个页面（扩展，非重写）

---

## 2. 架构总览

### 2.1 三层融合架构

```
┌─────────────────────────────────────────────────────────────┐
│  L4  前端（已有，扩展 2 页 + 1 设置中心）                      │
│      React 19 + Vite 8 + Tailwind 4 + ECharts               │
│      + ChatPage（新增）  + KnowledgePage（新增）              │
└─────────────────────────────────────────────────────────────┘
                            ↕ REST + SSE
┌─────────────────────────────────────────────────────────────┐
│  L3  问答编排层（★全新）                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Intent   │ │ QAE      │ │ Context  │ │ Session  │        │
│  │ Router   │→│ Engine   │→│ Assembler│→│ Manager  │        │
│  │(已有改造)│ │ 双腿检索  │ │ 溯源标注  │ │ 会话持久化│        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
└─────────────────────────────────────────────────────────────┘
        ↓ 数据腿                              ↓ 知识腿
┌──────────────────────┐        ┌──────────────────────────────┐
│  L2a 确定性数据层(已有)│        │  L2b 知识层（★全新）           │
│  SQLite 410MB        │        │  sqlite-vec（向量）            │
│  daily_kline 179k    │        │  + FTS5（关键词，jieba 分词）  │
│  indicators / score  │        │  + 多库隔离（kb_id）           │
└──────────────────────┘        └──────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│  L1  可插拔 Provider 层（★全新重构）                          │
│  LLMProvider: OpenAI兼容 / Anthropic / Ollama / 自定义        │
│  EmbeddingProvider: 本地 BGE-small-zh / 云端各家 / 自定义      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| **向量库** | **sqlite-vec** ✅ 已实测 | 项目已重度依赖 SQLite，扩展即可用；**零额外端口、零服务进程、单文件**，完美契合"本地部署"。实测：10k × 512 维写入 0.15s、KNN 检索 **1.1ms** |
| **关键词检索** | **FTS5 + 中文 2-gram 展开** ✅ 已实测 | **见下方 2.3 实测记录** —— trigram 方案已被证伪 |
| **混合检索** | **RRF 融合**（向量 + BM25） | Reciprocal Rank Fusion，无需调权重，两路结果按排名倒数加总。比分数归一化简单且稳 |

### 2.3 ⚠️ 实测记录：中文全文检索选型（2026-09-06 已验证）

已在隔离环境（Python 3.13.12 / SQLite 3.50.4 / sqlite-vec 0.1.9）实测三种方案，用真实交易术语查询：

| 方案 | 依赖 | 2 字词召回（缩量/买点/背离/仓位/止损） | 3–4 字词召回 | 结论 |
|---|---|---|---|---|
| **FTS5 trigram** | 零 | ❌ **全部失效** | ✅ 正常 | **弃用** |
| **FTS5 unicode61 + 中文 2-gram 展开** | **零**（仅 `re`） | ✅ **全部命中** | ✅ 正常 | ✅ **采用** |
| FTS5 + jieba 预分词 | jieba（~19MB） | ✅ 正常 | ✅ 正常 | 可选增强 |

**trigram 为什么不行**：trigram tokenizer 按 3 字符切分，**2 字词（长度 < 3）根本无法生成 token**。而 A 股术语里 2 字词是绝对主力 —— 买点、卖点、止损、仓位、缩量、放量、背离、金叉、死叉、回踩、破位、洗盘。这个坑如果没提前踩，会在 M2 阶段才暴露，届时索引已建、推倒重来。

**采用方案的实现（约 10 行，零依赖）**：

```python
def tokenize_cjk(text: str) -> str:
    """中文 2-gram 展开 — 零依赖，供 FTS5 unicode61 使用"""
    out = []
    for seg in re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]+', text):
        if re.match(r'^[a-zA-Z0-9]+$', seg):
            out.append(seg.lower())
        elif len(seg) == 1:
            out.append(seg)
        else:
            out.extend(seg[i:i+2] for i in range(len(seg) - 1))
    return ' '.join(out)
```

索引与查询**必须用同一个函数**，否则 token 空间不一致。

**已知边界**：中英混排词（如「J值」「B1点」）在短语查询下可能失配，因为 "J" 拆成英数 token、"值" 落入后续 2-gram 窗口。**缓解办法**：查询侧对短查询改用 OR 而非短语匹配；或用 jieba 加载自定义词典 `J值/B1/B2/B3/四块砖/少妇战法` 兜底。建议在 M2 阶段建一个 30 条的检索质量评测集回归验证。

**性能实测**：

```
写入 10,000 条 × 512 维向量 :  0.15s
KNN 检索 top10（10k 规模）  :  1.1ms
```

按你 `knowledge/` 29 个文件估测，全量索引后在 **2,000–5,000 chunk** 量级，检索延迟在**毫秒级**，完全无需引入任何外部向量服务。
| **Embedding 默认** | **BGE-small-zh-v1.5（本地）** | ~90MB，中文语义检索效果优秀，CPU 可跑，断网可用。云端作为可选 |
| **LLM 配置存储** | **SQLite 表 + YAML 种子导入** | 运行时可通过 UI 增删改；首次启动从 `configs/providers.yaml` 播种 |
| **流式输出** | **SSE**（非 WebSocket） | FastAPI 原生支持、前端 EventSource 零依赖、够用 |
| **部署形态** | **Docker Compose + 裸机脚本双轨** | Docker 给小白，`dev.sh` 给开发；前端 build 后由 FastAPI 静态托管，**单端口** |

---

## 3. 增量模块详细设计

### 3.1 G2：LLM Provider 抽象层（重构）

**现状问题**：`llm_providers.py` 里只有一个 `MiniMaxProvider`，`DEFAULT_BASE_URL` 硬编码。

**目标结构**：

```
modules/providers/
├── base.py              # LLMProvider / EmbeddingProvider 抽象基类
├── registry.py          # 注册表 + 工厂（按 type 实例化）
├── llm/
│   ├── openai_compat.py  # 覆盖 DeepSeek / 通义 / Kimi / 智谱 / MiniMax / 硅基流动 / Groq / 本地 vLLM
│   ├── anthropic.py
│   ├── ollama.py         # 本地模型
│   └── custom.py         # 任意 OpenAI 兼容端点
└── embedding/
    ├── local_bge.py      # sentence-transformers，本地
    ├── openai_compat.py
    └── ollama.py
```

**统一接口**：

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, user: str, **kw) -> str: ...

    @abstractmethod
    def generate_stream(self, system: str, user: str, **kw) -> Iterator[str]: ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]: ...   # 供设置页"测试连接"

class EmbeddingProvider(ABC):
    dimension: int                                     # 建表时需要，必须显式声明
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...
```

**配置模型**（存 SQLite `llm_provider` 表）：

```yaml
- id: deepseek-chat
  name: DeepSeek V3
  type: openai_compat
  base_url: https://api.deepseek.com/v1
  model: deepseek-chat
  api_key_ref: env:DEEPSEEK_API_KEY   # ★ 密钥只存引用，不存明文
  max_tokens: 4096
  temperature: 0.7
  enabled: true
  is_default: true
  tags: [chat, stock]
```

🔒 **安全设计**：API Key **不以明文存数据库**，只存 `env:XXX` 引用或系统钥匙串引用。这是开源项目的硬要求 —— 否则用户一旦把 `app.db` 上传就泄露。

### 3.2 G1：多知识库（全新）

**数据模型**：

```sql
-- 知识库（一等公民）
CREATE TABLE knowledge_base (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,                  -- 「Z哥交易体系」「我的交割单笔记」
  slug TEXT UNIQUE NOT NULL,
  description TEXT,
  embedding_provider_id TEXT,          -- 每库可独立指定 embedding
  chunk_size INTEGER DEFAULT 512,
  chunk_overlap INTEGER DEFAULT 64,
  retrieval_mode TEXT DEFAULT 'hybrid',-- hybrid | vector | fts
  vector_weight REAL DEFAULT 0.5,
  is_builtin INTEGER DEFAULT 0,        -- 内置库不可删除
  doc_count INTEGER DEFAULT 0,
  created_at TEXT
);

-- 文档
CREATE TABLE kb_document (
  id TEXT PRIMARY KEY,
  kb_id TEXT NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
  title TEXT, source_path TEXT, category TEXT,
  content_hash TEXT,                   -- ★ 增量索引：hash 未变则跳过
  char_count INTEGER, chunk_count INTEGER,
  status TEXT,                         -- pending | indexed | failed
  error_msg TEXT, created_at TEXT, updated_at TEXT
);

-- 分块
CREATE TABLE kb_chunk (
  id TEXT PRIMARY KEY,
  kb_id TEXT NOT NULL, doc_id TEXT NOT NULL,
  seq INTEGER, content TEXT,
  token_count INTEGER,
  meta_json TEXT                       -- {heading, page, section}
);

-- 向量（sqlite-vec 虚拟表，按 kb 分区或统一表 + kb_id 过滤）
CREATE VIRTUAL TABLE kb_chunk_vec USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding FLOAT[512]                 -- 维度由 embedding provider 决定
);

-- 全文（FTS5 unicode61 + 中文 2-gram 展开，零依赖；见 2.3 实测）
CREATE VIRTUAL TABLE kb_chunk_fts USING fts5(
  chunk_id UNINDEXED, kb_id UNINDEXED, content,
  tokenize='unicode61'
);
-- ⚠️ 写入与查询必须都经过 tokenize_cjk()，否则 token 空间不一致
```

**内置知识库（首次启动自动播种）**：

| 库 | 来源 | 内容 |
|---|---|---|
| `zettaranc-core` | `knowledge/*.md` 29 文件 | 交易体系、指标、卖出纪律、趋势线、仓位、宏观 |
| `zettaranc-life` | life-decision / career / business | 人生 / 职业 / 商业框架 |
| `zettaranc-heuristics` | `heuristics.md` + `harness.md` | 44 条启发式 + 约束规则 |

**支持的文档格式**：`.md` `.txt` `.pdf`(pypdf) `.docx`(python-docx) —— 全部可选依赖，缺失时优雅降级。

**检索流程（hybrid + RRF）**：

```
query
  ├─→ embedding.embed_query()    → kb_chunk_vec  MATCH  → top 20 (向量)
  └─→ tokenize_cjk(query)        → kb_chunk_fts  MATCH  → top 20 (BM25)
                    ↓
              RRF 融合（k=60）
                    ↓
        按 kb_id 过滤（本次挂载了哪些库）
                    ↓
              top_k 返回 + 溯源元信息
```

**溯源元信息必须包含**：`{kb_name, doc_title, source_path, heading, category, score, content_snippet}` —— 前端靠它渲染引用卡片。

### 3.3 G3：个股问答引擎（核心，全新）

这是整个改造的价值落点。

**完整链路**：

```
用户：「600519 现在能买吗？」
   ↓
① 意图路由（复用并增强 IntentRouter）
   规则匹配 → intent=stock, ts_code=600519.SH, confidence
   ↓
② 实体抽取
   ts_code / 股票简称 → 代码（复用 stock_basic 5,525 只）
   ↓
③ 双腿并行检索
   ┌─ 数据腿（确定性，已有能力封装）─────────────┐
   │  daily_kline 取近 120 日                      │
   │  → indicators 计算：B1/B2/B3、J值、量比、MA  │
   │  → 评分 / 战法匹配 / 风险标记                │
   │  → 输出结构化快照 {score, signals, risks}    │
   └───────────────────────────────────────────┘
   ┌─ 知识腿（RAG，新建）──────────────────────┐
   │  按 intent + 抽取的实体检索                  │
   │  → 挂载库：zettaranc-core + 用户自选库       │
   │  → 输出 top_k 知识卡片（带溯源）             │
   └───────────────────────────────────────────┘
   ↓
④ 上下文组装（ContextAssembler）
   人格 prompt（SKILL.md 蒸馏）
   + 数据快照（JSON，结构化）
   + 知识卡片（带编号 [1][2][3]，供引用）
   + 输出契约（必须含哪些要素 / 禁止哪些表述）
   + 免责声明触发条件
   ↓
⑤ LLM 生成（选中的 provider，SSE 流式）
   ↓
⑥ 后处理
   引用标注解析（把 [1] 映射回 knowledge_card）
   + 免责声明注入（命中「能不能买/卖」时强制追加）
   + 落库 llm_response_log（已有表，正好用上）
   ↓
⑦ SSE 流式返回
   event: token   → 增量文本
   event: refs    → 引用列表（生成完成后）
   event: data    → 数据快照（供前端渲染指标卡）
```

**为什么"数据腿"必须是确定性计算而非让 LLM 看图算数**：

LLM 算术不可靠，K 线数据也不能全塞进上下文。**正确分工是——Python 算好数值，只把结论喂给 LLM，LLM 负责用 Z 哥的方式讲出来。** 这既是准确性保障，也是 token 成本控制。

**API 设计**：

```
POST   /api/v1/chat/completions     SSE 流式问答
POST   /api/v1/chat/sessions        新建会话
GET    /api/v1/chat/sessions        会话列表
GET    /api/v1/chat/sessions/{id}   会话详情（含消息 + 引用）
DELETE /api/v1/chat/sessions/{id}
POST   /api/v1/chat/sessions/{id}/stop   中断生成
```

**会话表**：

```sql
CREATE TABLE chat_session (
  id TEXT PRIMARY KEY, title TEXT,
  llm_provider_id TEXT, kb_ids TEXT,      -- 本次挂载的知识库
  intent TEXT, ts_code TEXT,              -- 便于「该股票的历史提问」
  created_at TEXT, updated_at TEXT
);
CREATE TABLE chat_message (
  id TEXT PRIMARY KEY, session_id TEXT, role TEXT,
  content TEXT, refs_json TEXT,           -- 溯源引用
  data_snapshot_json TEXT,                -- 当时的指标快照（★ 可复现）
  token_usage_json TEXT, latency_ms INTEGER, created_at TEXT
);
```

🔑 **`data_snapshot_json` 是关键设计** —— 把当时的指标数值存下来，用户三个月后回看这段对话，能看到"当时 J=-12、量比 0.8"，而不是只有一段已经对不上的文字。这是复盘产品的核心价值。

### 3.4 G4：本地一键部署

**方案 A：Docker Compose（推荐给使用者）**

```yaml
services:
  app:                      # FastAPI 同时托管 API + 前端静态产物
    build: .
    ports: ["8770:8770"]
    volumes:
      - ./data:/app/data           # SQLite + 向量库
      - ./knowledge:/app/knowledge
      - ~/.zettaranc:/root/.zettaranc   # 配置持久化
    environment:
      - ZETTARANC_LLM_API_KEY=${LLM_API_KEY}
  ollama:                   # 可选 profile，本地 LLM
    profiles: ["local"]
    image: ollama/ollama
    ports: ["11434:11434"]
```

**方案 B：裸机脚本（开发用）**

```bash
./scripts/dev.sh        # 启动后端(8770) + 前端(5173) 双进程，热重载
./scripts/start.sh      # 生产模式：build 前端 → 单端口 8770
```

**前端生产形态**：`vite build` 输出到 `frontend/dist`，FastAPI 用 `StaticFiles` 挂载并 fallback 到 `index.html`。**单端口 8770**，本地部署零心智负担。

---

## 4. 前端页面规划

**原则：扩展，不重写。** 现有 7 页 + AppShell/Sidebar 全部保留。

### 4.1 新增页面

| 页面 | 路由 | 内容 |
|---|---|---|
| **ChatPage** | `/chat` | 主场景。左侧会话列表 + 中间对话流 + 右侧上下文面板（数据快照 + 引用卡片） |
| **KnowledgePage** | `/knowledge` | 知识库管理：库列表 / 文档上传 / 索引状态 / 检索测试沙盒 |

### 4.2 改造页面

| 页面 | 改造 |
|---|---|
| **Settings** | 拆成 4 个 Tab：LLM 供应商（增删改 + 测试连接）/ Embedding / 知识库默认 / 数据源(Tushare) |
| **StockAnalysis** | 增加「问 Z 哥」入口 → 带着该股上下文跳到 ChatPage |

### 4.3 ChatPage 三栏布局（核心 UI）

```
┌──────────┬────────────────────────────┬──────────────┐
│ 会话列表  │        对话流               │  上下文面板   │
│          │                            │              │
│ + 新对话  │  Q: 600519 现在能买吗？      │ ┌──────────┐ │
│          │                            │ │ 指标快照   │ │
│ · 茅台诊断│  A: 这票啊……（流式）         │ │ J值 -12   │ │
│ · 卖点讨论│                            │ │ 量比 0.8  │ │
│ · 职业选择│  [引用 1] trading-core.md  │ │ 评分 62   │ │
│          │  [引用 2] indicators.md    │ └──────────┘ │
│          │                            │ ┌──────────┐ │
│          │  ⚠️ 不构成投资建议…          │ │ 引用来源   │ │
│          │                            │ │ 2 条      │ │
│          │  ┌──────────────────────┐  │ └──────────┘ │
│          │  │ 输入…        [发送]  │  │              │
│          │  └──────────────────────┘  │              │
└──────────┴────────────────────────────┴──────────────┘
```

**右侧上下文面板是差异化关键** —— 用户能同时看到「算法算出来的数」和「LLM 引据的知识」，信任感来自这里，不是来自对话气泡。

---

## 5. 技术选型清单

### 5.1 新增 Python 依赖

| 包 | 用途 | 体积 | 必需性 |
|---|---|---|---|
| `sqlite-vec` | 向量检索 | **165KB** ✅ 已实测 | ✅ 核心 |
| `jieba` | 中文分词增强 | ~19MB | ⭕ **可选**（2-gram 方案已够用，见 2.3） |
| `sentence-transformers` + `torch` | 本地 embedding | **~2GB** | ⭕ 可选（local-emb profile） |
| `pypdf` | PDF 解析 | ~10MB | ⭕ 可选 |
| `python-docx` | docx 解析 | ~1MB | ⭕ 可选 |

**核心依赖只有 `sqlite-vec` 一个，165KB。** 这是"轻量本地部署"的关键 —— 加上零依赖的中文 2-gram 分词，整个知识库层不引入任何重量级组件。

⚠️ **torch 是最大负担**（~2GB）。必须做成 **optional dependency group**：

```toml
[project.optional-dependencies]
local-emb = ["sentence-transformers", "torch"]
docs = ["pypdf", "python-docx"]
```

**默认零 torch**：默认引导用户选云端 embedding（或 Ollama 的 bge-m3），要用本地 BGE-small 才 `pip install -e ".[local-emb]"`。

### 5.2 Embedding 方案对比

| 方案 | 体积 | 断网 | 中文效果 | 推荐度 |
|---|---|---|---|---|
| **BGE-small-zh-v1.5**（sentence-transformers） | ~90MB 模型 + 2GB torch | ✅ | 优秀 | ⭐⭐⭐ 本地首选 |
| **Ollama bge-m3** | 外部服务 | ✅ | 优秀 | ⭐⭐⭐ 已有 Ollama 时 |
| **硅基流动 BAAI/bge-m3** | 0 | ❌ | 优秀 | ⭐⭐ 免费额度可用 |
| **OpenAI text-embedding-3-small** | 0 | ❌ | 良好 | ⭐⭐ |

---

## 6. 开源治理清单

你的 `.gitignore` 已经很完善，但开源还差这几项：

| 项 | 现状 | 动作 |
|---|---|---|
| LICENSE | ✅ MIT | 保持 |
| CONTRIBUTING.md | ✅ 有 | 补充 Web 开发指引（前后端如何联调） |
| **CODE_OF_CONDUCT** | ❌ | 新增 |
| **SECURITY.md** | ❌ | 新增（漏洞报告流程） |
| **Issue / PR 模板** | ⚠️ 需确认 | 检查 `.github/`，补全 |
| **CI** | ⚠️ 需确认 | GitHub Actions：backend pytest + ruff + mypy；frontend tsc + eslint + build |
| **pre-commit** | ✅ 有 `.pre-commit-config.yaml` | 增加 detect-secrets / gitleaks 钩子 |
| **语料版权** | ⚠️ **最大风险** | 见下 |
| **示例数据** | ❌ | 提供 `scripts/seed_demo.py`：拉 100 只股票 1 年数据，让新用户 5 分钟跑通 |

### 6.1 语料版权（必须处理）

`corpus/` 的 467 篇直播整理来自粉丝整理（知行课代表、知行小菜鸟等），200 万字。

**建议策略**：
1. **原始语料 `references/sources/` 已 gitignore —— 保持不入库。** ✅
2. **`knowledge/*.md`（已提炼的框架文件）可开源**，但在 README 明确声明：
   > 本项目 `knowledge/` 下的内容为公开直播/付费课程内容的**二次提炼与结构化整理**，版权归原作者所有。本项目仅将其作为**可替换的知识库示例数据**分发，使用者可随时替换为自有内容。
3. **提供"空知识库"启动模式** —— `EMPTY_KB=1` 启动时不播种内置库，纯粹作为 RAG 框架使用。这样即便版权有争议，项目本身仍成立。
4. 知识库本身设计成**可插拔数据**，不是代码的一部分 —— 这在架构上已经做到了（知识库是 DB 记录 + 文档文件）。

---

## 7. 分阶段路线图

| 阶段 | 目标 | 工作量 | 交付物 | 验收标准 |
|---|---|---|---|---|
| **M0 开源卫生 + 能跑起来** | 让陌生人 5 分钟跑通 | 1–2 天 | docker-compose、dev.sh、seed_demo.py、CI、COC/SECURITY | 干净机器上 `docker compose up` 能打开页面 |
| **M1 LLM Provider 层** | 多模型可配置 | 3–5 天 | providers/ 抽象 + 注册表 + 设置页 Tab + 测试连接 | UI 里加一个 DeepSeek 并成功对话 |
| **M2 知识库** | 多库 + 检索 | 5–7 天 | sqlite-vec + FTS5 + 数据模型 + 索引管道 + 管理页 + 检索沙盒 | 上传 10 个 PDF 建库，检索沙盒能召回 |
| **M3 问答引擎** | 核心场景闭环 | 5–7 天 | QAEngine + ContextAssembler + SSE + ChatPage 三栏 + 溯源 | 问「600519 能买吗」返回带引用的流式回答 |
| **M4 打磨 + 发布** | 可对外 | 3–5 天 | 文档、示例、错误处理、性能优化、v1.0 tag | README 有完整截图和快速开始 |

**总计约 3–4 周（兼职节奏）。**

**建议排序理由**：M0 先做，因为它零风险且立刻让项目"能演示"；M1 先于 M2，因为 LLM 层更简单且能被 M3 直接验证；M2/M3 是硬骨头但也是全部价值所在。

---

## 8. 关键决策点（需要你拍板）

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| **D1** | 默认 Embedding | A. 本地 BGE-small（+2GB torch）／ B. 云端免费额度／ C. Ollama bge-m3 | **C 或 B**。torch 2GB 对"轻量本地部署"是硬伤；做成可选组，默认引导 Ollama |
| **D2** | 内置知识库是否默认播种 | A. 默认播种（开箱即用，有版权顾虑）／ B. 空库启动 + 一键导入脚本 | **B**，配 `EMPTY_KB=1` 开关，框架与内容解耦 |
| **D3** | 前端视觉 | A. 沿用现有深色+金色 ／ B. 重做为你既有的像素 8-bit + CRT 美学 | 需你定。现有前端风格与你的设计语言体系不一致 |
| **D4** | 是否需要登录鉴权 | A. 不要（本地单机）／ B. 简单的单用户口令 | **A**，v2 再说。但 API Key 必须走 env 引用，不能落库明文 |
| **D5** | 项目命名 | zettaranc-skill（保持）／ Zettaranc Studio ／ 万千工作台 | 建议仓库名保持（已有 remote），Web 应用另起产品名 |

---

## 9. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| **torch 体积劝退** | 高 | 做成 optional group，默认走 Ollama/云端；README 明确说明 |
| **LLM 输出合规** | 高 | 复用 SKILL.md 已有的强制免责声明逻辑；输出契约层硬校验（禁止出现"建议买入"等表述） |
| **语料版权争议** | 中高 | 见 6.1，知识库可插拔 + 空库启动模式 |
| **FTS5 中文分词效果** | ~~中~~ 已消除 | 已实测选型：2-gram 展开方案召回正常，trigram 已证伪（见 2.3）。残余风险为中英混排词，靠 30 条评测集回归 |
| **现有前端与算法层耦合** | 中 | 新增模块全部走新路由前缀 `/api/v1/`，不动现有 9 个路由 |
| **410MB SQLite 与向量库混存** | 低 | 向量库独立文件 `data/kb.db`，与 `stock_data.db` 分离 |

---

## 10. 立即可做的四件事

不用等整份规划批完，这四项现在就能动，且零风险：

0. **先修环境（5 分钟，必须先做）** —— `.venv313` 已损坏：
   ```
   dyld: Library not loaded: .../Cellar/python@3.13/3.13.13_1/Frameworks/Python.framework
   ```
   Homebrew 升级后 Python 框架被移除导致链接失效。`.venv` / `.venv311` / `.venv312` 均正常。
   处理：`rm -rf .venv313 && uv venv --python 3.13 .venv313`（或统一改用 `.venv`）。
   **不修的话，任何人 clone 后按 README 走都会卡在这一步，开源第一天就劝退。**

1. **M0 的 docker-compose + dev.sh** —— 半天工作量，立刻让项目可演示。

2. **`providers/base.py` 抽象基类** —— 纯新增文件，不影响现有 `MiniMaxProvider`，可以先写接口再慢慢迁移。

3. **`data/kb.db` 数据模型 + sqlite-vec 连通性验证** —— ✅ **本规划已提前完成验证**：sqlite-vec 0.1.9 可加载、10k × 512 维检索 1.1ms、中文 2-gram 召回正常。M2 技术可行性已确认，可直接进入建表。

---

*规划基于 2026-09-06 仓库状态（v4.3.1-pre-slim）｜ 数据规模以 `data/stock_data.db` 实际统计为准*
