#!/usr/bin/env python3
"""
意图识别与路由分发模块

规则匹配优先（< 1ms，零 token 消耗），LLM 轻量分类兜底。
集成知识库检索，组装对应角色框架。
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal, Optional

from .knowledge_retriever import KnowledgeRetriever, format_knowledge_cards


@dataclass
class RouterResult:
    intent: Literal["stock", "career", "life", "chat", "fallback"]
    confidence: float
    rule_matched: str | None  # 命中的规则名
    system_prompt: str  # 组装好的系统提示词
    knowledge_context: str  # 检索到的知识上下文
    matched_keywords: list = field(default_factory=list)


class IntentRouter:
    """意图识别 + RAG 检索 + 系统提示组装 统一入口"""

    def __init__(self, rules_path: str | None = None, kb_api_url: str | None = None, top_k: int = 5):
        if rules_path is None:
            rules_path = str(Path(__file__).parent.parent / "rules" / "intent_rules.yaml")

        self.rules = self._load_rules(rules_path)
        self.compiled_patterns = self._compile_patterns()
        self.kb_retriever = KnowledgeRetriever(kb_api_url, top_k)
        self.prompt_templates = self._load_prompts()

    def process(self, user_message: str) -> RouterResult:
        """完整处理流程"""
        # 1. 规则匹配
        matched = self._rule_match(user_message)
        if matched:
            intent, confidence, rule_name, keywords = matched
        else:
            # 2. 规则未命中 → fallback 到 chat
            intent, confidence, rule_name, keywords = "chat", 0.5, None, []

        # 3. chat/fallback 不需要 RAG 和角色框架
        if intent == "chat":
            return RouterResult(
                intent=intent,
                confidence=confidence,
                rule_matched=rule_name,
                system_prompt="",
                knowledge_context="",
                matched_keywords=keywords,
            )

        # 4. 知识库检索
        cards = self.kb_retriever.retrieve(user_message, intent)
        knowledge_context = format_knowledge_cards(cards)

        # 5. 组装系统提示
        system_prompt = self._build_system_prompt(intent, knowledge_context)

        return RouterResult(
            intent=intent,
            confidence=confidence,
            rule_matched=rule_name,
            system_prompt=system_prompt,
            knowledge_context=knowledge_context,
            matched_keywords=keywords,
        )

    # ---- 规则匹配 ----

    def _load_rules(self, rules_path: str) -> dict:
        with open(rules_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _compile_patterns(self) -> dict:
        compiled = {}
        for intent, config in self.rules.items():
            if config and config.get("patterns"):
                compiled[intent] = [re.compile(p, re.IGNORECASE) for p in config["patterns"]]
        return compiled

    def _rule_match(self, message: str) -> tuple | None:
        """规则匹配，返回 (intent, confidence, rule_name, matched_keywords)"""
        message_lower = message.lower()
        scored = []

        for intent, config in self.rules.items():
            if not config:
                continue

            priority = config.get("priority", 0)
            keywords = config.get("keywords", [])
            patterns = self.compiled_patterns.get(intent, [])

            # 关键词匹配（处理 YAML 可能把数字解析为 int 的情况）
            matched_kw = [str(kw).lower() for kw in keywords if str(kw).lower() in message_lower]
            keyword_score = len(matched_kw) / max(len(keywords), 1) if keywords else 0

            # 正则匹配
            pattern_match = False
            for pat in patterns:
                if pat.search(message):
                    pattern_match = True
                    break

            # 综合得分
            if pattern_match:
                score = max(keyword_score, 0.5) + (priority * 0.01)
            elif matched_kw:
                score = keyword_score + (priority * 0.01)
            else:
                score = 0

            if score > 0.05:  # 阈值
                scored.append((score, intent, priority, matched_kw))

        if not scored:
            return None

        # 按 score 排序，同分取 priority 高的
        scored.sort(key=lambda x: (x[0], x[2]), reverse=True)
        best = scored[0]
        return (best[1], min(best[0], 1.0), f"rule:{best[1]}", best[3])

    # ---- 提示词组装 ----

    def _load_prompts(self) -> dict:
        """加载各意图的 prompt 模板"""
        prompts = {}
        rules_dir = Path(__file__).parent.parent / "rules"

        prompt_files = {
            "stock": "SKILL.md",  # 特殊处理：用根目录的 SKILL.md
            "career": "career_prompt.md",
            "life": "life_prompt.md",
        }

        for intent, filename in prompt_files.items():
            fpath = rules_dir / filename
            if not fpath.exists():
                # stock 特殊处理：指向项目根目录的 SKILL.md
                if intent == "stock":
                    fpath = Path(__file__).parent.parent / "SKILL.md"

            if fpath.exists():
                prompts[intent] = fpath.read_text(encoding="utf-8")

        return prompts

    def _build_system_prompt(self, intent: str, knowledge_context: str) -> str:
        """组装系统提示：角色框架 + 知识上下文"""
        base = self.prompt_templates.get(intent, "")
        if not base:
            return ""

        if knowledge_context:
            return f"""{base}

---

## 知识上下文（来自知识库检索）

{knowledge_context}

请基于以上知识内容，用你的思维框架回应用户的问题。
如果知识库内容与你的认知冲突，以你的判断为准。
"""
        return base


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    # 测试
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))

    router = IntentRouter()

    test_cases = [
        "帮我看看 600487 亨通光电，KDJ 金叉了吗",
        "我想辞职全职炒股，你觉得怎么样",
        "最近很焦虑，晚上总失眠",
        "今天天气怎么样",
        "B1 买点三个条件是什么",
        "35 岁了想转行做 AI，来得及吗",
        "该不该在北京买房",
    ]

    for msg in test_cases:
        result = router.process(msg)
        print(f"\n输入: {msg}")
        print(f"意图: {result.intent} (置信度={result.confidence:.2f})")
        print(f"规则: {result.rule_matched}")
        if result.matched_keywords:
            print(f"命中词: {result.matched_keywords}")
        print(f"知识卡片: {len(result.knowledge_context)} 字符")
        print(f"系统提示: {len(result.system_prompt)} 字符")
