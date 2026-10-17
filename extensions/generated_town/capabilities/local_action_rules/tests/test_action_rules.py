"""Business tests for local.action_rules (unittest, fake dependencies)."""
import importlib.util
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from datanet.core.access_budget import active_agent
from datanet.core.node import Node

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'local_action_rules_module_under_test', ROOT / 'module.py'
)
MODULE_FILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE_FILE)
Module = MODULE_FILE.Module
MANIFEST = json.loads((ROOT / 'module.json').read_text(encoding='utf-8'))


@contextmanager
def acting_as(node_id):
    token = active_agent.set((SimpleNamespace(max_signal_strength=3), node_id))
    try:
        yield
    finally:
        active_agent.reset(token)


class FakeModules:
    def __init__(self, entities, balances, event_specs=None):
        self.entities = entities
        self.balances = balances
        self.event_specs = list(event_specs or [])
        self.event_counts = {}
        self.calls = []

    def call(self, node_id, module, operation, arguments=None):
        arguments = {} if arguments is None else dict(arguments)
        self.calls.append((node_id, module, operation, deepcopy(arguments)))
        if module == 'entity.profile' and operation == 'read':
            if node_id not in self.entities:
                raise KeyError(node_id)
            return deepcopy(self.entities[node_id])
        if module == 'entity.profile' and operation == 'adjust':
            if node_id not in self.entities:
                raise KeyError(node_id)
            current = deepcopy(self.entities[node_id])
            coins = current['coins'] + arguments.get('coins', 0)
            items = dict(current['items'])
            for name, delta in arguments.get('items', {}).items():
                items[name] = items.get(name, 0) + delta
            if coins < 0:
                raise ValueError('金币不能为负')
            if any(amount < 0 for amount in items.values()):
                raise ValueError('物品不能为负')
            current['coins'] = coins
            current['items'] = {name: amount for name, amount in items.items() if amount > 0}
            current['profile'].update(deepcopy(arguments.get('fields', {})))
            self.entities[node_id] = current
            return deepcopy(current)
        if module == 'action.points' and operation == 'get_balance':
            return {'ok': True, 'remaining': self.balances.get(node_id, 0),
                    'max': 10, 'message': '余额'}
        if module == 'action.points' and operation == 'spend':
            amount = arguments['amount']
            remaining = self.balances.get(node_id, 0)
            if amount > remaining:
                return {'ok': False, 'reason': 'insufficient', 'amount': amount,
                        'spent': 0, 'remaining': remaining, 'max': 10,
                        'message': '行动值不足：需要 %d，剩余 %d/10，未扣除。' % (amount, remaining)}
            self.balances[node_id] = remaining - amount
            return {'ok': True, 'amount': amount, 'spent': amount,
                    'remaining': remaining - amount, 'max': 10,
                    'message': '扣除 %d 行动值。' % amount}
        if module == 'chance.events' and operation == 'draw':
            trigger = arguments['trigger']
            hits = []
            for event in self.event_specs:
                if trigger not in event['triggers']:
                    continue
                count = self.event_counts.get(event['id'], 0)
                max_hits = event.get('max_hits')
                if max_hits is not None and count >= max_hits:
                    continue
                probability = event.get('probability', 1)
                if probability <= 0:
                    continue
                self.event_counts[event['id']] = count + 1
                hits.append({'id': event['id'], 'message': event.get('message', ''),
                             'effects': deepcopy(event.get('effects'))})
            return {'events': hits}
        raise KeyError((node_id, module, operation))

    @contextmanager
    def transaction(self, *node_ids):
        entities = deepcopy(self.entities)
        balances = deepcopy(self.balances)
        counts = deepcopy(self.event_counts)
        try:
            yield
        except BaseException:
            self.entities = entities
            self.balances = balances
            self.event_counts = counts
            raise


class FakeBackend:
    def __init__(self, modules, nodes):
        self.modules = modules
        self.network = SimpleNamespace(nodes=nodes)


DEFAULT_RULE = {
    'description': '在矿脉挖掘铁矿石',
    'cost': 1,
    'requires_items': {'镐': 1},
    'requires_profile': {'adult': True},
    'actor': {'items': {'铁矿石': 2}},
    'place': {'items': {'矿脉': -1}},
}


