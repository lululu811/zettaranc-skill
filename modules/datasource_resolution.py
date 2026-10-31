"""数据源决议 —— 「当前配置下该用哪个 provider」的唯一来源。

本模块是纯函数：不读数据库、不构造数据源、不发网络请求，只把环境变量翻译成
一个 provider 名。这样读路径与写路径可以共用同一套判断，而不必各自抄一份。

## 为什么要有这个 module

读路径（``CompositeDataSource``）与写路径（``DataSyncer``）此前各写了一份
"环境变量 → provider"的判断，而且**已经漂移**：

- 写路径没有 hithink 分支 —— 配了 ``HITHINK_FINANCE_API_KEY`` 的用户，
  ``zt analyze`` 走同花顺官方数据，``zt sync`` 却走免费源，两边数据对不上。
- 顶层 CLI 的 ``zt sync`` 直接钉死 ``get_datasource("tushare")``，绕过了任何
  决议 —— 在默认的 websearch 模式下 tushare 没有数据后端（``_pro is None``），
  取数恒返回 None，命令却打印"同步完成"。

现在两条路径都消费本模块的 ``resolve_provider()``。

## 优先级

============================================  ==========================
条件                                           选中的 provider
============================================  ==========================
``HITHINK_FINANCE_API_KEY``                   hithink（同花顺官方）
``INDEVS_API_KEY``                            indevs
``DATA_MODE=jnb`` 且 ``TUSHARE_TOKEN``        tushare
  且 ``TUSHARE_API_URL``
其它                                           无（调用方回退 a-stock-data 免费源）
============================================  ==========================

websearch 模式下 ``TushareClient._pro is None``（无数据后端），即使配了
``TUSHARE_TOKEN`` 也不路由 tushare —— 那等于把请求送到一个必然返回 None 的源。

JNB 模式同理：``TushareClient.__init__`` 要求 ``TUSHARE_TOKEN`` **与**
``TUSHARE_API_URL`` 两项齐全才可用，缺任一项都抛 ``CONFIG_MISSING``。只判
token 会让决议说 "tushare" 而实际构造失败回退——决议与实际用的源不一致。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResolution:
    """一次数据源决议的结果。

    Attributes:
        provider: 选中的 provider 名（``'hithink'`` / ``'indevs'`` / ``'tushare'``）；
            ``None`` 表示没有配置任何数据源，调用方应回退免费源（a-stock-data）。
        reason: 决议依据。写进日志与测试断言——"为什么选它"不该只能靠读代码。
    """

    provider: str | None
    reason: str

    @property
    def uses_free_source(self) -> bool:
        """是否应回退免费源（未配置任何 provider）。"""
        return self.provider is None

    def describe(self) -> str:
        """人类可读描述（日志用）。"""
        return f"{self.provider or 'a-stock-data'}（{self.reason}）"


def resolve_provider() -> ProviderResolution:
    """按环境变量解析 auto 模式的首选 provider。

    这是"环境变量 → provider"规则的唯一定义处。读路径
    （``CompositeDataSource``）与写路径（``DataSyncer``）都调它，
    因此两边的选择永远一致。

    Returns:
        ProviderResolution(provider, reason)。
    """
    if os.environ.get("HITHINK_FINANCE_API_KEY"):
        return ProviderResolution("hithink", "配置了 HITHINK_FINANCE_API_KEY")
    if os.environ.get("INDEVS_API_KEY"):
        return ProviderResolution("indevs", "配置了 INDEVS_API_KEY")
    if os.environ.get("DATA_MODE", "websearch") == "jnb":
        token = os.environ.get("TUSHARE_TOKEN")
        api_url = os.environ.get("TUSHARE_API_URL")
        # JNB 模式下 tushare 要**两项**配置齐全才能用：``TushareClient.__init__``
        # 缺任一项都抛 CONFIG_MISSING（见该文件的 JNB 检查）。只判 token 会让
        # 决议说 "tushare" 而实际构造时回退 a-stock-data —— 决议与实际用的源
        # 不一致。判定口径必须与构造条件一致。
        if token and api_url:
            return ProviderResolution("tushare", "JNB 模式且配置了 TUSHARE_TOKEN 与 TUSHARE_API_URL")
    return ProviderResolution(None, "未配置数据源，走免费源兜底")


__all__ = ["ProviderResolution", "resolve_provider"]
