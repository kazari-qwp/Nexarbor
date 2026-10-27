"""沿独立频道收集 Markdown 文件，按遍历顺序组装四路上下文。"""

from collections.abc import Callable, Iterable
from copy import deepcopy
from inspect import isawaitable

from domain.core import MarkdownNode, Module, Node, access
from domain.core.channel_filters import normalize_channels, validate_mode

KINDS = ("system_prompt", "context", "inputs", "tail")
DEFAULT_CHANNELS = ("context.assembler", *("context.assembler." + kind for kind in KINDS))


class ContextAssemblerModule(Module):
    def __init__(
        self, config: dict | None = None, *,
        channels: str | Iterable[str] = DEFAULT_CHANNELS,
        strength: float = 1, channel_mode: str = "allow",
        read_text: Callable | None = None,
    ) -> None:
        super().__init__(
            "context.assembler", description="上下文组装器",
            channels=channels, strength=strength, channel_mode=channel_mode,
        )
        self.config = deepcopy(config) if config is not None else {}
        # 由装配方显式授予文件端口；模块不持有后端或全局网络引用。
        self.read_text = read_text

    def _channel_filter(self, config: dict, field: str, default: tuple[str, ...]):
        """配置选择与模块授权取交集；deny 的频道全集仍由 access 解析。"""
        selected = normalize_channels(config.get(field, default))
        mode = validate_mode(config.get("channel_modes", {}).get(field, "allow"))
        granted = normalize_channels(self.channels)
        grant_mode = validate_mode(self.channel_mode)
        if mode == "allow":
            return tuple(c for c in selected if (c in granted) == (grant_mode == "allow")), "allow"
        if grant_mode == "allow":
            return tuple(sorted(c for c in granted if c not in selected)), "allow"
        return tuple(dict.fromkeys((*selected, *granted))), "deny"

    @access(channels=())
    async def _local_sources(self, node: Node, config: dict) -> dict:
        rows, errors = [], []
        for source in config.get("sources", []):
            item = {
                **source, "id": "node:" + node.info.node_id + ":source:" + source["id"],
                "source": source.get("path") if source["type"] == "file" else "直接文本",
                "channel": None,
            }
            try:
                if source["type"] == "file":
                    if self.read_text is None:
                        raise PermissionError("未授权 read_text 文件端口")
                    data = self.read_text(source.get("path", ""), config.get("document_roots", []))
                    if isawaitable(data):
                        data = await data
                    item.update(text=data["text"], resolved_path=data["path"])
                rows.append(item)
            except Exception as error:
                errors.append({"source": item["source"], "kind": item["kind"], "error": str(error)})
        return {"sources": rows, "errors": errors}

    async def _markdown_sources(self, kind: str, config: dict, origin_id: str) -> list[dict]:
        channels, mode = self._channel_filter(config, kind + "_channels", ("context.assembler." + kind,))

        @access(channels=channels, channel_mode=mode)
        async def read(owner, node: Node):
            if node.info.node_id == origin_id or not isinstance(node, MarkdownNode):
                return None
            source = {
                "id": "node:" + node.info.node_id, "kind": kind,
                "source": node.info.node_id, "channel": list(channels), "channel_mode": mode,
                "file": str(node.dataer.data.path), "resolved_path": str(node.dataer.data.path),
            }
            try:
                # 在访问到节点时读取，未来的节点访问门禁也覆盖这次文件操作。
                return {**source, "text": node.dataer.read(), "event_id": "once", "delivery": "followup"}
            except Exception as error:
                return {**source, "error": str(error)}

        return [source for source in (await read(self)).values() if source is not None]

    async def collect(self, config: dict | None = None) -> dict:
        """收集本组装器的来源；文件地址随来源返回，不记录网络访问路径。"""
        config = deepcopy(self.config if config is None else config)
        local = await self._local_sources(config)
        origin_id, packet = next(iter(local.items()))
        for kind in KINDS:
            try:
                for source in await self._markdown_sources(kind, config, origin_id):
                    packet["errors" if "error" in source else "sources"].append(source)
            except Exception as error:
                packet["errors"].append({"source": kind, "error": str(error)})
        return packet

    async def assemble(self, config: dict | None = None) -> dict:
        """按广度顺序合并下游 collect，避免递归将深层组装器提前插入。"""
        config = deepcopy(self.config if config is None else config)
        packet = await self.collect(config)
        channels, mode = self._channel_filter(config, "channels", ("context.assembler",))

        @access(channels=channels, channel_mode=mode)
        async def collect_downstream(owner, node: Node):
            relay = node.modules.get(self.module_id)
            if not isinstance(relay, ContextAssemblerModule) or relay is self:
                return None
            try:
                return await relay.collect()
            except Exception as error:
                return {"sources": [], "errors": [{"source": node.info.node_id, "error": str(error)}]}

        for downstream in (await collect_downstream(self)).values():
            if downstream is not None:
                packet["sources"].extend(downstream["sources"])
                packet["errors"].extend(downstream["errors"])
        return _assemble(packet)

    async def preview(self, config: dict | None = None) -> dict:
        """草稿预览与 assemble 同源，不修改配置、不消费输入事件。"""
        return await self.assemble(config)


def _assemble(packet: dict) -> dict:
    """沿用原来源身份、去重及四路 patch 规则；不排序。"""
    patch = {"system_prompt": "", "context": [], "inputs": [], "tail": []}
    seen, unique, errors = {}, [], packet["errors"]
    for item in packet["sources"]:
        kind, key = item["kind"], (item["kind"], item["id"])
        if key in seen:
            if seen[key].get("text") != item.get("text"):
                errors.append({"source": item["id"], "error": "同一来源在本次读取中内容发生变化"})
            continue
        seen[key] = item
        unique.append({**item, "matched": True})
        text = item.get("text", "")
        if not isinstance(text, str):
            errors.append({"source": item["id"], "error": "来源不是文本"})
            continue
        if not text.strip():
            continue
        if kind == "system_prompt":
            patch[kind] += ("\n\n" if patch[kind] else "") + text
        elif kind == "context":
            patch[kind].append({"id": item["id"], "text": text})
        elif kind == "tail":
            patch[kind].append(text)
        else:
            event = item.get("event_id") or "once"
            patch[kind].append({"id": item["id"] + "/" + event, "text": text, "delivery": item.get("delivery", "followup")})
    return {"format": "nexarbor-context/v1", "patch": patch, "sources": unique, "errors": errors}
