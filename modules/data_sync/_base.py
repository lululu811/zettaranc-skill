"""SyncAdapter 协议定义。

每种数据类型的同步适配器必须实现此协议。
设计意图：让每种数据类型的 fetch → transform → upsert 管线
可以独立实例化、独立测试，不依赖完整 DataSyncer。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SyncAdapter(Protocol):
    """每种数据类型的同步适配器必须实现的接口。

    注意：这里用 Protocol 而非抽象基类，leverage 结构化子类型——
    现有 adapter 无需继承，只要实现同名方法即可。
    测试时可以用 MagicMock(spec=SyncAdapter) 或手写 stub。
    """

    def sync_one(self, **kwargs) -> int:
        """同步单条记录（单只股票/单日/全量），返回写入条数。"""
        ...

    def sync_batch(self, ts_codes: list[str] | None = None, **kwargs) -> dict[str, int]:
        """批量同步，返回 {ts_code: count}。"""
        ...