class ActionRuleTests(unittest.TestCase):
    def make(self, *, rules=None, actor_profile=None, actor_items=None,
             actor_coins=10, place_items=None, balance=10,
             connect=True, reverse=True, reverse_channel='act.local',
             event_specs=None, events_ref=None):
        actor_node = Node('agent/alan', '阿岚', None)
        address_id = 'place/market'
        address_node = Node(address_id, '集市', None)
        nodes = {actor_node.node_id: actor_node, address_id: address_node}
        if connect:
            actor_node.connect(address_id, channels=['act.local'], threshold=1)
        if reverse:
            address_node.connect(actor_node.node_id, channels=[reverse_channel], threshold=1)
        entities = {
            actor_node.node_id: {
                'profile': {'name': '阿岚', 'adult': True, 'home': 'place/home'}
                if actor_profile is None else dict(actor_profile),
                'coins': actor_coins,
                'items': {'镐': 5} if actor_items is None else dict(actor_items),
            },
            address_id: {
                'profile': {'name': '集市'},
                'coins': 0,
                'items': {'矿脉': 10} if place_items is None else dict(place_items),
            },
        }
        balances = {actor_node.node_id: balance}
        modules = FakeModules(entities, balances, event_specs)
        backend = FakeBackend(modules, nodes)
        config = {'address': address_id,
                  'channels': ['act.local'],
                  'rules': deepcopy(rules or {'mine': DEFAULT_RULE})}
        if events_ref is not None:
            config['events_ref'] = events_ref
        module = Module(backend, address_node, config, {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        return module, backend, actor_node, address_node

    def assert_no_state_change(self, backend, actor_node, address_node):
        self.assertEqual(backend.modules.entities[actor_node.node_id], {
            'profile': {'name': '阿岚', 'adult': True, 'home': 'place/home'},
            'coins': 10,
            'items': {'镐': 5},
        })
        self.assertEqual(backend.modules.entities[address_node.node_id]['items'], {'矿脉': 10})

    def test_act_multiplies_items_and_charges_cost_once(self):
        module, backend, actor, address = self.make()
        with acting_as(actor.node_id):
            result = module.act('mine', 2)
        self.assertTrue(result['ok'])
        self.assertEqual(result['remaining'], 9)
        self.assertEqual(result['cost'], 1)
        self.assertEqual(result['changes']['actor']['items'], {'铁矿石': 4})
        self.assertEqual(result['changes']['place']['items'], {'矿脉': -2})
        self.assertEqual(backend.modules.entities[actor.node_id]['items']['铁矿石'], 4)
        self.assertEqual(backend.modules.entities[address.node_id]['items']['矿脉'], 8)
        self.assertEqual(backend.modules.balances[actor.node_id], 9)

    def test_requires_items_is_per_unit(self):
        module, backend, actor, address = self.make(actor_items={'镐': 1})
        with acting_as(actor.node_id):
            result = module.act('mine', 2)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_items')
        self.assertEqual(result['remaining'], 10)
        self.assertIn('镐', result['message'])
        self.assertEqual(backend.modules.entities[actor.node_id]['items'], {'镐': 1})

    def test_insufficient_coins_rejected_without_change(self):
        rules = {'buy': {'description': '买面包', 'cost': 1,
                         'actor': {'coins': -5}, 'place': {}}}
        module, backend, actor, address = self.make(rules=rules, actor_coins=3)
        with acting_as(actor.node_id):
            result = module.act('buy')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_coins')
        self.assertEqual(result['remaining'], 10)
        self.assertEqual(backend.modules.entities[actor.node_id]['coins'], 3)
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

    def test_insufficient_place_stock_rolls_back_action(self):
        module, backend, actor, address = self.make(place_items={'矿脉': 1})
        with acting_as(actor.node_id):
            result = module.act('mine', 2)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_items')
        self.assertEqual(backend.modules.entities[actor.node_id]['items'], {'镐': 5})
        self.assertEqual(backend.modules.entities[address.node_id]['items'], {'矿脉': 1})
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

    def test_insufficient_action_points_rejected(self):
        module, backend, actor, address = self.make(balance=0)
        with acting_as(actor.node_id):
            result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_action')
        self.assertEqual(result['remaining'], 0)
        self.assertEqual(backend.modules.entities[actor.node_id]['items'], {'镐': 5})
        self.assertEqual(backend.modules.entities[address.node_id]['items'], {'矿脉': 10})

    def test_cost_per_unit_uses_actual_cost_for_check_spend_and_return(self):
        rules = {'mine': {'description': '按件计酬挖矿', 'cost': 6,
                          'cost_per_unit': True,
                          'actor': {'items': {'铁矿石': 2}},
                          'place': {'items': {'矿脉': -1}}}}
        module, backend, actor, address = self.make(rules=rules, balance=10)
        before_actor = deepcopy(backend.modules.entities[actor.node_id])
        with acting_as(actor.node_id):
            rejected = module.act('mine', 2)
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'insufficient_action')
        self.assertEqual(rejected['remaining'], 10)
        self.assertIn('12', rejected['message'])
        self.assertEqual(backend.modules.entities[actor.node_id], before_actor)
        self.assertEqual(backend.modules.entities[address.node_id]['items'], {'矿脉': 10})
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

        with acting_as(actor.node_id):
            accepted = module.act('mine', 1)
        self.assertTrue(accepted['ok'])
        self.assertEqual(accepted['cost'], 6)
        self.assertEqual(accepted['remaining'], 4)
        self.assertEqual(backend.modules.balances[actor.node_id], 4)
        self.assertEqual(backend.modules.entities[actor.node_id]['items']['铁矿石'], 2)

    def test_default_cost_charges_once_for_trade_quantity(self):
        rules = {'trade': {'description': '整单交易', 'cost': 1,
                           'actor': {'items': {'面包': 1}}, 'place': {}}}
        module, backend, actor, address = self.make(rules=rules, balance=10)
        with acting_as(actor.node_id):
            result = module.act('trade', 3)
        self.assertTrue(result['ok'])
        self.assertEqual(result['quantity'], 3)
        self.assertEqual(result['cost'], 1)
        self.assertEqual(result['remaining'], 9)
        self.assertEqual(backend.modules.balances[actor.node_id], 9)
        self.assertEqual(backend.modules.entities[actor.node_id]['items']['面包'], 3)

    def test_negative_zero_and_oversized_quantity_rejected(self):
        module, backend, actor, address = self.make()
        for quantity in (-1, 0, 101, 1.5):
            with acting_as(actor.node_id):
                result = module.act('mine', quantity)
            self.assertFalse(result['ok'], quantity)
            self.assertEqual(result['reason'], 'invalid_quantity')
            self.assertEqual(result['remaining'], 10)
        self.assertEqual(backend.modules.entities[actor.node_id]['items'], {'镐': 5})
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

    def test_cross_location_and_one_way_connection_rejected(self):
        module, backend, actor, address = self.make(connect=False, reverse=False)
        with acting_as(actor.node_id):
            result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'not_present')

        module, backend, actor, address = self.make(reverse=False)
        with acting_as(actor.node_id):
            result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'not_present')

        module, backend, actor, address = self.make(reverse_channel='other.channel')
        with acting_as(actor.node_id):
            result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'not_present')
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

    def test_only_own_home_profile_equality(self):
        rules = {'rest': {'description': '在自己家休息', 'cost': 1,
                          'requires_profile': {'home': 'place/home'},
                          'actor': {'fields': {'energy': 'rested'}}, 'place': {}}}
        module, backend, actor, address = self.make(
            rules=rules, actor_profile={'name': '阿岚', 'adult': True,
                                        'home': 'place/other'})
        with acting_as(actor.node_id):
            result = module.act('rest')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'profile_requirement')
        self.assertIn('home', result['message'])
        self.assertEqual(backend.modules.balances[actor.node_id], 10)

        backend.modules.entities[actor.node_id]['profile']['home'] = 'place/home'
        with acting_as(actor.node_id):
            result = module.act('rest', 3)
        self.assertTrue(result['ok'])
        self.assertEqual(backend.modules.entities[actor.node_id]['profile']['energy'], 'rested')
        self.assertEqual(result['changes']['actor']['fields'], {'energy': 'rested'})

    def test_unknown_action_lists_menu(self):
        module, backend, actor, address = self.make()
        with acting_as(actor.node_id):
            result = module.act('fly')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'unknown_action')
        self.assertIn('mine', result['message'])

    def test_no_caller_rejected(self):
        module, backend, actor, address = self.make()
        result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'no_caller')
        self.assertEqual(result['changes'], {})

    def test_tool_description_and_channels(self):
        module, backend, actor, address = self.make()
        definition = address.tool_definitions['act']
        self.assertEqual(definition['access_channels'], ['act.local'])
        self.assertIn('mine', definition['description'])
        self.assertIn('在矿脉挖掘铁矿石', definition['description'])
        self.assertIn('消耗 1 行动值', definition['description'])
        self.assertIn('镐', definition['description'])
        self.assertIn('adult', definition['description'])

    def test_event_effects_apply_to_actor_and_message_returned(self):
        rules = {'tavern': {'description': '喝酒', 'cost': 1,
                            'actor': {'coins': -3}, 'place': {'coins': 3},
                            'event_trigger': 'tavern'}}
        event_specs = [{'id': 'rumor', 'triggers': ['tavern'],
                        'message': '你听到一个传闻。',
                        'effects': {'coins': 2, 'items': {'旧硬币': 1},
                                    'fields': {'heard': 'rumor'}}}]
        module, backend, actor, address = self.make(
            rules=rules, actor_coins=10, event_specs=event_specs,
            events_ref={'node': 'place/tavern', 'module': 'chance.events'})
        backend.network.nodes['place/tavern'] = Node('place/tavern', '酒馆', None)
        with acting_as(actor.node_id):
            result = module.act('tavern')
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['events']), 1)
        self.assertIn('你听到一个传闻。', result['message'])
        self.assertEqual(backend.modules.entities[actor.node_id]['coins'], 9)
        self.assertEqual(backend.modules.entities[actor.node_id]['items']['旧硬币'], 1)
        self.assertEqual(backend.modules.entities[actor.node_id]['profile']['heard'], 'rumor')
        self.assertEqual(backend.modules.balances[actor.node_id], 9)
        self.assertEqual(backend.modules.event_counts, {'rumor': 1})

    def test_event_effect_failure_rolls_back_action_and_counts(self):
        rules = {'mine': DEFAULT_RULE}
        event_specs = [{'id': 'bad', 'triggers': ['mine'], 'message': '坏事',
                        'effects': {'items': {'不存在': -1}}}]
        module, backend, actor, address = self.make(
            event_specs=event_specs,
            events_ref={'node': 'place/tavern', 'module': 'chance.events'})
        backend.network.nodes['place/tavern'] = Node('place/tavern', '酒馆', None)
        with acting_as(actor.node_id):
            result = module.act('mine')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_items')
        self.assertEqual(backend.modules.entities[actor.node_id]['items'], {'镐': 5})
        self.assertEqual(backend.modules.entities[address.node_id]['items'], {'矿脉': 10})
        self.assertEqual(backend.modules.balances[actor.node_id], 10)
        self.assertEqual(backend.modules.event_counts, {})

    def test_pure_rumor_event_has_no_resource_change(self):
        rules = {'rest': {'description': '休息', 'cost': 0,
                          'actor': {}, 'place': {}, 'event_trigger': 'rest'}}
        event_specs = [{'id': 'gossip', 'triggers': ['rest'],
                        'message': '远处有人说话。'}]
        module, backend, actor, address = self.make(
            rules=rules, event_specs=event_specs,
            events_ref={'node': 'place/tavern', 'module': 'chance.events'})
        backend.network.nodes['place/tavern'] = Node('place/tavern', '酒馆', None)
        with acting_as(actor.node_id):
            result = module.act('rest')
        self.assertTrue(result['ok'])
        self.assertEqual(result['events'][0]['message'], '远处有人说话。')
        self.assertEqual(result['changes']['actor'], {'coins': 0, 'items': {}, 'fields': {}})
        self.assertEqual(backend.modules.balances[actor.node_id], 10)
        self.assertEqual(backend.modules.event_counts, {'gossip': 1})


if __name__ == '__main__':
    unittest.main()
