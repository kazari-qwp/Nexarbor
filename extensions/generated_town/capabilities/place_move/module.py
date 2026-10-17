"""通用地点移动：地址节点公开 move_here，沿道路迁移人物的在场连接。"""
from dataclasses import replace

from datanet.core.access_budget import current_agent_id
from datanet.studio.contract import StudioModule

ARRIVAL_TRIGGER = 'arrive'
DEFAULT_COST = 3
DEFAULT_ROAD_CHANNELS = ('road',)
DEFAULT_PRESENCE_CHANNEL = 'presence'
DEFAULT_ENTITY_MODULE = 'entity.profile'
DEFAULT_ACTION_MODULE = 'action.points'
EFFECT_KEYS = ('coins', 'items', 'fields')


class Module(StudioModule):
    """地址节点上的移动入口；所有实例差异都来自 config。"""

    def setup(self):
        # 移动是即时的图与档案变更，不需要额外的持久业务状态。
        pass

    def tool_description(self, name, default):
        if name != 'move_here':
            return default
        return f'移动到「{self._place_name()}」（花费 {self._cost()} 点行动值）。'

    def move_here(self):
        """把当前 Agent 从其真实所在地点移动到本地点。"""
        agent_id = current_agent_id()
        if not isinstance(agent_id, str) or not agent_id:
            return self._failure('无法确认发起移动的人物身份，未移动。')
        network = self.backend.network
        agent = network.nodes.get(agent_id)
        if agent is None:
            return self._failure(f'发起移动的人物节点「{agent_id}」不在网络里，未移动。')
        try:
            place_id = self._current_place(agent_id)
        except (KeyError, PermissionError):
            return self._failure('人物资料组件不可用，无法确定当前位置，未移动。')
        if place_id is None:
            return self._failure('人物资料里没有记录当前位置（profile.place），未移动。')
        origin = network.nodes.get(place_id)
        if origin is None:
            return self._failure(f'人物记录的地点「{place_id}」不在网络里，未移动。')
        remaining = self._balance(agent_id)
        target = self.node
        if origin.node_id == target.node_id:
            return {
                'ok': True,
                'moved': False,
                'place': target.node_id,
                'place_name': self._place_name(),
                'cost': 0,
                'remaining': remaining,
                'message': f'你已经在「{self._place_name()}」，位置未变，未消耗行动值{self._remaining_text(remaining)}。',
            }
        if not self._road_link(origin, target):
            return self._failure(
                f'无法从「{origin.name}」移动到「{self._place_name()}」：两地之间没有直接相连的道路。',
                remaining,
            )
        cost = self._cost()
        events_ref = self._events_ref()
        arrivals = []
        try:
            with self.backend.modules.transaction(*self._transaction_nodes(agent_id, events_ref)):
                if cost > 0:
                    spent = self.backend.modules.call(agent_id, self._action_module(), 'spend', {'amount': cost})
                    if not isinstance(spent, dict) or not spent.get('ok'):
                        remaining = spent.get('remaining') if isinstance(spent, dict) else remaining
                        detail = f'剩余 {remaining} 点' if isinstance(remaining, int) else '剩余行动值未知'
                        return {
                            'ok': False,
                            'moved': False,
                            'place': target.node_id,
                            'place_name': self._place_name(),
                            'cost': 0,
                            'remaining': remaining,
                            'message': f'行动值不足：前往「{self._place_name()}」需要 {cost} 点，{detail}，未移动。',
                        }
                    remaining = spent.get('remaining')
                if events_ref is not None:
                    arrivals = self._draw_arrivals(agent_id, events_ref)
                self.backend.modules.call(
                    agent_id,
                    self._entity_module(),
                    'update_profile',
                    {'fields': {'place': target.node_id}},
                )
        except Exception as error:
            return self._failure(
                f'移动未完成，行动值、位置与资源均未改变：{self._error_text(error)}',
                self._balance(agent_id),
            )
        # 事件与效果都已成功落库，最后再迁移在场接口；接口迁移本身不改模块状态。
        self._move_presence(agent, origin, target)
        message = (
            f'你从「{origin.name}」沿道路来到「{self._place_name()}」，'
            f'消耗 {cost} 点行动值{self._remaining_text(remaining)}。'
        )
        lines = [item['message'] for item in arrivals if isinstance(item.get('message'), str) and item['message']]
        if lines:
            message += '\n到达时见闻：\n' + '\n'.join(lines)
        message += '\n你可以继续行动。'
        result = {
            'ok': True,
            'moved': True,
            'place': target.node_id,
            'place_name': self._place_name(),
            'cost': cost,
            'remaining': remaining,
            'message': message,
        }
        if events_ref is not None:
            result['events'] = arrivals
        return result

    # ---- config helpers -------------------------------------------------

    def _place_name(self):
        return self.config.get('place_name') or self.node.name

    def _cost(self):
        return self.config.get('cost', DEFAULT_COST)

    def _entity_module(self):
        return self.config.get('entity_module') or DEFAULT_ENTITY_MODULE

    def _action_module(self):
        return self.config.get('action_module') or DEFAULT_ACTION_MODULE

    def _road_channels(self):
        configured = self.config.get('road_channels')
        if not configured:
            return DEFAULT_ROAD_CHANNELS
        return tuple(configured)

    def _presence_channel(self):
        return self.config.get('presence_channel') or DEFAULT_PRESENCE_CHANNEL

    def _events_ref(self):
        reference = self.config.get('events_ref')
        return reference if reference else None

    @staticmethod
    def _transaction_nodes(agent_id, events_ref):
        nodes = [agent_id]
        if events_ref is not None and events_ref.get('node') != agent_id:
            nodes.append(events_ref['node'])
        return nodes

    # ---- profile, events and graph helpers ------------------------------

    def _current_place(self, agent_id):
        snapshot = self.backend.modules.call(agent_id, self._entity_module(), 'read', {})
        profile = snapshot.get('profile') if isinstance(snapshot, dict) else None
        place = profile.get('place') if isinstance(profile, dict) else None
        return place if isinstance(place, str) and place else None

    def _balance(self, agent_id):
        # 只用于展示剩余行动值；读取失败时保留 null，不因此改变移动结果。
        try:
            result = self.backend.modules.call(agent_id, self._action_module(), 'get_balance', {})
        except Exception:
            return None
        return result.get('remaining') if isinstance(result, dict) else None

    def _draw_arrivals(self, agent_id, events_ref):
        result = self.backend.modules.call(
            events_ref['node'],
            events_ref['module'],
            'draw',
            {
                'trigger': ARRIVAL_TRIGGER,
                'context': {'actor': agent_id, 'place': self.node.node_id},
            },
        )
        events = result.get('events') if isinstance(result, dict) else None
        if not isinstance(events, list):
            raise ValueError('事件组件返回格式不正确')
        arrivals = []
        for event in events:
            if not isinstance(event, dict):
                continue
            self._apply_effects(agent_id, event.get('effects'))
            arrivals.append({'id': event.get('id'), 'message': event.get('message')})
        return arrivals

    def _apply_effects(self, agent_id, effects):
        if not isinstance(effects, dict):
            return
        arguments = {key: effects[key] for key in EFFECT_KEYS if key in effects}
        if arguments:
            self.backend.modules.call(agent_id, self._entity_module(), 'adjust', arguments)

    def _road_link(self, origin, target):
        channels = set(self._road_channels())
        for source, other_id in ((origin, target.node_id), (target, origin.node_id)):
            for edge in source.interfaces:
                if edge.target_node_id == other_id and channels.intersection(edge.metadata.channels):
                    return True
        return False

    def _move_presence(self, agent, origin, target):
        channel = self._presence_channel()
        self._drop_channel(origin, agent.node_id, channel)
        self._drop_channel(agent, origin.node_id, channel)
        target.connect(agent.node_id, channels=[channel], threshold=1)
        agent.connect(target.node_id, channels=[channel], threshold=1)

    @staticmethod
    def _drop_channel(node, target_id, channel):
        kept = []
        for edge in node.interfaces:
            if edge.target_node_id != target_id or channel not in edge.metadata.channels:
                kept.append(edge)
                continue
            remaining = tuple(name for name in edge.metadata.channels if name != channel)
            if remaining:
                kept.append(replace(edge, metadata=replace(edge.metadata, channels=remaining)))
        node.interfaces[:] = kept

    # ---- result helpers -------------------------------------------------

    @staticmethod
    def _remaining_text(remaining):
        return f'，剩余 {remaining} 点' if isinstance(remaining, int) else ''

    @staticmethod
    def _error_text(error):
        if isinstance(error, (KeyError, PermissionError)):
            return '依赖组件不可用'
        text = str(error).strip()
        return text[:120] if text else error.__class__.__name__

    def _failure(self, message, remaining=None):
        return {
            'ok': False,
            'moved': False,
            'place': self.node.node_id,
            'place_name': self._place_name(),
            'cost': 0,
            'remaining': remaining,
            'message': message,
        }
