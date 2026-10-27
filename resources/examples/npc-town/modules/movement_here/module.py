"""目的地移动工具；前置钩子、位置资料与双向位置边使用同一事务。"""

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller, as_requester, requester_id
from domain.annotated_link import AnnotatedLink
from domain.core import CallableTool, Module, Multiplier, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))


def connected(edges, target, relation):
    channels = {'location', 'movement', 'road'} if relation == 'location' else {'movement', 'road'}
    return any(edge.target_id == target and getattr(edge, 'attributes', {}).get('relation') == relation
               and channels.intersection(edge.channels) for edge in edges)


def location_channels(module):
    channels=thaw(module.config.get('location_channels',('location',)))
    if not isinstance(channels,list) or not channels:
        raise ValueError('新位置边频道必须是非空字符串数组')
    if any(not isinstance(channel,str) or not channel for channel in channels):
        raise ValueError('新位置边频道必须是非空字符串')
    if len(set(channels))!=len(channels):
        raise ValueError('新位置边频道不能重复')
    if not {'location','movement','road'}.intersection(channels):
        raise ValueError('新位置边频道必须包含 location、road 或 movement')
    if 'self' in channels:
        raise ValueError('新位置边频道不能包含 self 频道')
    return channels


def _add_location(node, target, channels):
    for edge in node.links:
        if edge.target_id == target and edge.channels == tuple(channels) and edge.threshold == 1 and edge.channel_mode == 'allow' and type(edge.processor) is Multiplier and edge.processor.factor == 1 and getattr(edge, 'attributes', {}) == {'relation':'location'}:
            return
    node.links.add(AnnotatedLink(target, channels, threshold=1, attributes={'relation':'location'}))


class MovementHereModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('movement.here', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], self.move, spec['description'], deepcopy(spec['parameters'])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id + '\0' + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = 'mod_' + sha256((source_id + '\0' + spec['id']).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + ' · ' + spec['name'] + ' · ' + spec['description']

    @access()
    async def _participants(self, node):
        return node

    async def _call(self, participants, target, operation, arguments=None, module_id='place.info'):
        with as_caller(self._access_origin.info.node_id):
            return await getattr(participants[target].modules.get(module_id), operation)(**(arguments or {}))

    async def _run_hooks(self, participants, actor, old, destination):
        targets = {'requester':actor, 'origin':old, 'destination':destination}
        results = []
        for index, hook in enumerate(self.config.get('before_hooks', ())):
            key = hook.get('target')
            if key not in targets:raise ValueError('第 %d 个移动前钩子的目标无效' % (index+1))
            module = hook.get('module');operation = hook.get('operation')
            if not isinstance(module, str) or not module or not isinstance(operation, str) or not operation:
                raise ValueError('第 %d 个移动前钩子必须填写模块和操作' % (index+1))
            arguments = thaw(hook.get('arguments', {}))
            if not isinstance(arguments, dict):raise ValueError('第 %d 个移动前钩子的参数必须是对象' % (index+1))
            try:data = await self._call(participants, targets[key], operation, arguments, module)
            except Exception as error:
                raise RuntimeError('移动前钩子第 %d 项失败：%s' % (index+1,error)) from error
            results.append(dict(target=key, module=module, operation=operation, data=thaw(data) if data is not None else None))
        return results

    async def move(self):
        try:
            async with asyncio.timeout(self.config.get('timeout_seconds', 15)):
                return next(iter((await self._move()).values()))
        except Exception as error:
            raise RuntimeError('移动未完成：' + (str(error) or '等待或执行超时，请重试')) from error

    @access(channels=())
    async def _move(self, node):
        channels = location_channels(self)
        destination_id = node.info.node_id
        actor = requester_id.get() or destination_id
        participants = await self._participants()
        actor_node = participants[actor]
        if actor_node.node_type != 'agent':raise ValueError('移动请求必须由 Agent 发起')
        with as_requester(actor):
            before = await self._call(participants, actor, 'read')
            old = before['location']
            if not old:raise ValueError('NPC 尚未设置初始所在地点，请装配位置资料')
            if old == destination_id:return dict(moved=False, location=destination_id, before_results=[])
            async with self.transaction([actor, old, destination_id]):
                current = await self._call(participants, actor, 'read')
                if current['location'] != old:raise RuntimeError('等待期间位置已变化，请重新选择目的地')
                old_edges = tuple(participants[old].links)
                new_edges = tuple(node.links)
                actor_edges = tuple(actor_node.links)
                if not connected(old_edges, destination_id, 'road') or not connected(new_edges, old, 'road'):
                    raise ValueError('目的地必须与旧地点有双向相邻道路')
                if not connected(actor_edges, old, 'location') or not connected(old_edges, actor, 'location'):
                    raise ValueError('NPC 的位置资料与双向位置连接不一致')
                before_results = await self._run_hooks(participants, actor, old, destination_id)
                _add_location(actor_node, destination_id, channels)
                destination = await self._call(participants, destination_id, 'read')
                await self._call(participants, destination_id, 'arrive', {'visitor':actor})
                await self._call(participants, old, 'leave', {'visitor':actor})
                await self._call(participants, actor, 'set_location', {'location':destination_id, 'description':destination['name']+'：'+destination['description']})
                for source, target, edges in ((actor_node, old, actor_edges), (participants[old], actor, old_edges)):
                    for edge in edges:
                        if edge.target_id == target and getattr(edge, 'attributes', {}).get('relation') == 'location':
                            source.links.remove(edge)
                _add_location(node, actor, channels)
        return dict(moved=True, from_location=old, location=destination_id, description=destination['description'], before_results=before_results)
