"""沿可达节点发现工具表，并串联途中遇到的工具发现模块。"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from hashlib import sha256
from inspect import isawaitable

from jsonschema import Draft202012Validator

from domain.core import access
from domain.core import Module
from domain.core import Node
from domain.core import Tools
from domain.core.channel_filters import declared_channels, resolve
from domain.declared_tool import DeclaredTool


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

    async def collect(self) -> list[dict]:
        """提供给执行器的来源目录；不把同名的不同来源压进一个 Tools。"""
        return await self._collect(frozenset())

    async def _collect(self, ancestors) -> list[dict]:
        if self in ancestors:
            return []
        branches = await self._collect_nodes(ancestors | {self})
        tools = {}
        for branch in branches.values():
            for item in branch:
                previous = tools.get(item["id"])
                if previous is None or len(item["via"]) < len(previous["via"]):
                    tools[item["id"]] = item
        return list(tools.values())

    def _visible(self, node, tool):
        if not isinstance(tool, DeclaredTool):
            return True
        channels = self.channels
        if self.channel_mode == "deny":
            universe = node._channel_names() if node._channel_names is not None else declared_channels((node,))
            channels = resolve(channels, "deny", universe)
        return tool.exposed_to(channels, local=node is self._access_origin)

    @access()
    async def _collect_nodes(self, node: Node, ancestors) -> list[dict]:
        tools = []
        relay = node.modules.get(self.module_id)
        if isinstance(relay, ToolDiscoveryModule) and relay not in ancestors:
            for item in await relay._collect(ancestors):
                tools.append(dict(item, via=[node.info.node_id, *item["via"]]))
        for tool in node.tools:
            if not self._visible(node, tool):
                continue
            reference = tool.reference if isinstance(tool, DeclaredTool) else tool.name
            tools.append(dict(
                id=tool_id(node.info.node_id, reference), name=tool.name,
                description=tool.description, parameters=deepcopy(tool.parameters or {"type": "object"}),
                origin=dict(node_id=node.info.node_id, tool=reference), via=[],
            ))
        return tools

    async def invoke(self, identifier: str, arguments: dict):
        """每次重新发现并逐段执行，保留的工具句柄不能越过撤销后的连线。"""
        return await self._invoke(identifier, arguments, frozenset())

    async def _invoke(self, identifier, arguments, ancestors):
        if self in ancestors:
            raise PermissionError("工具来源已不再可达")
        selected = next((item for item in await self._collect(ancestors) if item["id"] == identifier), None)
        if selected is None:
            raise PermissionError("工具来源已不再可达")
        results = await self._invoke_nodes(selected, arguments, ancestors | {self})
        for found, result in results.values():
            if found:
                return result
        raise PermissionError("工具来源已不再可达")

    @access()
    async def _invoke_nodes(self, node: Node, selected, arguments, ancestors):
        if selected["via"]:
            if node.info.node_id == selected["via"][0]:
                relay = node.modules.get(self.module_id)
                if isinstance(relay, ToolDiscoveryModule):
                    return True, await relay._invoke(selected["id"], arguments, ancestors)
        elif node.info.node_id == selected["origin"]["node_id"]:
            for tool in node.tools:
                reference = tool.reference if isinstance(tool, DeclaredTool) else tool.name
                if reference != selected["origin"]["tool"] or not self._visible(node, tool):
                    continue
                Draft202012Validator(tool.parameters or {"type": "object"}).validate(arguments)
                result = tool.invoke(**arguments)
                if isawaitable(result):
                    result = await result
                return True, result
        return False, None


def tool_id(node_id: str, reference: str) -> str:
    return "tool_" + sha256((node_id + "\0" + reference).encode()).hexdigest()[:24]
