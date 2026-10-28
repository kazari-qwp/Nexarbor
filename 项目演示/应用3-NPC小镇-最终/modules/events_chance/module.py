"""地点概率事件；成功次数和请求者奖励在同一节点事务内提交。"""
import random
from copy import deepcopy
from app.runtime.requester import requester_id
from domain.core import Module, access


def _event_entries(config):
    """读取并校验事件配置，返回普通 Python 列表。"""
    events = config.get("events", [])
    if not isinstance(events, (list, tuple)):
        raise ValueError("事件配置必须是数组")

    normalized = []
    seen = set()
    for index, raw in enumerate(events, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 项事件必须是对象")
        event_id = raw.get("id")
        text = raw.get("text")
        probability = raw.get("probability", 0)
        limit = raw.get("limit")
        rewards = raw.get("rewards", {})
        triggers = raw.get("triggers", [])

        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"第 {index} 项事件缺少有效的事件标识")
        if event_id in seen:
            raise ValueError(f"事件标识重复：{event_id}")
        if not isinstance(text, str) or not text:
            raise ValueError(f"事件 {event_id} 缺少有效的事件文字")
        if (
            not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or probability < 0
            or probability > 1
        ):
            raise ValueError(f"事件 {event_id} 的触发概率必须在 0 到 1 之间")
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
        ):
            raise ValueError(f"事件 {event_id} 的成功次数上限必须是正整数或 null")
        if not isinstance(rewards, dict):
            raise ValueError(f"事件 {event_id} 的奖励必须是数字映射")
        if not isinstance(triggers, (list, tuple)):
            raise ValueError(f"事件 {event_id} 的触发筛选必须是字符串数组")

        clean_triggers = []
        seen_triggers = set()
        for trigger in triggers:
            if not isinstance(trigger, str) or not trigger:
                raise ValueError(f"事件 {event_id} 的触发筛选只能包含非空字符串")
            if trigger in seen_triggers:
                raise ValueError(f"事件 {event_id} 的触发筛选重复：{trigger}")
            seen_triggers.add(trigger)
            clean_triggers.append(trigger)

        clean_rewards = {}
        for field, amount in rewards.items():
            if (
                not isinstance(field, str)
                or not field
                or not isinstance(amount, (int, float))
                or isinstance(amount, bool)
                or amount < 0
            ):
                raise ValueError(f"事件 {event_id} 的奖励字段和数值必须是非负数字映射")
            clean_rewards[field] = amount

        seen.add(event_id)
        normalized.append(
            {
                "id": event_id,
                "text": text,
                "probability": probability,
                "limit": limit,
                "rewards": clean_rewards,
                "triggers": clean_triggers,
            }
        )
    return normalized


class EventsChanceModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('events.chance', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})

    @access()
    async def _participants(self, node):
        return node

    async def sample(self, trigger=''):
        if not isinstance(trigger, str):
            raise ValueError('触发入口必须是字符串')
        return next(iter((await self._sample(trigger)).values()))

    @access(channels=())
    async def _sample(self, node, trigger):
        _event_entries(self.config)
        requester = requester_id.get()
        if not isinstance(requester, str) or not requester:
            raise ValueError('缺少真实请求者，不能抽取地点事件')
        if requester == node.info.node_id:
            raise PermissionError('请求者不能是地点事件节点自身')
        participants = await self._participants()
        actor = participants.get(requester)
        if actor is None or actor.node_type != 'agent':
            raise PermissionError('只有真实 Agent 请求者才能抽取地点事件')

        observations, rewards = [], {}
        async with self.transaction([node.info.node_id, requester], timeout=20):
            events = _event_entries(self.config)
            counts = self.state.setdefault('counts', {})
            if not isinstance(counts, dict):
                raise ValueError('事件次数状态必须是对象')
            for event in events:
                counts.setdefault(event['id'], 0)
            for event in events:
                event_id = event['id']
                used = counts[event_id]
                if not isinstance(used, int) or isinstance(used, bool) or used < 0:
                    raise ValueError(f'事件 {event_id} 的成功次数状态非法')
                if event['triggers'] and trigger not in event['triggers']:
                    continue
                if event['limit'] is not None and used >= event['limit']:
                    continue
                if random.random() >= event['probability']:
                    continue
                counts[event_id] = used + 1
                observations.append(event['text'])
                for field, amount in event['rewards'].items():
                    rewards[field] = rewards.get(field, 0) + amount
            if rewards:
                try:
                    await actor.modules.get('records.store').apply(deltas=dict(rewards))
                except Exception as error:
                    raise RuntimeError(f'发放事件奖励失败：{error}') from error
            final_counts = {event['id']: int(counts[event['id']]) for event in events}
        return dict(observations=observations, rewards=rewards, counts=final_counts)
