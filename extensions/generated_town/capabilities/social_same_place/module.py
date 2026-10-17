"""通用同场所交流：每个 Agent 挂一个可被同场者远程调用的 talk 端点。

本实例始终代表“收话者”——它所在节点就是消息的接收者。发起者由
datanet.core.access_budget.current_agent_id() 取得，绝不作为工具参数暴露。
"""
import uuid

from datanet.core.access_budget import current_agent_id
from datanet.studio.contract import StudioModule

GONE_MESSAGE = '他好像已经去了某地点，已经不在这里了'

DEFAULT_SOURCE = 'social.same_place'


class Module(StudioModule):
    """收话者 Agent 上的同场所交流端点。"""

    def tool_description(self, name, default):
        if name != 'talk':
            return default
        who = self._receiver_name()
        return (
            f'和{who}说一句话。{who}和你在同一场所时，这句话会带上你的姓名写进{who}的输入，'
            f'由{who}在下次模型请求时自行处理；不会立刻唤醒{who}，也不会自动回复。'
            f'发送会消耗你的行动值。'
        )

    def on_tool_denied(self, name, actor, reason):
        """解释“曾经可见的 talk 现在已不可达”；只读资料，不扣费、不投递、不改状态。"""
        if name != 'talk':
            return reason
        if not isinstance(actor, str) or not actor or actor == self.node.node_id:
            return reason
        receiver_fields = self._profile(self.node.node_id)
        receiver_place = self._place(receiver_fields)
        sender_fields = self._profile(actor)
        sender_place = self._place(sender_fields)
        if receiver_place is None or sender_place is None or receiver_place == sender_place:
            return reason
        who = self._receiver_name(receiver_fields)
        place_name = self._place_label(receiver_place)
        return f'{who}好像已经去了「{place_name}」，已经不在这里了'

    def talk(self, message):
        text = message.strip() if isinstance(message, str) else ''
        if not text:
            return self._failure('empty_message', '要说的话不能为空，没有发送。')

        sender_id = current_agent_id()
        if not sender_id:
            return self._failure('no_caller', '这个工具只能由可信的 Agent 调用发起。')

        receiver_id = self.node.node_id
        if sender_id == receiver_id:
            return self._failure('self_talk', '你不能把这句话说给自己听。')

        sender_fields = self._profile(sender_id)
        if sender_fields is None:
            return self._failure('sender_profile_unavailable', '无法确认你的所在场所，没有发送。')
        sender_place = self._place(sender_fields)
        if sender_place is None:
            return self._failure('sender_not_present', '你当前不在任何场所，没有发送。')

        receiver_fields = self._profile(receiver_id)
        receiver_place = self._place(receiver_fields)
        if receiver_place is None or receiver_place != sender_place:
            return self._failure('receiver_not_present', GONE_MESSAGE)

        cost = self._action_cost()
        action_module = self._text_config('action_module', 'action.points')
        try:
            spent = self.backend.modules.call(sender_id, action_module, 'spend', {'amount': cost})
        except Exception:
            return self._failure('action_unavailable', '无法扣除行动值，没有发送。')
        if not isinstance(spent, dict) or not spent.get('ok'):
            detail = spent.get('message') if isinstance(spent, dict) else None
            return self._failure(
                'insufficient_action',
                detail if isinstance(detail, str) and detail else '行动值不足，没有发送。',
                remaining=spent.get('remaining') if isinstance(spent, dict) else None,
            )

        sender_name = self._name_from(sender_id, sender_fields)
        receiver_name = self._receiver_name(receiver_fields)
        message_id = uuid.uuid4().hex
        entry = {
            'id': message_id,
            'text': f'{sender_name}（{sender_id}）对你说：{text}',
        }
        try:
            self.node.inputs.update(self._source(), {'inputs': [entry]})
        except Exception:
            return self._failure(
                'delivery_failed',
                '话没有送进对方输入。',
                remaining=spent.get('remaining'),
                max=spent.get('max'),
            )

        remaining = spent.get('remaining')
        maximum = spent.get('max')
        if isinstance(remaining, int) and isinstance(maximum, int):
            summary = f'消息已发给{receiver_name}，剩余行动值 {remaining}/{maximum}。'
        elif isinstance(remaining, int):
            summary = f'消息已发给{receiver_name}，剩余行动值 {remaining}。'
        else:
            summary = f'消息已发给{receiver_name}。'
        return {
            'ok': True,
            'sent': True,
            'reason': None,
            'message': summary,
            'receiver': receiver_name,
            'receiver_id': receiver_id,
            'input_id': message_id,
            'remaining': remaining,
            'max': maximum,
        }

    # 以下只读依赖与配置，不写任何业务状态。

    def _profile(self, node_id):
        if not isinstance(node_id, str) or not node_id:
            return None
        module = self._text_config('profile_module', 'entity.profile')
        try:
            snapshot = self.backend.modules.call(node_id, module, 'read', {})
        except Exception:
            return None
        if not isinstance(snapshot, dict):
            return None
        fields = snapshot.get('profile')
        return fields if isinstance(fields, dict) else None

    def _place(self, fields):
        if not isinstance(fields, dict):
            return None
        value = fields.get(self._text_config('place_field', 'place'))
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _place_label(self, place):
        """把 profile.place 里的地点 ID 显示为节点名；节点不存在时保留原 ID。"""
        if not isinstance(place, str) or not place:
            return '未知地点'
        network = getattr(self.backend, 'network', None)
        nodes = getattr(network, 'nodes', None)
        if isinstance(nodes, dict):
            node = nodes.get(place)
            name = getattr(node, 'name', None) if node is not None else None
            if isinstance(name, str) and name.strip():
                return name.strip()
        return place

    def _action_cost(self):
        value = self.config.get('action_cost', 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 1
        return value

    def _text_config(self, key, default):
        value = self.config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    def _node(self, node_id):
        if node_id == self.node.node_id:
            return self.node
        network = getattr(self.backend, 'network', None)
        nodes = getattr(network, 'nodes', None)
        if isinstance(nodes, dict):
            return nodes.get(node_id)
        return None

    def _name_from(self, node_id, fields):
        if isinstance(fields, dict):
            value = fields.get('name')
            if isinstance(value, str) and value.strip():
                return value.strip()
        node = self._node(node_id)
        value = getattr(node, 'name', None) if node is not None else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return node_id

    def _receiver_name(self, fields=None):
        if fields is None:
            fields = self._profile(self.node.node_id)
        if isinstance(fields, dict):
            value = fields.get('name')
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = self.config.get('display_name')
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self._name_from(self.node.node_id, None)

    def _source(self):
        manifest = getattr(self, 'manifest', None)
        if isinstance(manifest, dict) and isinstance(manifest.get('id'), str) and manifest['id']:
            return manifest['id']
        return DEFAULT_SOURCE

    def _failure(self, reason, message, **extra):
        result = {'ok': False, 'sent': False, 'reason': reason, 'message': message}
        result.update(extra)
        return result
