"""按频道和强度执行单节点操作，遍历由装饰器内部统一完成。"""

from __future__ import annotations

from asyncio import create_task, gather
from collections.abc import Callable, Iterable
from contextlib import nullcontext
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




def _scope(origin, node_id, *, asynchronous):
    guard = origin._access_guard
    if guard is None:
        return nullcontext()
    return guard.access([node_id], mutable=False) if asynchronous else guard.access_sync([node_id], mutable=False)


def _node_at(origin, node_id):
    node = origin if node_id == origin.info.node_id else origin._resolve(node_id) if origin._resolve is not None else None
    if node is None:
        raise ValueError(f"节点不存在：{node_id}")
    return node


def _received(node, strengths, *, first):
    remaining = strengths[0] if first else _validate_strength(node.aggregation.combine(strengths)) + node.bias
    if not isfinite(remaining):
        raise ValueError("偏置计算后的强度必须是有限数值")
    return remaining


def _outgoing(node, remaining, channels, mode, visited):
    if mode == "deny":
        universe = node._channel_names() if node._channel_names is not None else declared_channels((node,))
        channels = resolve(channels, mode, universe)
    result = []
    for link in node.links:
        if link.target_id in visited:
            continue
        channel = next((item for item in channels if link.allows(remaining, item)), None)
        if channel is not None:
            transmitted = link.transmit(remaining, channel)
            if transmitted is not None:
                result.append((link.target_id, _validate_strength(transmitted)))
    return result


def _pending(branches):
    pending = {}
    for branch in branches:
        for node_id, strength in branch:
            pending.setdefault(node_id, []).append(strength)
    return pending


async def _gather(operations):
    tasks = [create_task(operation) for operation in operations]
    try:
        return await gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await gather(*tasks, return_exceptions=True)
        raise



def access(
    operation: Callable | None = None, *,
    channels: str | Iterable[str] | None = None, strength: float | None = None,
    channel_mode: str | None = None,
):
    """装饰 operation(self, node, ...)；调用时省略 node，返回 {节点ID: 结果}。

    省略的参数使用对象的 channels 和 strength；对象未设置时使用空频道和强度 1。
    显式参数优先；显式频道表默认白名单，空表只访问本节点。
    频道黑名单推进时按当前声明解析；锁定节点解锁后使用恢复或提交的出边。
    向外访问按广度分层推进，异步操作同层并发、整层结束后推进。
    同步操作保持逐节点执行。节点门禁同时保护汇合、偏置、操作和出边读取。
    调用对象的 _access_origin 由装配方绑定，装饰器不依赖具体模块类型。
    """
    channels = None if channels is None else _normalize_channels(channels)
    strength = None if strength is None else _validate_strength(strength)
    channel_mode = None if channel_mode is None else validate_mode(channel_mode)

    def decorate(operation: Callable):
        def policy_for(owner):
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
            validate_mode(selected_mode)
            return origin, selected_channels, selected_strength, selected_mode

        if iscoroutinefunction(operation):
            @wraps(operation)
            async def invoke(owner, *args, **kwargs):
                origin, selected_channels, selected_strength, selected_mode = policy_for(owner)
                pending = {origin.info.node_id: [selected_strength]}
                results, visited = {}, set()
                first = True

                async def visit(node_id, strengths, first):
                    async with _scope(origin, node_id, asynchronous=True):
                        node = _node_at(origin, node_id)
                        remaining = _received(node, strengths, first=first)
                        if remaining < 0:
                            return None
                        return node_id, remaining, await operation(owner, node, *args, **kwargs)

                async def advance(node_id, remaining):
                    async with _scope(origin, node_id, asynchronous=True):
                        return _outgoing(_node_at(origin, node_id), remaining, selected_channels, selected_mode, visited)

                while pending:
                    layer = [value for value in await _gather(visit(node_id, strengths, first)
                             for node_id, strengths in pending.items()) if value is not None]
                    first = False
                    visited.update(node_id for node_id, _, _ in layer)
                    results.update((node_id, value) for node_id, _, value in layer)
                    if not selected_channels and selected_mode == "allow":
                        break
                    pending = _pending(await _gather(advance(node_id, remaining) for node_id, remaining, _ in layer))
                return results
        else:
            @wraps(operation)
            def invoke(owner, *args, **kwargs):
                origin, selected_channels, selected_strength, selected_mode = policy_for(owner)
                pending = {origin.info.node_id: [selected_strength]}
                results, visited = {}, set()
                first = True
                while pending:
                    layer = []
                    for node_id, strengths in pending.items():
                        with _scope(origin, node_id, asynchronous=False):
                            node = _node_at(origin, node_id)
                            remaining = _received(node, strengths, first=first)
                            if remaining >= 0:
                                results[node_id] = operation(owner, node, *args, **kwargs)
                                layer.append((node_id, remaining))
                    first = False
                    visited.update(node_id for node_id, _ in layer)
                    if not selected_channels and selected_mode == "allow":
                        break
                    branches = []
                    for node_id, remaining in layer:
                        with _scope(origin, node_id, asynchronous=False):
                            branches.append(_outgoing(_node_at(origin, node_id), remaining, selected_channels, selected_mode, visited))
                    pending = _pending(branches)
                return results
        return invoke

    return decorate if operation is None else decorate(operation)
