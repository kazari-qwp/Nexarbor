"""沿用原平台的频道 allow/deny 匹配与已声明频道全集解析。"""

from collections.abc import Iterable


def normalize_channels(channels: str | Iterable[str]) -> tuple[str, ...]:
    channels = (channels,) if isinstance(channels, str) else tuple(channels)
    if any(not isinstance(channel, str) or not channel.strip() for channel in channels):
        raise ValueError("频道名称必须是非空字符串")
    return tuple(dict.fromkeys(channels))


def validate_mode(value: str) -> str:
    if value not in ("allow", "deny"):
        raise ValueError("频道模式必须是 allow 或 deny")
    return value


def matches(items, candidates, policy="allow") -> bool:
    selected = set(items)
    validate_mode(policy)
    return any((channel in selected) == (policy == "allow") for channel in candidates)


def resolve(items, policy="allow", universe=()) -> tuple[str, ...]:
    items = normalize_channels(items)
    validate_mode(policy)
    return tuple(channel for channel in universe if channel not in items) if policy == "deny" else items


def declared_channels(nodes) -> tuple[str, ...]:
    """与原 Network.channel_names 一样，每次从当前声明中取得频道全集。"""
    found = set()

    def scan(value, key=""):
        if isinstance(value, dict):
            for name, item in value.items():
                scan(item, name)
        elif isinstance(value, (list, tuple)):
            if "channels" in key:
                found.update(channel for channel in value if isinstance(channel, str))
            else:
                for item in value:
                    scan(item, key)

    for node in nodes:
        for link in node.links:
            found.update(link.channels)
        for module in node.modules:
            found.update(normalize_channels(module.channels))
            scan(getattr(module, "config", {}))
        for tool in node.tools:
            scan(getattr(tool, "access_channels", ()), "access_channels")
    return tuple(sorted(found))
