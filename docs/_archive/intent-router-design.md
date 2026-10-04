# 意图识别编排层 · 技术方案 v2

> 意图识别 + 向量知识库 RAG + LLM 角色生成

---

## 一、现状分析

### 现有资源

| 组件 | 状态 | 位置 |
|------|------|------|
| **向量知识库** | 已就绪（5700+ 文件，262MB Qdrant 存储） | `/Users/chenlei/knowledge-base/` |
| **Embedding** | qwen3-embedding:8b（768 维，中文优化） | Ollama localhost:11434 |
| **LLM** | qwen3:32b | Ollama localhost:11434 |
| **向量库** | Qdrant + BM25 混合搜索 | localhost:6333 |
| **API 服务** | `api.py`（FastAPI）已存在 | knowledge-base/ |
| **查询脚本** | `query.py` 已可用 | knowledge-base/ |

### 知识库分类（天然可映射到意图）

```
01_战法系列 (1447)  → stock 意图的核心数据源
02_直播笔记 (822)   → stock + career + life 的通用心法
03_选股方法 (56)    → stock
04_大盘市场分析 (250) → stock
05_交易心理心态 (200) → stock + life（焦虑/迷茫/心态）
06_行业宏观研究 (73)  → stock + career（赛道/行业选择）
07_锦囊周评总结 (57)  → stock
08_知识汇总体系 (209) → 全部意图
09_其他 (261)        → life + career（人生/城市/职业）
```

### 架构优势

现有知识库已经完成了最重的部分：**数据摄入、分类、向量化、检索**。
意图识别编排层不需要自己建向量库，只需要**消费**现有 RAG 系统的检索结果。

---

## 二、架构设计

```
用户输入
  │
  ├─ [1] 意图识别层 (intent_router.py)
  │     ├─ 规则匹配（keywords/patterns）→ 命中 stock/career/life/chat
  │     └─ LLM 轻量分类（~50 token）→ 兜底
  │
  ├─ [2] 知识库检索层 (knowledge_retriever.py)
  │     ├─ 调用现有 knowledge-base 的 API
  │     │   GET /api/query?query={message}&top_k=5
  │     │   → 返回 [{content, source, score}, ...]
  │     ├─ 根据 intent 自动注入 collection_filter
  │     │   stock → 优先 01/03/04/07 分类
  │     │   career → 优先 06/02/09 分类
  │     │   life → 优先 05/08/09 分类
  │     └─ 返回 top_k 知识卡片
  │
  ├─ [3] 系统提示组装层 (prompt_assembler.py)
  │     ├─ 角色框架（role_prompt）
  │     │   stock → SKILL.md（Z哥投资模式）
  │     │   career → career_prompt.md（Z哥职业模式）
  │     │   life → life_prompt.md（Z哥人生模式）
  │     │   chat → ""（不注入角色）
  │     └─ 知识上下文（rag_context）
  │         拼接检索到的知识卡片，注入到 system prompt
  │
  └─ [4] LLM 生成层
        ├─ 组装完整 prompt：角色框架 + 知识上下文 + 用户问题
        ├─ 调用 qwen3:32b 生成回答
        └─ 返回给用户
```

---

## 三、核心模块实现

### 3.1 知识库检索适配器

```python
# zettaranc-skill/modules/knowledge_retriever.py

import httpx
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class KnowledgeCard:
    content: str       # 知识卡片正文
    source: str        # 来源文件路径
    category: str      # 分类目录（如 "01_战法系列"）
    score: float       # 相关度分数

class KnowledgeRetriever:
    """向量知识库检索适配器
    
    消费现有 knowledge-base 的 RAG 服务，
    按意图自动注入分类过滤，提高检索精准度。
    """
    
    # 意图 → 知识库分类优先级映射
    CATEGORY_FILTERS = {
        "stock": ["01_战法系列", "03_选股方法", "04_大盘市场分析", 
                   "07_锦囊周评总结", "02_直播笔记"],
        "career": ["06_行业宏观研究", "02_直播笔记", "09_其他",
                    "08_知识汇总体系"],
        "life": ["05_交易心理心态", "09_其他", "08_知识汇总体系",
                  "02_直播笔记"],
    }
    
    def __init__(self, kb_api_url: str = "http://localhost:8000",
                 top_k: int = 5):
        self.api_url = kb_api_url
        self.top_k = top_k
    
    def retrieve(self, query: str, intent: str) -> List[KnowledgeCard]:
        """按意图检索知识库"""
        # 1. 调用知识库 API
        params = {"query": query, "top_k": self.top_k * 2}
        response = httpx.get(f"{self.api_url}/api/query", 
                            params=params, timeout=10.0)
        results = response.json().get("results", [])
        
        # 2. 按意图分类过滤 + 重排序
        priority_categories = self.CATEGORY_FILTERS.get(intent, [])
        scored_results = []
        for r in results:
            category = self._extract_category(r.get("source", ""))
            # 优先分类加权
            if category in priority_categories:
                boost = 1.0 + (priority_categories.index(category) * 0.1)
            else:
                boost = 0.8
            scored_results.append((r["score"] * boost, r, category))
        
        # 3. 按加权分数排序，取 top_k
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        cards = []
        for score, r, category in scored_results[:self.top_k]:
            cards.append(KnowledgeCard(
                content=r["content"],
                source=r.get("source", ""),
                category=category,
                score=round(score, 3),
            ))
        return cards
    
    def _extract_category(self, source_path: str) -> str:
        """从文件路径提取分类目录"""
        # 如 "data/classified/01_战法系列/xxx.md" → "01_战法系列"
        parts = source_path.split("/")
        for p in parts:
            if p.startswith("0") and "_" in p:
                return p
        return "unknown"
```

