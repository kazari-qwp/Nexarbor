"""有向连接及节点出边集合。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field


DEFAULT_CHANNEL = "default"


@dataclass
class Multiplier:
    """默认的强度处理函数，乘数默认为 1。"""

    factor: float = 1

    def __call__(self, strength: float) -> float:
        return strength * self.factor


@dataclass(eq=False)
class Link:
    """先检查频道和输入阈值，通过后再处理强度。"""

    target_id: str
    channels: str | Iterable[str] = (DEFAULT_CHANNEL,)
    threshold: float = 0
    processor: Callable[[float], float] = field(default_factory=Multiplier)

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, str) or not self.target_id.strip():
            raise ValueError("目标节点 ID 必须是非空字符串")
        channels = (self.channels,) if isinstance(self.channels, str) else tuple(self.channels)
        if any(not isinstance(channel, str) or not channel.strip() for channel in channels):
            raise ValueError("频道名称必须是非空字符串")
        self.channels = tuple(dict.fromkeys(channels))
        if self.threshold < 0:
            raise ValueError("阈值不能为负数")
        if not callable(self.processor):
            raise TypeError("处理函数必须可调用")

    def allows(self, strength: float, channel: str = DEFAULT_CHANNEL) -> bool:
        return channel in self.channels and strength >= self.threshold

    def transmit(self, strength: float, channel: str = DEFAULT_CHANNEL) -> float | None:
        """被阻挡时返回 None；否则返回处理后的强度。"""
        if not self.allows(strength, channel):
            return None
        return self.processor(strength)


class Links:
    """按添加顺序管理出边，允许指向相同目标的多条连接。"""

    def __init__(self, links: Iterable[Link] = ()) -> None:
        self._links: list[Link] = []
        for link in links:
            self.add(link)

    def add(self, link: Link) -> None:
        """添加连接；同一连接对象不重复加入。"""
        if not isinstance(link, Link):
            raise TypeError("成员必须是 Link 实例")
        if not any(existing is link for existing in self._links):
            self._links.append(link)

    def remove(self, link: Link) -> bool:
        """按对象身份移除连接，返回是否移除。"""
        for index, existing in enumerate(self._links):
            if existing is link:
                del self._links[index]
                return True
        return False

    def __iter__(self) -> Iterator[Link]:
        return iter(self._links)

    def __len__(self) -> int:
        return len(self._links)

    def list(self) -> list[Link]:
        return list(self)
