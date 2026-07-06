#!/usr/bin/env python3
"""
Z哥量化预警推送模块
支持 macOS 系统级弹窗与 飞书/钉钉 webhook 主动推送
"""

import os
import subprocess
import logging
import requests
from typing import Any

logger = logging.getLogger("zettaranc-notifier")


def escape_applescript_string(s: str) -> str:
    """对字符串进行 AppleScript 安全转义"""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def notify_macos(title: str, message: str, sound_name: str = "Glass") -> bool:
    """
    通过 macOS 系统的 osascript 发送系统通知
    """
    try:
        title_esc = escape_applescript_string(title)
        msg_esc = escape_applescript_string(message)

        # 组装 AppleScript 指令
        script = f'display notification "{msg_esc}" with title "{title_esc}"'
        if sound_name:
            script += f' sound name "{sound_name}"'

        cmd = ["osascript", "-e", script]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        logger.error("macOS 通知发送失败: %s", e)
        return False


def notify_feishu(webhook_url: str, title: str, message: str) -> bool:
    """
    向飞书/Lark群机器人 Webhook 发送主动通知
    """
    if not webhook_url:
        return False
    try:
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": f"🔔 【{title}】\n{message}"}}
        headers = {"Content-Type": "application/json"}
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("飞书 Webhook 发送失败: %s", e)
        return False


def notify_all(title: str, message: str, webhook_url: str | None = None) -> dict[str, bool]:
    """
    全通路推送：系统通知 + 飞书推送（如果配置了）
    """
    results = {}

    # 1. 尝试 macOS 本地通知
    # 只有当系统是 mac 时才进行
    try:
        sysname = os.uname().sysname
    except AttributeError:
        sysname = "Unknown"

    if sysname == "Darwin":
        results["macos"] = notify_macos(title, message)
    else:
        results["macos"] = False

    # 2. 尝试飞书通知
    url = webhook_url or os.getenv("IM_PUSH_WEBHOOK")
    if url:
        results["feishu"] = notify_feishu(url, title, message)
    else:
        results["feishu"] = False

    return results


if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    import sys

    # 简单自测
    print("测试发送 macOS 通知...")
    res = notify_all("Z哥量化测试", "这是一条测试警报，一切正常！")
    print(f"发送结果: {res}")
