"""收集来源，串联组装器，再按策略生成四路上下文。"""

from collections.abc import Callable, Iterable
from copy import deepcopy
from inspect import isawaitable

from domain.core import Module, access
from .context_strategy import STRATEGIES, assemble_packet, channel_filter

KINDS = tuple(STRATEGIES)
DEFAULT_CHANNELS = ("context.assembler", *("context.assembler." + kind for kind in KINDS))


class ContextAssemblerModule(Module):
    def __init__(
        self, config: dict | None = None, *,
        channels: str | Iterable[str] = DEFAULT_CHANNELS,
        strength: float = 1, channel_mode: str = "allow",
        read_text: Callable | None = None,
    ) -> None:
        super().__init__("context.assembler", description="上下文组装器",
                         channels=channels, strength=strength, channel_mode=channel_mode)
        self.config = deepcopy(config) if config is not None else {}
        self.read_text = read_text

    async def collect(self, config: dict | None = None) -> dict:
        config = self.config if config is None else config
        origin_id, packet = next(iter((await self._configured_sources(config)).items()))
        for strategy in STRATEGIES.values():
            try:
                for source in await strategy.collect(self, config, origin_id):
                    packet["errors" if "error" in source else "sources"].append(source)
            except Exception as error:
                packet["errors"].append(dict(source=strategy.kind, error=str(error)))
        return packet

    async def assemble(self, config: dict | None = None) -> dict:
        config = self.config if config is None else config
        packet = await self.collect(config)
        for downstream in await self._downstream_sources(config):
            packet["sources"].extend(downstream["sources"])
            packet["errors"].extend(downstream["errors"])
        return assemble_packet(packet)

    async def preview(self, config: dict | None = None) -> dict:
        return await self.assemble(config)

    @access(channels=())
    async def _configured_sources(self, node, config):
        sources, errors = [], []
        for source in config.get("sources", []):
            item = {**source, "id": "node:" + node.info.node_id + ":source:" + source["id"],
                    "source": source.get("path") if source["type"] == "file" else "直接文本", "channel": None}
            try:
                if source["type"] == "file":
                    data = self.read_text(source["path"], config.get("document_roots", []))
                    if isawaitable(data):
                        data = await data
                    item.update(text=data["text"], resolved_path=data["path"])
                sources.append(item)
            except Exception as error:
                errors.append(dict(source=item["source"], kind=item["kind"], error=str(error)))
        return dict(sources=sources, errors=errors)

    async def _downstream_sources(self, config):
        channels, mode = channel_filter(self, config, "channels", ("context.assembler",))

        @access(channels=channels, channel_mode=mode)
        async def collect(owner, node):
            relay = node.modules.get(self.module_id)
            if relay is None or relay is self:
                return None
            try:
                return await relay.collect()
            except Exception as error:
                return dict(sources=[], errors=[dict(source=node.info.node_id, error=str(error))])

        return [packet for packet in (await collect(self)).values() if packet is not None]
