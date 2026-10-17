"""通用同场赠送：每个 Agent 挂一个可被同场者远程调用的 give 端点。

本实例始终代表“收礼者”——它所在节点就是礼物接收方。送出资源的人由
datanet.core.access_budget.current_agent_id() 取得，绝不作为工具参数暴露。
双方必须在同一场所，并且各自与那个场所节点之间存在真实的双向在场连接。
"""
from datanet.core.access_budget import current_agent_id
from datanet.studio.contract import StudioModule

DEFAULT_ENTITY_MODULE = 'entity.profile'
DEFAULT_ACTION_MODULE = 'action.points'
DEFAULT_PRESENCE_CHANNEL = 'presence'


class Module(StudioModule):
    """收礼者 Agent 上的同场赠送端点。"""

    # ------------------------------------------------------------------ 工具描述
    def tool_description(self, name, default):
        if name != 'give':
            return default
        who = self._receiver_name()
        cost = self._action_cost()
        if cost > 0:
            cost_text = f'成功会消耗你 {cost} 点行动值，失败不会扣除。'
        else:
            cost_text = '本实例不消耗行动值。'
        return (
            f'把你自己拥有的金币或物品送给{who}。只有和{who}在同一场所、'
            f'且双方都真实在场时才能送；coins 与 items 至少填一项，数量必须是正整数。'
            f'{cost_text}'
        )

    # ------------------------------------------------------------------ 工具
    def give(self, coins=None, items=None):
        """把调用者自己的金币/物品转给本节点这位收礼者。"""
        coin_amount, item_amounts, problem = self._normalise_gift(coins, items)
        if problem is not None:
            return problem

        sender_id = current_agent_id()
        if not sender_id:
            return self._failure('no_caller', '这个工具只能由可信的 Agent 调用发起，未赠送。')

        receiver_id = self.node.node_id
        if sender_id == receiver_id:
            return self._failure('self_gift', '你不能把东西送给自己，未赠送。')

        sender_profile = self._profile(sender_id)
        if sender_profile is None:
            return self._failure('sender_profile_unavailable', '无法确认你的资料，未赠送。')
        sender_place = self._place(sender_profile)
        if sender_place is None:
            return self._failure('sender_not_present', '你当前不在任何场所，未赠送。')

        receiver_profile = self._profile(receiver_id)
        if receiver_profile is None:
            return self._failure(
                'receiver_profile_unavailable',
                f'无法确认{self._receiver_name()}的资料，未赠送。',
            )
        receiver_name = self._name_from(receiver_id, receiver_profile)
        receiver_place = self._place(receiver_profile)
        if receiver_place is None or receiver_place != sender_place:
            return self._failure(
                'not_same_place',
                f'{receiver_name}不在你所在的场所，未赠送。',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )

        nodes = getattr(getattr(self.backend, 'network', None), 'nodes', None)
        if not isinstance(nodes, dict):
            return self._failure('network_unavailable', '无法确认现场连接，未赠送。')
        place = nodes.get(sender_place)
        if place is None:
            return self._failure(
                'place_unavailable',
                '你们记录的场所不在网络里，未赠送。',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )
        sender_node = nodes.get(sender_id)
        if sender_node is None:
            return self._failure('sender_not_present', '找不到你的人物节点，未赠送。')

        if not self._really_present(
            sender_node, self.node, place
        ):
            if not self._place_presence(sender_node, place):
                return self._failure(
                    'sender_not_really_present',
                    '你与这个场所没有真实的双向在场连接，未赠送。',
                    receiver=receiver_name,
                    receiver_id=receiver_id,
                )
            return self._failure(
                'receiver_not_really_present',
                f'{receiver_name}与这个场所没有真实的双向在场连接，未赠送。',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )

        sender_snapshot = self._entity_snapshot(sender_id)
        if sender_snapshot is None:
            return self._failure('entity_unavailable', '无法读取你的金币与物品，未赠送。')
        problem = self._check_resources(
            sender_snapshot, coin_amount, item_amounts, receiver_name, receiver_id
        )
        if problem is not None:
            return problem

        return self._transfer(
            sender_id,
            receiver_id,
            receiver_name,
            coin_amount,
            item_amounts,
        )

    # ------------------------------------------------------------------ 参数校验
    def _normalise_gift(self, coins, items):
        coin_amount = 0
        if coins is not None:
            if type(coins) is not int or coins <= 0:
                return None, None, self._failure(
                    'invalid_coins', '金币数量必须是正整数，未赠送。'
                )
            coin_amount = coins

        item_amounts = {}
        if items is not None:
            if not isinstance(items, dict) or not items:
                return None, None, self._failure(
                    'invalid_items', '物品必须写成物品名到正整数数量的对象，未赠送。'
                )
            for raw_name, quantity in items.items():
                if not isinstance(raw_name, str) or not raw_name.strip():
                    return None, None, self._failure(
                        'invalid_items', '物品名必须是非空字符串，未赠送。'
                    )
                if type(quantity) is not int or quantity <= 0:
                    return None, None, self._failure(
                        'invalid_items', '每种物品的数量必须是正整数，未赠送。'
                    )
                item_amounts[raw_name.strip()] = (
                    item_amounts.get(raw_name.strip(), 0) + quantity
                )

        if coin_amount <= 0 and not item_amounts:
            return None, None, self._failure(
                'empty_gift', '至少要送出金币或物品中的一种，且数量必须为正，未赠送。'
            )
        return coin_amount, item_amounts, None

    def _check_resources(self, snapshot, coin_amount, item_amounts, receiver_name, receiver_id):
        coins = snapshot.get('coins', 0)
        if not isinstance(coins, int) or isinstance(coins, bool) or coins < 0:
            return self._failure(
                'entity_invalid', '你的金币记录异常，未赠送。',
                receiver=receiver_name, receiver_id=receiver_id,
            )
        if coin_amount > coins:
            return self._failure(
                'insufficient_coins',
                f'你的金币不足：要送 {coin_amount}，只有 {coins}，未赠送。',
                receiver=receiver_name, receiver_id=receiver_id,
            )

        sender_items = snapshot.get('items')
        if not isinstance(sender_items, dict):
            sender_items = {}
        for name, quantity in item_amounts.items():
            owned = sender_items.get(name, 0)
            if not isinstance(owned, int) or isinstance(owned, bool) or owned < quantity:
                owned_text = owned if isinstance(owned, int) else 0
                return self._failure(
                    'insufficient_items',
                    f'你的「{name}」不足：要送 {quantity}，只有 {owned_text}，未赠送。',
                    receiver=receiver_name, receiver_id=receiver_id,
                )
        return None

    # ------------------------------------------------------------------ 短事务转移
    def _transfer(self, sender_id, receiver_id, receiver_name, coin_amount, item_amounts):
        entity_module = self._config_text('entity_module', DEFAULT_ENTITY_MODULE)
        action_module = self._config_text('action_module', DEFAULT_ACTION_MODULE)
        cost = self._action_cost()

        negative = self._adjust_arguments(coin_amount, item_amounts, sign=-1)
        positive = self._adjust_arguments(coin_amount, item_amounts, sign=1)

        spent = None
        try:
            with self.backend.modules.transaction(sender_id, receiver_id):
                spent = self.backend.modules.call(
                    sender_id, action_module, 'spend', {'amount': cost}
                )
                if not isinstance(spent, dict) or not spent.get('ok'):
                    detail = spent.get('message') if isinstance(spent, dict) else None
                    return self._failure(
                        'insufficient_action',
                        detail if isinstance(detail, str) and detail else '行动值不足，未赠送。',
                        remaining=spent.get('remaining') if isinstance(spent, dict) else None,
                        receiver=receiver_name,
                        receiver_id=receiver_id,
                    )
                self.backend.modules.call(
                    sender_id, entity_module, 'adjust', negative
                )
                self.backend.modules.call(
                    receiver_id, entity_module, 'adjust', positive
                )
        except (KeyError, PermissionError):
            return self._failure(
                'dependency_unavailable',
                '实体资料或行动值组件不可用，本次赠送已取消。',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )
        except (ValueError, TypeError) as error:
            return self._failure(
                'transfer_failed',
                f'资源转移未完成，已取消：{error}',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )
        except Exception as error:
            return self._failure(
                'transfer_failed',
                f'资源转移未完成，已取消：{error}',
                receiver=receiver_name,
                receiver_id=receiver_id,
            )

        remaining = spent.get('remaining')
        maximum = spent.get('max')
        message = self._success_message(
            receiver_name, coin_amount, item_amounts, cost, remaining, maximum
        )
        return {
            'ok': True,
            'given': True,
            'reason': None,
            'message': message,
            'receiver': receiver_name,
            'receiver_id': receiver_id,
            'coins': coin_amount,
            'items': dict(item_amounts),
            'cost': cost,
            'remaining': remaining,
            'max': maximum,
        }

    @staticmethod
    def _adjust_arguments(coin_amount, item_amounts, sign):
        arguments = {}
        if coin_amount:
            arguments['coins'] = coin_amount * sign
        if item_amounts:
            arguments['items'] = {
                name: quantity * sign for name, quantity in item_amounts.items()
            }
        return arguments

    @staticmethod
    def _success_message(receiver_name, coin_amount, item_amounts, cost, remaining, maximum):
        parts = []
        if coin_amount:
            parts.append(f'{coin_amount} 金币')
        if item_amounts:
            parts.append('、'.join(f'{name}×{quantity}' for name, quantity in item_amounts.items()))
        gift_text = ' 和 '.join(parts)
        if isinstance(remaining, int) and isinstance(maximum, int):
            remaining_text = f'剩余行动值 {remaining}/{maximum}'
        elif isinstance(remaining, int):
            remaining_text = f'剩余行动值 {remaining}'
        else:
            remaining_text = '剩余行动值未知'
        if cost > 0:
            cost_text = f'消耗 {cost} 点行动值，'
        else:
            cost_text = '未消耗行动值，'
        return f'你已把 {gift_text} 送给{receiver_name}，{cost_text}{remaining_text}。'

    # ------------------------------------------------------------------ 现场与资料
    def _really_present(self, sender, receiver, place):
        """判断双方是否真实双向在场。

        优先看双方是否各自与共同场所节点有双向在场连接（与 place.move 建立的
        连接一致）；如果应用没有使用场所节点在场连接，则要求发送者与收礼者
        在配置的赠送频道上双向直达。两种拓扑满足其一即视为真实双向在场。
        """
        if self._place_presence(sender, place) and self._place_presence(receiver, place):
            return True
        return self._direct_presence(sender, receiver)

    def _place_presence(self, agent, place):
        """人物与场所之间必须有双向的 presence 连接。"""
        channel = self._presence_channel()
        return (
            channel in self._channels_towards(agent, place.node_id)
            and channel in self._channels_towards(place, agent.node_id)
        )

    def _direct_presence(self, sender, receiver):
        """双方在配置的赠送频道上互相直达，作为在场连接的后备证据。"""
        channels = set(self._tool_channels())
        if not channels:
            return False
        return (
            bool(channels.intersection(self._channels_towards(sender, receiver.node_id)))
            and bool(channels.intersection(self._channels_towards(receiver, sender.node_id)))
        )

    def _tool_channels(self):
        value = self.config.get('channels')
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(item for item in value if isinstance(item, str) and item)

    @staticmethod
    def _channels_towards(node, target_id):
        channels = set()
        for edge in getattr(node, 'interfaces', ()) or ():
            if getattr(edge, 'target_node_id', None) != target_id:
                continue
            metadata = getattr(edge, 'metadata', None)
            values = getattr(metadata, 'channels', ()) or ()
            channels.update(values)
        return channels

    def _profile(self, node_id):
        module = self._config_text('entity_module', DEFAULT_ENTITY_MODULE)
        try:
            snapshot = self.backend.modules.call(node_id, module, 'read', {})
        except Exception:
            return None
        if not isinstance(snapshot, dict):
            return None
        fields = snapshot.get('profile')
        return fields if isinstance(fields, dict) else None

    def _entity_snapshot(self, node_id):
        module = self._config_text('entity_module', DEFAULT_ENTITY_MODULE)
        try:
            snapshot = self.backend.modules.call(node_id, module, 'read', {})
        except Exception:
            return None
        return snapshot if isinstance(snapshot, dict) else None

    def _place(self, fields):
        if not isinstance(fields, dict):
            return None
        value = fields.get(self._config_text('place_field', 'place'))
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

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

    def _name_from(self, node_id, fields):
        if isinstance(fields, dict):
            value = fields.get('name')
            if isinstance(value, str) and value.strip():
                return value.strip()
        nodes = getattr(getattr(self.backend, 'network', None), 'nodes', None)
        node = nodes.get(node_id) if isinstance(nodes, dict) else None
        value = getattr(node, 'name', None) if node is not None else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return node_id

    # ------------------------------------------------------------------ 配置读取
    def _action_cost(self):
        value = self.config.get('action_cost', 1)
        if type(value) is not int or value < 0:
            return 1
        return value

    def _presence_channel(self):
        return self._config_text('presence_channel', DEFAULT_PRESENCE_CHANNEL)

    def _config_text(self, key, default):
        value = self.config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    # ------------------------------------------------------------------ 结果
    def _failure(self, reason, message, **extra):
        result = {'ok': False, 'given': False, 'reason': reason, 'message': message}
        result.update(extra)
        return result
