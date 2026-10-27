"""按频道和强度执行单节点操作，遍历由装饰器内部统一完成。"""

from __future__ import annotations

from asyncio import create_task, gather
from collections.abc import Callable, Iterable, Iterator
from functools import wraps
from inspect import iscoroutinefunction
from math import isfinite
from typing import TYPE_CHECKING

from .channel_filters import declared_channels, normalize_channels as _normalize_channels, resolve, validate_mode

if TYPE_CHECKING:
    from .node import Node


def _validate_strength(value: float) -> float:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("强度必须是有限非负数")
    return value




def _layers(origin: Node, channels: tuple[str, ...], strength: float) -> Iterator[list[Node]]:
    """起点使用输入强度；目标先汇合再加偏置，负值不进入下一层。

    包含起点，每节点访问一次；不额外检查拓扑是否含环。
    """
    layer = [(origin, strength)]
    visited: set[str] = set()
    while layer:
        visited.update(node.info.node_id for node, _ in layer)
        yield [node for node, _ in layer]
        if not channels:
            return

        pending: dict[str, list[float]] = {}
        for node, remaining in layer:
            for link in node.links:
                if link.target_id in visited:
                    continue
                channel = next((item for item in channels if link.allows(remaining, item)), None)
                if channel is None:
                    continue
                transmitted = link.transmit(remaining, channel)
                if transmitted is not None:
                    pending.setdefault(link.target_id, []).append(_validate_strength(transmitted))

        layer = []
        for node_id, strengths in pending.items():
            target = origin._resolve(node_id) if origin._resolve is not None else None
            if target is None:
                raise ValueError(f"节点不存在：{node_id}")
            combined = _validate_strength(target.aggregation.combine(strengths))
            remaining = combined + target.bias
            if not isfinite(remaining):
                raise ValueError("偏置计算后的强度必须是有限数值")
            if remaining >= 0:
                layer.append((target, remaining))


def access(
    operation: Callable | None = None, *,
    channels: str | Iterable[str] | None = None, strength: float | None = None,
    channel_mode: str | None = None,
):
    """装饰 operation(self, node, ...)；调用时省略 node，返回 {节点ID: 结果}。

    省略的参数使用对象的 channels 和 strength；对象未设置时使用空频道和强度 1。
    显式参数优先；显式频道表默认白名单，空表只访问本节点。
    频道黑名单在每次调用时按当前已声明频道全集解析，与原平台一致。
    向外访问按广度分层推进，异步操作同层并发、整层结束后推进。
    同步操作保持逐节点执行。
    调用对象的 _access_origin 由装配方绑定，装饰器不依赖具体模块类型。
    """
    channels = None if channels is None else _normalize_channels(channels)
    strength = None if strength is None else _validate_strength(strength)
    channel_mode = None if channel_mode is None else validate_mode(channel_mode)

    def decorate(operation: Callable):
        def layers_for(owner):
            origin = owner._access_origin
            if origin is None:
                raise RuntimeError("操作所属对象尚未绑定节点")
            selected_channels = channels if channels is not None else _normalize_channels(
                getattr(owner, "channels", ()),
            )
            selected_strength = strength if strength is not None else _validate_strength(
                getattr(owner, "strength", 1),
            )
            # 显式频道表默认是白名单；省略频道时连同模块的匹配模式一起继承。
            selected_mode = channel_mode if channel_mode is not None else (
                getattr(owner, "channel_mode", "allow") if channels is None else "allow"
            )
            if selected_mode == "deny":
                universe = origin._channel_names() if origin._channel_names is not None else declared_channels((origin,))
                selected_channels = resolve(selected_channels, selected_mode, universe)
            else:
                validate_mode(selected_mode)
            return _layers(origin, selected_channels, selected_strength)

        if iscoroutinefunction(operation):
            @wraps(operation)
            async def invoke(owner, *args, **kwargs):
                results = {}
                for layer in layers_for(owner):
                    tasks = [create_task(operation(owner, node, *args, **kwargs)) for node in layer]
                    try:
                        values = await gather(*tasks)
                    except BaseException:
                        for task in tasks:
                            task.cancel()
                        await gather(*tasks, return_exceptions=True)
                        raise
                    results.update((node.info.node_id, value) for node, value in zip(layer, values))
                return results
        else:
            @wraps(operation)
            def invoke(owner, *args, **kwargs):
                return {node.info.node_id: operation(owner, node, *args, **kwargs)
                        for layer in layers_for(owner) for node in layer}
        return invoke

    return decorate if operation is None else decorate(operation)
