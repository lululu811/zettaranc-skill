#!/usr/bin/env python3
"""意图识别 + 知识库检索 测试"""

import sys
import os
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

# 清除代理，避免知识库 API 请求走代理
for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(k, None)
os.environ["no_proxy"] = "localhost,127.0.0.1"

from modules.intent_router import IntentRouter  # noqa: E402


def test_rule_match():
    """规则匹配测试"""
    router = IntentRouter()

    cases = [
        # (input, expected_intent)
        ("帮我看看 600487 亨通光电", "stock"),
        ("B1 买点怎么判断", "stock"),
        ("KDJ 金叉了吗", "stock"),
        ("我想辞职全职炒股", "career"),
        ("35 岁想转行做 AI", "career"),
        ("副业搞钱怎么做", "career"),
        ("最近很焦虑，失眠", "life"),
        ("该不该在北京买房", "life"),
        ("结婚前要看什么", "life"),
        ("今天天气怎么样", "chat"),
        ("帮我写封邮件", "chat"),
        ("000001.SZ 分析一下", "stock"),
        ("MACD 顶背离怎么看", "stock"),
        ("创业失败怎么办", "career"),
        ("孩子教育问题", "life"),
    ]

    passed = 0
    failed = 0

    for msg, expected in cases:
        result = router.process(msg)
        status = "✅" if result.intent == expected else "❌"
        if result.intent != expected:
            failed += 1
        else:
            passed += 1
        print(f"  {status} [{result.intent}] {msg}")
        if result.rule_matched:
            print(f"       规则: {result.rule_matched}")
        if result.matched_keywords:
            print(f"       命中词: {result.matched_keywords[:5]}")

    print(f"\n规则匹配: {passed} passed, {failed} failed")
    assert failed == 0


def test_kb_retrieval():
    """知识库检索测试"""
    router = IntentRouter()

    cases = [
        ("B1 买点怎么判断", "stock"),
        ("三波理论是什么", "stock"),
        ("我想辞职创业", "career"),
        ("最近很焦虑怎么办", "life"),
    ]

    for query, intent in cases:
        cards = router.kb_retriever.retrieve(query, intent)
        print(f"\n=== {intent} | {query} ===")
        print(f"  检索到 {len(cards)} 条")
        for c in cards[:2]:
            print(f"  [{c.category}] score={c.score}")
            print(f"  source: {c.source.split('/')[-1]}")


def test_system_prompt():
    """系统提示组装测试"""
    router = IntentRouter()

    result = router.process("B1 买点怎么判断")
    print("\n=== stock prompt 长度 ===")
    print(f"  system_prompt: {len(result.system_prompt)} 字符")
    print(f"  knowledge_context: {len(result.knowledge_context)} 字符")
    print(f"  前 200 字: {result.system_prompt[:200]}...")

    result = router.process("今天天气怎么样")
    print("\n=== chat prompt ===")
    print(f"  system_prompt: '{result.system_prompt}'")
    print(f"  knowledge_context: '{result.knowledge_context}'")


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1: 意图识别 + 知识库检索测试")
    print("=" * 60)

    print("\n--- 1. 规则匹配测试 ---")
    rule_ok = test_rule_match()

    print("\n--- 2. 知识库检索测试 ---")
    test_kb_retrieval()

    print("\n--- 3. 系统提示组装测试 ---")
    test_system_prompt()

    print("\n" + "=" * 60)
    if rule_ok:
        print("Phase 1 PASS")
    else:
        print("Phase 1 FAILED - 规则匹配有错误")
    print("=" * 60)
