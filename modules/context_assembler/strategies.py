"""四类上下文的收集与组装策略。"""

from abc import ABC, abstractmethod

from domain.core import MarkdownNode, access


def channel_filter(owner, config, field, default):
    selected = config.get(field, default)
    selected = (selected,) if isinstance(selected, str) else tuple(selected)
    mode = config.get("channel_modes", {}).get(field, "allow")
    granted = (owner.channels,) if isinstance(owner.channels, str) else owner.channels
    if mode == "allow":
        return tuple(c for c in selected if (c in granted) == (owner.channel_mode == "allow")), "allow"
    if owner.channel_mode == "allow":
        return tuple(c for c in granted if c not in selected), "allow"
    return tuple(dict.fromkeys((*selected, *granted))), "deny"


class ContextStrategy(ABC):
    kind: str

    async def collect(self, owner, config, origin_id):
        channels, mode = channel_filter(owner, config, self.kind + "_channels", ("context.assembler." + self.kind,))

        @access(channels=channels, channel_mode=mode)
        async def read(module, node):
            if node.info.node_id == origin_id or not isinstance(node, MarkdownNode):
                return None
            source = dict(
                id="node:" + node.info.node_id, kind=self.kind, source=node.info.node_id,
                channel=list(channels), channel_mode=mode,
                file=str(node.dataer.data.path), resolved_path=str(node.dataer.data.path),
                event_id="once", delivery="followup",
            )
            try:
                source["text"] = node.dataer.read()
            except Exception as error:
                source["error"] = str(error)
            return source

        return [source for source in (await read(owner)).values() if source is not None]

    def initial(self):
        return []

    @abstractmethod
    def append(self, value, source):
        pass


class SystemPromptStrategy(ContextStrategy):
    kind = "system_prompt"

    def initial(self):
        return ""

    def append(self, value, source):
        return value + ("\n\n" if value else "") + source["text"]


class ContextDocumentStrategy(ContextStrategy):
    kind = "context"

    def append(self, value, source):
        value.append(dict(id=source["id"], text=source["text"]))
        return value


class InputEventStrategy(ContextStrategy):
    kind = "inputs"

    def append(self, value, source):
        event = source.get("event_id") or "once"
        value.append(dict(id=source["id"] + "/" + event, text=source["text"],
                          delivery=source.get("delivery", "followup")))
        return value


class TailStrategy(ContextStrategy):
    kind = "tail"

    def append(self, value, source):
        value.append(source["text"])
        return value


STRATEGIES = {strategy.kind: strategy for strategy in (
    SystemPromptStrategy(), ContextDocumentStrategy(), InputEventStrategy(), TailStrategy(),
)}


def assemble_packet(packet):
    patch = {kind: strategy.initial() for kind, strategy in STRATEGIES.items()}
    seen, sources = set(), []
    for source in packet["sources"]:
        kind = source["kind"]
        key = kind, source["id"]
        if key in seen:
            continue
        seen.add(key)
        sources.append({**source, "matched": True})
        if source.get("text", "").strip():
            patch[kind] = STRATEGIES[kind].append(patch[kind], source)
    return dict(format="nexarbor-context/v1", patch=patch, sources=sources, errors=packet["errors"])
