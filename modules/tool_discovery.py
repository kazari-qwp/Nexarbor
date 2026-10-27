"""沿可达节点发现工具表，并串联途中遇到的工具发现模块。"""

from __future__ import annotations

from collections.abc import Iterable

from domain.core import access
from domain.core import Module
from domain.core import Node
from domain.core import Tools


class ToolDiscoveryModule(Module):
    def __init__(self, channels: str | Iterable[str], strength: float, *, channel_mode: str = "allow") -> None:
        super().__init__(
            "tool_discovery", description="串联工具发现", channels=channels, strength=strength, channel_mode=channel_mode,
        )

    def discover(self) -> Tools:
        """返回各工具表引用组成的工具箱；每次调用重新确定可达节点。"""
        sources = self._discover(set())
        return Tools(sources.values())

    def _discover(self, visited: set[ToolDiscoveryModule]) -> dict[str, Tools]:
        if self in visited:
            return {}
        visited.add(self)
        sources: dict[str, Tools] = {}
        for branch in self._read_nodes(visited).values():
            sources.update(branch)
        return sources

    @access()
    def _read_nodes(self, node: Node, visited: set[ToolDiscoveryModule]) -> dict[str, Tools]:
        sources = {node.info.node_id: node.tools}
        relay = node.modules.get("tool_discovery")
        if isinstance(relay, ToolDiscoveryModule) and relay not in visited:
            sources.update(relay._discover(visited))
        return sources