### 3.2 意图识别 + RAG 统一入口

```python
# zettaranc-skill/modules/intent_router.py

from dataclasses import dataclass
from typing import Optional, Literal
from .knowledge_retriever import KnowledgeRetriever

@dataclass
class RouterResult:
    intent: Literal["stock", "career", "life", "chat", "fallback"]
    confidence: float
    system_prompt: str           # 组装好的系统提示
    knowledge_context: str       # 检索到的知识上下文（空 = 不需要RAG）
    stock_data: Optional[dict]   # 如果是 stock 意图，附加实时行情数据

class IntentRouter:
    """意图识别 + RAG 检索 + 系统提示组装 统一入口"""
    
    def __init__(self, 
                 rules_path: str = "rules/intent_rules.yaml",
                 kb_api_url: str = "http://localhost:8000"):
        self.rule_matcher = RuleMatcher(rules_path)
        self.kb_retriever = KnowledgeRetriever(kb_api_url)
        self.prompt_templates = self._load_prompts()
    
    def process(self, user_message: str) -> RouterResult:
        """完整处理流程"""
        # 1. 意图分类
        intent, confidence = self.rule_matcher.match(user_message)
        if not intent:
            intent, confidence = self._llm_classify(user_message)
        
        # 2. chat/fallback 不需要 RAG，直接返回
        if intent in ("chat", "fallback"):
            return RouterResult(
                intent=intent,
                confidence=confidence,
                system_prompt="",
                knowledge_context="",
                stock_data=None,
            )
        
        # 3. 知识库检索
        cards = self.kb_retriever.retrieve(user_message, intent)
        knowledge_context = self._format_knowledge(cards)
        
        # 4. 组装系统提示
        system_prompt = self._build_system_prompt(intent, knowledge_context)
        
        # 5. stock 意图附加实时数据
        stock_data = None
        if intent == "stock":
            stock_codes = self._extract_stock_codes(user_message)
            if stock_codes:
                from modules.indicators import analyze_stock
                stock_data = analyze_stock(stock_codes[0])
        
        return RouterResult(
            intent=intent,
            confidence=confidence,
            system_prompt=system_prompt,
            knowledge_context=knowledge_context,
            stock_data=stock_data,
        )
    
    def _build_system_prompt(self, intent: str, 
                             knowledge_context: str) -> str:
        """组装系统提示：角色框架 + 知识上下文"""
        base = self.prompt_templates.get(intent, "")
        if not base:
            return ""
        
        if knowledge_context:
            return f"""{base}

## 知识上下文（来自知识库）

{knowledge_context}

请基于以上知识内容，用你的思维框架回应用户的问题。
如果知识库内容与你的认知冲突，以你的判断为准。
"""
        return base
```

### 3.3 知识卡片格式

```
[01_战法系列] B1买点完整体系.md
────────────────────────────
B1 是左侧抄底信号，需要满足三个条件：
1. J 值 ≤ -10（超卖区）
2. N 型结构（先涨后跌再涨）
3. 缩量回调（量能萎缩）

有瑕疵的 B1 不做：黄线距离太远、压力位附近、呼吸紊乱。
```

---

## 四、知识库 API 集成方案

### 4.1 使用现有 API（推荐，最小改动）

