"""Configuration-driven local action rules for one business address node.

The module exposes only ``act(action, quantity=1)``.  Every concrete business
(mining, wood cutting, repair, rest, shop trade, tavern spending, ...) is
described by the instance config, so this file contains no NPC, place or app
node identifiers.  Channel intersection and strength are handled by the core;
this module only checks the business preconditions it owns.
"""
from datanet.core.access_budget import current_agent_id
from datanet.studio.contract import StudioModule

_MISSING = object()
_EFFECT_KEYS = ('coins', 'items', 'fields')


def _plain(value):
    """Return a JSON-friendly copy (config may contain frozen tuples)."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class _Rejected(Exception):
    def __init__(self, reason, message, remaining=None):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.remaining = remaining


class Module(StudioModule):
    def setup(self):
        self._validate_config()

    # ------------------------------------------------------------------ config
    def _validate_config(self):
        config = self.config
        address = config.get('address')
        if not isinstance(address, str) or not address.strip():
            raise ValueError('config.address must be a non-empty node id')
        channels = config.get('channels')
        if not isinstance(channels, (list, tuple)) or not channels:
            raise ValueError('config.channels must be a non-empty list')
        for channel in channels:
            if not isinstance(channel, str) or not channel.strip():
                raise ValueError('config.channels must contain non-empty names')
        for key, default in (('entity_module', 'entity.profile'),
                             ('action_module', 'action.points')):
            value = config.get(key, default)
            if not isinstance(value, str) or not value.strip():
                raise ValueError('config.' + key + ' must be a non-empty module id')
        events_ref = config.get('events_ref')
        if events_ref is not None:
            if not isinstance(events_ref, dict):
                raise ValueError('config.events_ref must be an object')
            for key in ('node', 'module'):
                value = events_ref.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('config.events_ref.' + key + ' must be a non-empty string')
        rules = config.get('rules')
        if not isinstance(rules, dict) or not rules:
            raise ValueError('config.rules must be a non-empty object')
        for name, rule in rules.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError('Every rule name must be a non-empty string')
            if not isinstance(rule, dict):
                raise ValueError('Rule ' + name + ' must be an object')
            description = rule.get('description')
            if not isinstance(description, str) or not description.strip():
                raise ValueError('Rule ' + name + ' needs a non-empty description')
            cost = rule.get('cost')
            if type(cost) is not int or cost < 0:
                raise ValueError('Rule ' + name + ' cost must be an integer >= 0')
            cost_per_unit = rule.get('cost_per_unit', False)
            if type(cost_per_unit) is not bool:
                raise ValueError('Rule ' + name + ' cost_per_unit must be a boolean')
            for key in ('requires_items', 'requires_profile'):
                value = rule.get(key, {})
                if not isinstance(value, dict):
                    raise ValueError('Rule ' + name + ' ' + key + ' must be an object')
            for item_name, amount in rule.get('requires_items', {}).items():
                if not isinstance(item_name, str) or not item_name.strip():
                    raise ValueError('Rule ' + name + ' requires_items has an invalid item name')
                if type(amount) is not int or amount < 0:
                    raise ValueError('Rule ' + name + ' requires_items values must be integers >= 0')
            for key in ('actor', 'place'):
                effects = rule.get(key, {})
                if not isinstance(effects, dict):
                    raise ValueError('Rule ' + name + ' ' + key + ' must be an object')
                self._validate_effects(name, key, effects)
            trigger = rule.get('event_trigger')
            if trigger is not None and (not isinstance(trigger, str) or not trigger.strip()):
                raise ValueError('Rule ' + name + ' event_trigger must be a non-empty string')

    @staticmethod
    def _validate_effects(rule_name, group, effects):
        unknown = set(effects) - set(_EFFECT_KEYS)
        if unknown:
            raise ValueError('Rule ' + rule_name + ' ' + group + ' has unknown effect keys: ' +
                             ', '.join(sorted(unknown)))
        if 'coins' in effects and type(effects['coins']) is not int:
            raise ValueError('Rule ' + rule_name + ' ' + group + '.coins must be an integer')
        if 'items' in effects:
            items = effects['items']
            if not isinstance(items, dict):
                raise ValueError('Rule ' + rule_name + ' ' + group + '.items must be an object')
            for item_name, amount in items.items():
                if not isinstance(item_name, str) or not item_name.strip():
                    raise ValueError('Rule ' + rule_name + ' ' + group + '.items has an invalid item name')
                if type(amount) is not int:
                    raise ValueError('Rule ' + rule_name + ' ' + group + '.items values must be integers')
        if 'fields' in effects and not isinstance(effects['fields'], dict):
            raise ValueError('Rule ' + rule_name + ' ' + group + '.fields must be an object')

    # ------------------------------------------------------------ descriptions
    def tool_description(self, name, default):
        if name != 'act':
            return default
        rules = self.config.get('rules', {})
        if not rules:
            return default
        menu = []
        for action_name, rule in rules.items():
            if rule.get('cost_per_unit', False):
                detail = ['每单位消耗 ' + str(rule.get('cost', 0)) + ' 行动值']
            else:
                detail = ['每次调用消耗 ' + str(rule.get('cost', 0)) + ' 行动值']
            requires_items = rule.get('requires_items') or {}
            if requires_items:
                detail.append('每单位需要 ' + '、'.join(
                    item + '×' + str(amount) for item, amount in requires_items.items()))
            requires_profile = rule.get('requires_profile') or {}
            if requires_profile:
                detail.append('要求 ' + '、'.join(
                    field + '=' + str(expected) for field, expected in requires_profile.items()))
            menu.append(action_name + '：' + rule.get('description', '') + '（' +
                        '；'.join(detail) + '）')
        return ('在本地点执行配置好的本地行动，动作菜单：' + '；'.join(menu) +
                '。quantity 为 1 到 100 的整数：物品和金币按数量倍增，'
                '行动消耗按该动作标注的每次/每单位方式结算，资料字段原样写入。')

    # --------------------------------------------------------------------- act
    def act(self, action, quantity=1):
        balance = None
        normalized_quantity = quantity if type(quantity) is int else None
        normalized_action = action if isinstance(action, str) else None
        try:
            caller = current_agent_id()
            if caller is None:
                raise _Rejected('no_caller', '这个工具只能由可信的 Agent 调用发起。')
            balance = self._balance(caller)
            if type(quantity) is not int or not 1 <= quantity <= 100:
                raise _Rejected('invalid_quantity', 'quantity 必须是 1 到 100 的整数。',
                                remaining=balance)
            if not isinstance(action, str) or not action.strip():
                raise _Rejected('invalid_action', 'action 必须是非空的动作名。', remaining=balance)
            rules = self.config.get('rules', {})
            rule = rules.get(action)
            if rule is None:
                raise _Rejected('unknown_action',
                                '没有配置名为「' + action + '」的动作。可选动作：' +
                                '、'.join(rules) + '。', remaining=balance)

            address = self.config['address']
            self._check_presence(caller, address)

            actor = self._read_entity(caller, '你的资料')
            place = self._read_entity(address, '本地点库存')

            self._check_profile(rule, actor)
            self._check_required_items(rule, actor, quantity)

            actor_effects = self._effect_plan(
                actor, rule.get('actor') or {}, quantity, '你的')
            place_effects = self._effect_plan(
                place, rule.get('place') or {}, quantity, '本地点')

            cost = rule.get('cost', 0)
            if rule.get('cost_per_unit', False):
                cost = cost * quantity
            if balance is None:
                raise _Rejected('action_unavailable', '无法读取你的行动值，未执行。')
            if balance < cost:
                raise _Rejected('insufficient_action',
                                '行动值不足：需要 ' + str(cost) + '，剩余 ' + str(balance) + '。',
                                remaining=balance)

            event_node = None
            event_module = None
            events_ref = self.config.get('events_ref')
            if events_ref:
                event_node = events_ref['node']
                event_module = events_ref['module']

            entity_module = self.config.get('entity_module', 'entity.profile')
            action_module = self.config.get('action_module', 'action.points')
            trigger = rule.get('event_trigger') or action

            transaction_nodes = [caller, address]
            if event_node and event_node not in transaction_nodes:
                transaction_nodes.append(event_node)

            with self.backend.modules.transaction(*transaction_nodes):
                spend = self.backend.modules.call(
                    caller, action_module, 'spend', {'amount': cost})
                if not spend.get('ok'):
                    raise _Rejected('insufficient_action',
                                    spend.get('message', '行动值不足，未执行。'),
                                    remaining=spend.get('remaining'))
                remaining = spend.get('remaining')
                if type(remaining) is not int:
                    remaining = balance - cost

                self._adjust(caller, entity_module, actor_effects)
                self._adjust(address, entity_module, place_effects)

                events = []
                if event_node:
                    try:
                        drawn = self.backend.modules.call(
                            event_node, event_module, 'draw',
                            {'trigger': trigger,
                             'context': {'action': action,
                                         'quantity': quantity,
                                         'actor': caller,
                                         'address': address}})
                    except Exception as error:
                        raise _Rejected('event_unavailable',
                                        '成功后的概率事件无法抽取，行动已回滚：' + str(error),
                                        remaining=remaining)
                    events = _plain(drawn.get('events') or [])
                    preview = self._preview(actor, actor_effects)
                    event_effects = self._event_effects(events, preview)
                    if event_effects is not None:
                        try:
                            self._adjust(caller, entity_module, event_effects)
                        except Exception as error:
                            raise _Rejected('event_effect_failed',
                                            '事件效果无法结算，行动已回滚：' + str(error),
                                            remaining=remaining)

                actor_after = self._read_entity(caller, '你的资料')
                place_after = self._read_entity(address, '本地点库存')

            changes = {'actor': self._delta(actor, actor_after),
                       'place': self._delta(place, place_after)}
            message = ('「' + action + '」已完成 ×' + str(quantity) + '，消耗 ' +
                       str(cost) + ' 点行动值，剩余 ' + str(remaining) + ' 点。')
            event_messages = [str(event.get('message', '')) for event in events
                              if str(event.get('message', '')).strip()]
            if event_messages:
                message += ' ' + '；'.join(event_messages)
            return {
                'ok': True,
                'reason': None,
                'message': message,
                'remaining': remaining,
                'action': action,
                'quantity': quantity,
                'cost': cost,
                'events': events,
                'changes': changes,
            }
        except _Rejected as error:
            return self._failure(
                error.reason, error.message,
                error.remaining if error.remaining is not None else balance,
                normalized_action, normalized_quantity)
        except Exception as error:
            return self._failure('internal_error', '行动没有完成：' + str(error), balance,
                                 normalized_action, normalized_quantity)

    # ---------------------------------------------------------------- preconditions
    def _check_presence(self, caller, address):
        network = getattr(self.backend, 'network', None)
        nodes = getattr(network, 'nodes', {}) if network is not None else {}
        if address not in nodes or caller not in nodes:
            raise _Rejected('not_present',
                            '你或业务地址不在网络中，无法确认在场，未执行。')
        if caller == address:
            raise _Rejected('not_present',
                            '调用者不能是业务地址本身，未执行。')
        outgoing = self._edge_channels(caller, address)
        incoming = self._edge_channels(address, caller)
        configured = set(self.config.get('channels', ()))
        if not (outgoing & incoming & configured):
            raise _Rejected(
                'not_present',
                '你并不真正在「' + address + '」：需要与该地址具备双向在场连接，'
                '且两个方向的连接共用同一个行动频道（' +
                '、'.join(self.config.get('channels', ())) + '）。')

    def _edge_channels(self, source_id, target_id):
        network = getattr(self.backend, 'network', None)
        nodes = getattr(network, 'nodes', {}) if network is not None else {}
        source = nodes.get(source_id)
        channels = set()
        for edge in getattr(source, 'interfaces', ()) or ():
            if edge.target_node_id == target_id:
                channels.update(getattr(edge.metadata, 'channels', ()) or ())
        return channels

    def _check_profile(self, rule, actor):
        profile = actor.get('profile') or {}
        for field, expected in (rule.get('requires_profile') or {}).items():
            if profile.get(field, _MISSING) != expected:
                shown = profile.get(field, '未设置')
                raise _Rejected(
                    'profile_requirement',
                    '不满足动作前提：资料字段「' + field + '」需要为 ' +
                    str(expected) + '，当前为 ' + str(shown) + '。')

    @staticmethod
    def _check_required_items(rule, actor, quantity):
        items = actor.get('items') or {}
        for item_name, per_unit in (rule.get('requires_items') or {}).items():
            needed = per_unit * quantity
            held = items.get(item_name, 0)
            if held < needed:
                raise _Rejected(
                    'insufficient_items',
                    '物品不足：每单位需要「' + item_name + '」×' + str(per_unit) +
                    '，本次共需 ' + str(needed) + '，当前持有 ' + str(held) + '。')

    # ------------------------------------------------------------------ effects
    def _effect_plan(self, snapshot, effects, multiplier, label):
        effects = effects or {}
        coins = effects.get('coins', 0)
        if type(coins) is not int:
            raise _Rejected('invalid_effect', label + '金币增量必须是整数。')
        items = effects.get('items') or {}
        fields = effects.get('fields') or {}
        scaled_items = {}
        for item_name, amount in items.items():
            if type(amount) is not int:
                raise _Rejected('invalid_effect', label + '物品增量必须是整数。')
            scaled_items[item_name] = amount * multiplier
        scaled_coins = coins * multiplier
        current_coins = snapshot.get('coins', 0)
        if current_coins + scaled_coins < 0:
            raise _Rejected(
                'insufficient_coins',
                '金币不足：需要 ' + str(-scaled_coins) + '，当前 ' + str(current_coins) + '。')
        current_items = snapshot.get('items') or {}
        for item_name, delta in scaled_items.items():
            held = current_items.get(item_name, 0)
            if held + delta < 0:
                raise _Rejected(
                    'insufficient_items',
                    '物品不足：需要「' + item_name + '」×' + str(-delta) +
                    '，当前 ' + str(held) + '。')
        return {'coins': scaled_coins,
                'items': scaled_items,
                'fields': _plain(fields)}

    def _event_effects(self, events, snapshot):
        coins = 0
        items = {}
        fields = {}
        for event in events:
            effects = event.get('effects') if isinstance(event, dict) else None
            if not isinstance(effects, dict):
                continue
            has_resource = any(key in effects for key in _EFFECT_KEYS)
            if not has_resource:
                continue
            event_id = event.get('id', '未命名事件')
            event_coins = effects.get('coins', 0)
            if type(event_coins) is not int:
                raise _Rejected('invalid_event_effect',
                                '事件「' + str(event_id) + '」的 coins 必须是整数。')
            event_items = effects.get('items') or {}
            if not isinstance(event_items, dict):
                raise _Rejected('invalid_event_effect',
                                '事件「' + str(event_id) + '」的 items 必须是对象。')
            event_fields = effects.get('fields') or {}
            if not isinstance(event_fields, dict):
                raise _Rejected('invalid_event_effect',
                                '事件「' + str(event_id) + '」的 fields 必须是对象。')
            coins += event_coins
            for item_name, amount in event_items.items():
                if type(amount) is not int:
                    raise _Rejected('invalid_event_effect',
                                    '事件「' + str(event_id) + '」的物品增量必须是整数。')
                items[item_name] = items.get(item_name, 0) + amount
            fields.update(event_fields)
        raw = {'coins': coins, 'items': items, 'fields': fields}
        if not any(raw[key] for key in _EFFECT_KEYS):
            return None
        return self._effect_plan(snapshot, raw, 1, '事件奖励')

    def _adjust(self, node_id, entity_module, plan):
        arguments = {}
        if plan.get('coins'):
            arguments['coins'] = plan['coins']
        if plan.get('items'):
            arguments['items'] = dict(plan['items'])
        if plan.get('fields'):
            arguments['fields'] = _plain(plan['fields'])
        if not arguments:
            return
        self.backend.modules.call(node_id, entity_module, 'adjust', arguments)

    @staticmethod
    def _preview(snapshot, plan):
        result = {
            'profile': _plain(snapshot.get('profile') or {}),
            'coins': snapshot.get('coins', 0) + plan.get('coins', 0),
            'items': dict(snapshot.get('items') or {}),
        }
        for item_name, delta in (plan.get('items') or {}).items():
            result['items'][item_name] = result['items'].get(item_name, 0) + delta
        result['profile'].update(_plain(plan.get('fields') or {}))
        return result

    @staticmethod
    def _delta(before, after):
        before_items = before.get('items') or {}
        after_items = after.get('items') or {}
        item_delta = {}
        for item_name in set(before_items) | set(after_items):
            difference = after_items.get(item_name, 0) - before_items.get(item_name, 0)
            if difference:
                item_delta[item_name] = difference
        before_profile = before.get('profile') or {}
        after_profile = after.get('profile') or {}
        field_delta = {}
        for field in set(before_profile) | set(after_profile):
            if before_profile.get(field, _MISSING) != after_profile.get(field, _MISSING):
                field_delta[field] = _plain(after_profile.get(field))
        return {'coins': after.get('coins', 0) - before.get('coins', 0),
                'items': item_delta,
                'fields': field_delta}

    # ---------------------------------------------------------------- dependencies
    def _read_entity(self, node_id, label):
        module = self.config.get('entity_module', 'entity.profile')
        try:
            snapshot = self.backend.modules.call(node_id, module, 'read', {})
        except Exception as error:
            raise _Rejected('entity_unavailable',
                            '无法读取' + label + '，未执行：' + str(error))
        if not isinstance(snapshot, dict):
            raise _Rejected('entity_unavailable', '无法读取' + label + '，未执行。')
        return snapshot

    def _balance(self, node_id):
        module = self.config.get('action_module', 'action.points')
        try:
            result = self.backend.modules.call(node_id, module, 'get_balance', {})
        except Exception:
            return None
        remaining = result.get('remaining') if isinstance(result, dict) else None
        return remaining if type(remaining) is int else None

    @staticmethod
    def _failure(reason, message, remaining, action, quantity):
        return {
            'ok': False,
            'reason': reason,
            'message': message,
            'remaining': remaining if type(remaining) is int else None,
            'action': action,
            'quantity': quantity,
            'events': [],
            'changes': {},
        }
