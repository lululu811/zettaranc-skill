#!/usr/bin/env python3
"""
知识库检索适配器

消费现有 knowledge-base 的 RAG API，
按意图自动注入分类过滤，提高检索精准度。
"""

from typing import Optional
import os
import httpx
from dataclasses import dataclass


@dataclass
class KnowledgeCard:
    content: str  # 知识卡片正文
    source: str  # 来源文件路径
    category: str  # 分类目录（如 "01_战法系列"）
    score: float  # 相关度分数


class KnowledgeRetriever:
    """向量知识库检索适配器

    消费现有 knowledge-base 的 RAG 服务，
    按意图自动注入分类过滤，提高检索精准度。
    """

    # 意图 → 知识库分类优先级映射
    CATEGORY_FILTERS = {
        "stock": ["01_战法系列", "03_选股方法", "04_大盘市场分析", "07_锦囊周评总结", "02_直播笔记", "08_知识汇总体系"],
        "career": ["06_行业宏观研究", "02_直播笔记", "09_其他", "08_知识汇总体系"],
        "life": ["05_交易心理心态", "09_其他", "08_知识汇总体系", "02_直播笔记"],
    }

    def __init__(self, kb_api_url: str | None = None, top_k: int = 5):
        if kb_api_url is None:
            kb_api_url = os.getenv("KB_API_URL", "http://localhost:8000")
        self.api_url = kb_api_url.rstrip("/")
        self.top_k = top_k

        # 读取开关：默认关闭，设为 true 且提供 KB_API_URL 才启用
        self.enabled = os.getenv("KB_ENABLED", "false").lower() == "true"

    def retrieve(self, query: str, intent: str) -> list[KnowledgeCard]:
        """按意图检索知识库

        如果 KB_ENABLED=false，直接返回空列表，不发起请求。
        """
        if not self.enabled:
            return []

        # 1. 调用知识库 API
        params = {"query": query, "top_k": self.top_k * 2, "mode": "hybrid"}
        try:
            response = httpx.post(
                f"{self.api_url}/retrieve",
                json=params,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return []

        results = data.get("documents", [])

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
        for score, r, category in scored_results[: self.top_k]:
            # 过滤掉 cover_image 等无效内容
            content = r.get("content", "").strip()
            if len(content) < 20:
                continue
            cards.append(
                KnowledgeCard(
                    content=content,
                    source=r.get("source", ""),
                    category=category,
                    score=round(score, 3),
                )
            )
        return cards

    def _extract_category(self, source_path: str) -> str:
        """从文件路径提取分类目录"""
        # 如 "data/classified/01_战法系列/xxx.md" → "01_战法系列"
        parts = source_path.split("/")
        for p in parts:
            if p.startswith("0") and "_" in p:
                return p
        return "unknown"


def format_knowledge_cards(cards: list[KnowledgeCard]) -> str:
    """格式化知识卡片为 LLM 可阅读的文本"""
    if not cards:
        return ""

    parts = []
    for card in cards:
        # 截断过长内容
        content = card.content
        if len(content) > 800:
            content = content[:800] + "..."

        parts.append(f"[{card.category}] (score={card.score})\n{content}")

    return "\n\n---\n\n".join(parts)


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    # 测试
    retriever = KnowledgeRetriever()

    test_cases = [
        ("B1 买点怎么判断", "stock"),
        ("我想辞职全职炒股", "career"),
        ("最近很焦虑，怎么办", "life"),
    ]

    for query, intent in test_cases:
        print(f"\n=== {intent} | {query} ===")
        cards = retriever.retrieve(query, intent)
        print(f"检索到 {len(cards)} 条知识卡片")
        for c in cards[:2]:
            print(f"  [{c.category}] score={c.score}")
            print(f"  source: {c.source}")
            print(f"  content: {c.content[:80]}...")
            print()