现有 `knowledge-base/api.py` 已有 FastAPI 服务，直接调用：

```bash
# 启动知识库 API
cd /Users/chenlei/knowledge-base
python api.py
# API 运行在 http://localhost:8000
```

```python
# zettaranc-skill 调用
import httpx

response = httpx.get("http://localhost:8000/api/query", 
                     params={"query": "我想辞职全职炒股", "top_k": 5})
results = response.json()
# → [{content, source, score}, ...]
```

### 4.2 如果 API 未启动：直接调用 query.py 逻辑

```python
# 直接 import knowledge-base 的查询模块
import sys
sys.path.insert(0, "/Users/chenlei/knowledge-base")
from query import query_knowledge

results = query_knowledge("我想辞职全职炒股", top_k=5)
```

### 4.3 如果需要增强：按分类过滤检索

现有知识库已经按目录分类存储，可以在 Qdrant 层面给每个 chunk 加上 metadata（category），支持按意图过滤：

```python
# Qdrant 按分类过滤
from qdrant_client import models

results = client.search(
    collection_name="knowledge_base",
    query_vector=embedding,
    query_filter=models.Filter(
        must=[models.FieldCondition(
            key="category",
            match=models.MatchAny(any=["05_交易心理心态", "09_其他"]),
        )]
    ),
    limit=5,
)
```

---

## 五、各意图的 Prompt + RAG 组合

### stock（投资模式）

```
角色框架：SKILL.md（完整 Z 哥投资思维框架）
RAG 检索：01_战法系列 + 03_选股方法 + 04_大盘市场分析 + 07_锦囊周评
实时数据：analyze_stock() + screener + 指标计算
```

### career（职业/搞钱模式）

```
角色框架：career_prompt.md（Z 哥通用心法 + 职业决策框架）
RAG 检索：06_行业宏观研究 + 02_直播笔记 + 09_其他（职业相关）
实时数据：无
```

### life（人生/决策模式）

```
角色框架：life_prompt.md（Z 哥通用心法 + 人生决策框架）
RAG 检索：05_交易心理心态 + 09_其他（人生相关） + 08_知识汇总体系
实时数据：无
```

### chat（正常 AI）

```
角色框架：无
RAG 检索：无
实时数据：无
→ 直接用默认 LLM 回复
```

---

## 六、实施步骤

### Phase 1：知识库 API 确认（半天）

- [ ] 确认 knowledge-base 的 API 能正常启动
- [ ] 测试 query 接口能否正常返回结果
- [ ] 确认分类元数据是否已写入 Qdrant chunk metadata

### Phase 2：意图识别层（1 天）

- [ ] 创建 `rules/intent_rules.yaml`
- [ ] 实现 `modules/intent_router.py`（规则匹配 + LLM 兜底）
- [ ] 编写 `tests/test_intent_router.py`

### Phase 3：知识库适配器（1 天）

- [ ] 实现 `modules/knowledge_retriever.py`
- [ ] 实现意图 → 分类过滤映射
- [ ] 实现知识卡片格式组装
- [ ] 编写 career_prompt.md 和 life_prompt.md

### Phase 4：集成（1 天）

- [ ] 统一 RouterResult 输出
- [ ] CLI 集成（chat 模式直接打印 LLM 回复，stock 模式走现有流程）
- [ ] SKILL.md 顶部加入意图识别协议
- [ ] 端到端测试 50+ 条真实输入

### Phase 5：优化（按需）

- [ ] 知识库 chunk metadata 补充分类标签
- [ ] 意图权重学习（记录分类结果和用户反馈）
- [ ] 多轮对话意图追踪

---

## 七、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 知识库 API 未启动 | RAG 检索失败 | 降级为不使用知识上下文，只用角色框架 |
| 分类元数据缺失 | 意图过滤不准确 | 退化为全局检索 + 后过滤 |
| Qdrant 未运行 | 向量检索不可用 | 退化为仅规则匹配 + LLM 分类 |
| 意图误判 | 用户收到不相关内容 | 规则阈值可调 + LLM 兜底 + 用户可手动指定 |

---

## 八、总结

**不需要新增语料，不需要蒸馏，知识库已经就绪。**

意图识别编排层的核心工作只是：
1. 识别用户想聊什么（stock/career/life/chat）
2. 按意图到知识库里检索相关内容
3. 拼装对应的角色框架 + 知识上下文
4. 调 LLM 生成回答

知识库是地基，意图识别是路由器，LLM 是发动机。三者组合，就能把一个炒股工具升级成多领域智能系统。
