"""网络只管理内存中的节点，出边由各节点持有。"""

from collections.abc import Iterable, Iterator

from .node import Node
from .channel_filters import declared_channels


class Network:
    def __init__(self, nodes: Iterable[Node] = ()) -> None:
        self._nodes: dict[str, Node] = {}
        for node in nodes:
            self.add(node)

    def add(self, node: Node) -> None:
        node_id = node.info.node_id
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("节点 ID 必须是非空字符串")
        existing = self._nodes.get(node_id)
        if existing is not None and existing is not node:
            raise ValueError(f"节点 ID 冲突：{node_id}")
        if node._resolve is not None and node._resolve != self.get:
            raise ValueError("同一个节点不能同时属于两个网络")
        self._nodes[node_id] = node
        node._resolve = self.get
        node._channel_names = self.channel_names

    def channel_names(self) -> tuple[str, ...]:
        return declared_channels(self._nodes.values())

    def get(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def __iter__(self) -> Iterator[Node]:
        return iter(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)
