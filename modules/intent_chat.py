#!/usr/bin/env python3
"""
意图识别 + RAG + LLM 聊天界面

用法：
    python -m modules.intent_chat          # 交互模式
    python -m modules.intent_chat "B1 买点怎么判断"   # 单次查询
"""

import os
import sys

# 清除代理
for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    os.environ.pop(k, None)
os.environ["no_proxy"] = "localhost,127.0.0.1"

from .intent_router import IntentRouter  # noqa: E402

# 意图显示名称
INTENT_LABELS = {
    "stock": "📈 投资模式",
    "career": "💼 职业模式",
    "life": "🌊 人生模式",
    "chat": "💬 闲聊模式",
    "fallback": "🤔 默认模式",
}


def get_llm():
    """获取 LLM 实例

    如果未配置 LLM_API_KEY，返回 None，不影响主流程。
    """
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return None

    try:
        from .llm_providers import MiniMaxProvider

        return MiniMaxProvider(
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL"),
            model=os.getenv("LLM_MODEL"),
        )
    except Exception as e:
        print(f"[警告] LLM 初始化失败: {e}")
        return None


def generate_reply(llm, system_prompt: str, user_message: str) -> str:
    """生成回复"""
    if not llm:
        return "[未配置 LLM，请设置 MINIMAX_API_KEY]，系统提示已准备好。"
    return llm.generate(system_prompt, user_message)


def chat_once(router: IntentRouter, message: str, llm=None):
    """单次意图识别 + RAG + LLM 查询"""
    result = router.process(message)

    # 显示识别结果
    label = INTENT_LABELS.get(result.intent, result.intent)
    print(f"\n{'=' * 60}")
    print(f"🎯 意图: {label}")
    print(f"📊 置信度: {result.confidence:.0%}")
    if result.rule_matched:
        print(f"📏 匹配规则: {result.rule_matched}")
    if result.matched_keywords:
        print(f"🔑 命中词: {', '.join(result.matched_keywords[:5])}")

    # 显示知识库检索结果
    if result.knowledge_context:
        card_count = result.knowledge_context.count("---") // 2 + 1
        print(f"📚 知识卡片: {card_count} 条")
        # 显示卡片来源
        for line in result.knowledge_context.split("\n"):
            if line.startswith("[") and "] " in line:
                print(f"   {line}")

    print(f"📝 系统提示: {len(result.system_prompt)} 字符")
    print(f"{'=' * 60}\n")

    # 生成回复
    if result.intent == "chat":
        # chat 模式：不加载角色框架，直接用用户消息
        print("💬 闲聊模式，不加载角色框架\n")
        if llm:
            reply = llm.generate("", message)
        else:
            reply = "[未配置 LLM，无法生成回复]"
    else:
        # 加载角色框架 + 知识上下文
        if not result.system_prompt:
            print("[系统提示为空]")
            return
        print("🤖 正在生成回复...")
        reply = generate_reply(llm, result.system_prompt, message)

    print(f"\n{'=' * 60}")
    print(reply)
    print(f"{'=' * 60}\n")


def chat_interactive(router: IntentRouter, llm):
    """交互模式"""
    print("\n" + "=" * 60)
    print("Z哥意图识别聊天")
    if llm:
        print("LLM: MiniMax")
    else:
        print("LLM: 未配置（仅显示路由结果）")
    print("输入消息自动识别意图并检索知识库")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            message = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not message:
            continue
        if message.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        chat_once(router, message, llm)


def main():
    router = IntentRouter()
    llm = get_llm()

    if len(sys.argv) > 1:
        # 单次查询
        message = " ".join(sys.argv[1:])
        chat_once(router, message, llm)
    else:
        # 交互模式
        chat_interactive(router, llm)


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    main()
