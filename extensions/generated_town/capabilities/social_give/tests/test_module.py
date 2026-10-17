"""social.give 的业务测试（unittest）。"""
import importlib.util
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from datanet.core.access_budget import active_agent

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'social_give_module_under_test', ROOT / 'module.py'
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


class FakeNode:
    def __init__(self, node_id, name, signal_type='agent'):
        self.node_id = node_id
        self.name = name
        self.signal_type = signal_type
        self.interfaces = []
        self.tools = {}
        self.tool_definitions = {}
        self.tool_refusals = {}
        self.expose = []

    def connect(self, target_id, channels, threshold=1):
        for edge in self.interfaces:
            if edge.target_node_id == target_id:
                merged = tuple(dict.fromkeys(tuple(edge.metadata.channels) + tuple(channels)))
                edge.metadata = SimpleNamespace(
                    channels=merged,
                    threshold=edge.metadata.threshold,
                )
                return edge
        edge = SimpleNamespace(
            target_node_id=target_id,
            metadata=SimpleNamespace(channels=tuple(channels), threshold=threshold),
        )
        self.interfaces.append(edge)
        return edge

    def drop_all_edges_to(self, target_id):
        self.interfaces[:] = [
            edge for edge in self.interfaces if edge.target_node_id != target_id
        ]

    def register_tool(self, name, function, *, description, parameters, access_channels, refusal=None):
        self.tools[name] = function
        self.tool_definitions[name] = {
            'name': name,
            'description': description,
            'parameters': parameters,
            'access_channels': list(access_channels),
        }
        if refusal is not None:
            self.tool_refusals[name] = refusal


class FakeNetwork:
    def __init__(self, nodes):
        self.nodes = nodes


class FakeModules:
    def __init__(self, entity_module='entity.profile', action_module='action.points', max_points=10):
        self.entity_module = entity_module
        self.action_module = action_module
        self.max_points = max_points
        self.state = {}
        self.calls = []
        self.fail_adjust_for = set()

    def seed(self, node_id, profile, coins=0, items=None, ap=10):
        self.state[(node_id, self.entity_module)] = {
            'profile': dict(profile),
            'coins': coins,
            'items': dict(items or {}),
        }
        if ap is not None:
            self.state[(node_id, self.action_module)] = {
                'remaining': ap,
                'last_signal_id': None,
            }

    def entity(self, node_id):
        return self.state[(node_id, self.entity_module)]

    def action(self, node_id):
        return self.state[(node_id, self.action_module)]

    def call(self, node_id, module, operation, arguments=None):
        arguments = {} if arguments is None else dict(arguments)
        self.calls.append((node_id, module, operation, arguments))
        key = (node_id, module)
        if key not in self.state:
            raise KeyError(key)
        state = self.state[key]

        if module == self.entity_module and operation == 'read':
            return {
                'profile': deepcopy(state['profile']),
                'coins': state['coins'],
                'items': deepcopy(state['items']),
            }

        if module == self.entity_module and operation == 'adjust':
            if node_id in self.fail_adjust_for:
                raise ValueError('模拟资源调整失败')
            coins = state['coins'] + arguments.get('coins', 0)
            items = dict(state['items'])
            for name, delta in arguments.get('items', {}).items():
                value = items.get(name, 0) + delta
                if value < 0:
                    raise ValueError(f'「{name}」数量不足')
                if value == 0:
                    items.pop(name, None)
                else:
                    items[name] = value
            if coins < 0:
                raise ValueError('金币数量不足')
            state['coins'] = coins
            state['items'] = items
            return {
                'profile': deepcopy(state['profile']),
                'coins': coins,
                'items': deepcopy(items),
            }

        if module == self.action_module and operation == 'get_balance':
            return {
                'ok': True,
                'remaining': state['remaining'],
                'max': self.max_points,
                'message': f"剩余 {state['remaining']}/{self.max_points}。",
            }

        if module == self.action_module and operation == 'spend':
            amount = arguments.get('amount', 0)
            remaining = state['remaining']
            if amount > remaining:
                return {
                    'ok': False,
                    'reason': 'insufficient',
                    'amount': amount,
                    'spent': 0,
                    'remaining': remaining,
                    'max': self.max_points,
                    'message': f'行动值不足：需要 {amount}，剩余 {remaining}/{self.max_points}，未扣除。',
                }
            state['remaining'] = remaining - amount
            return {
                'ok': True,
                'amount': amount,
                'spent': amount,
                'remaining': state['remaining'],
                'max': self.max_points,
                'message': f"扣除 {amount} 行动值，剩余 {state['remaining']}/{self.max_points}。",
            }

        raise KeyError((node_id, module, operation))

    @contextmanager
    def transaction(self, *node_ids):
        snapshots = [
            (state, deepcopy(state))
            for (node_id, _), state in self.state.items()
            if not node_ids or node_id in node_ids
        ]
        try:
            yield
        except BaseException:
            for target, snapshot in snapshots:
                target.clear()
                target.update(snapshot)
            raise


class FakeBackend:
    def __init__(self, modules, nodes):
        self.modules = modules
        self.network = FakeNetwork(nodes)


class SameSceneGiveTests(unittest.TestCase):
    def make(
        self,
        *,
        config=None,
        place_id='place/square',
        alice_place=None,
        bob_place=None,
        alice_coins=10,
        bob_coins=2,
        alice_items=None,
        bob_items=None,
        alice_ap=5,
        with_presence=True,
        entity_module='entity.profile',
        action_module='action.points',
        presence_channel='place.presence',
        place_field='place',
        max_points=10,
    ):
        alice_place = place_id if alice_place is None else alice_place
        bob_place = place_id if bob_place is None else bob_place
        square = FakeNode(place_id, '中央广场', signal_type='node')
        alice = FakeNode('agent/alice', '爱丽丝')
        bob = FakeNode('agent/bob', '鲍勃')
        nodes = {
            place_id: square,
            'agent/alice': alice,
            'agent/bob': bob,
        }

        alice.connect('agent/bob', ['social.give'])
        bob.connect('agent/alice', ['social.give'])
        if with_presence:
            for agent in (alice, bob):
                square.connect(agent.node_id, [presence_channel])
                agent.connect(place_id, [presence_channel])

        modules = FakeModules(entity_module, action_module, max_points)
        modules.seed('agent/alice', {'name': '爱丽丝', place_field: alice_place},
                     coins=alice_coins, items=alice_items, ap=alice_ap)
        modules.seed('agent/bob', {'name': '鲍勃', place_field: bob_place},
                     coins=bob_coins, items=bob_items, ap=10)

        config = {
            'channels': ['social.give'],
            'presence_channel': 'place.presence',
            'entity_module': 'entity.profile',
            'action_module': 'action.points',
        } if config is None else config

        backend = FakeBackend(modules, nodes)
        module = Module(backend, bob, deepcopy(config), {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        return SimpleNamespace(
            module=module, backend=backend, modules=modules,
            alice=alice, bob=bob, square=square, nodes=nodes,
        )

    def test_install_registers_give_and_shows_receiver_name(self):
        env = self.make()
        definition = env.bob.tool_definitions['give']
        self.assertEqual(definition['access_channels'], ['social.give'])
        self.assertIn('鲍勃', definition['description'])
        self.assertIn('give', env.bob.tools)
        self.assertEqual(env.module.state, {})
        self.assertEqual(definition['parameters']['anyOf'],
                         [{'required': ['coins']}, {'required': ['items']}])

    def test_give_coins_moves_coins_and_spends_action(self):
        env = self.make()
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=4)
        self.assertTrue(result['ok'])
        self.assertTrue(result['given'])
        self.assertEqual(result['receiver'], '鲍勃')
        self.assertEqual(result['receiver_id'], 'agent/bob')
        self.assertEqual(result['coins'], 4)
        self.assertEqual(result['items'], {})
        self.assertEqual(result['remaining'], 4)
        self.assertEqual(result['max'], 10)
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 6)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 6)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 4)
        self.assertIn('鲍勃', result['message'])
        self.assertIn('剩余行动值 4/10', result['message'])

    def test_give_items_moves_only_named_items(self):
        env = self.make(
            alice_items={'bread': 2, 'torch': 1},
            bob_items={'bread': 1},
        )
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](items={'bread': 2, 'torch': 1})
        self.assertTrue(result['ok'])
        self.assertEqual(result['items'], {'bread': 2, 'torch': 1})
        self.assertEqual(result['coins'], 0)
        self.assertEqual(env.modules.entity('agent/alice')['items'], {})
        self.assertEqual(env.modules.entity('agent/bob')['items'],
                         {'bread': 3, 'torch': 1})
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 4)

    def test_give_both_coins_and_items(self):
        env = self.make(alice_items={'torch': 1})
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=3, items={'torch': 1})
        self.assertTrue(result['ok'])
        self.assertEqual(result['coins'], 3)
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 7)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 5)
        self.assertEqual(env.modules.entity('agent/alice')['items'], {})
        self.assertEqual(env.modules.entity('agent/bob')['items'], {'torch': 1})

    def test_zero_and_negative_amounts_are_rejected_without_changes(self):
        env = self.make()
        with acting_as('agent/alice'):
            for coins in (0, -1):
                result = env.module.give(coins=coins)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], 'invalid_coins')
            for items in ({'bread': 0}, {'bread': -2}, {}, []):
                result = env.module.give(items=items)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], 'invalid_items')
            result = env.module.give()
            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'], 'empty_gift')
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 10)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_registered_tool_schema_rejects_nonpositive_values(self):
        env = self.make()
        with acting_as('agent/alice'):
            with self.assertRaises(Exception):
                env.bob.tools['give'](coins=0)
            with self.assertRaises(Exception):
                env.bob.tools['give'](items={'bread': -1})

    def test_self_gift_is_rejected(self):
        env = self.make()
        with acting_as('agent/bob'):
            result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'self_gift')
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 2)
        self.assertEqual(env.modules.action('agent/bob')['remaining'], 10)

    def test_different_place_is_rejected_before_any_change(self):
        env = self.make(bob_place='place/hill')
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'not_same_place')
        self.assertIn('鲍勃', result['message'])
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 10)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_missing_all_bidirectional_presence_is_rejected(self):
        env = self.make()
        env.alice.drop_all_edges_to('place/square')
        env.alice.drop_all_edges_to('agent/bob')
        env.bob.drop_all_edges_to('agent/alice')
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'sender_not_really_present')
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 10)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_direct_channel_presence_can_back_up_place_edges(self):
        env = self.make()
        env.alice.drop_all_edges_to('place/square')
        env.bob.drop_all_edges_to('place/square')
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertTrue(result['ok'])
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 3)

    def test_receiver_one_way_presence_is_rejected(self):
        env = self.make()
        env.square.drop_all_edges_to('agent/bob')
        env.bob.drop_all_edges_to('agent/alice')
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'receiver_not_really_present')
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 2)

    def test_insufficient_coins_is_rejected_without_spending_action(self):
        env = self.make(alice_coins=2)
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=5)
        self.assertEqual(result['reason'], 'insufficient_coins')
        self.assertIn('金币不足', result['message'])
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 2)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_insufficient_items_is_rejected_without_spending_action(self):
        env = self.make(alice_items={'面包': 1})
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](items={'面包': 2})
        self.assertEqual(result['reason'], 'insufficient_items')
        self.assertIn('面包', result['message'])
        self.assertEqual(env.modules.entity('agent/alice')['items'], {'面包': 1})
        self.assertEqual(env.modules.entity('agent/bob')['items'], {})
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_insufficient_action_is_rejected_without_moving_resources(self):
        env = self.make(alice_ap=0)
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'insufficient_action')
        self.assertEqual(result['remaining'], 0)
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 10)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 2)

    def test_failed_receiver_adjust_rolls_back_sender_and_action(self):
        env = self.make()
        env.modules.fail_adjust_for.add('agent/bob')
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=4)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'transfer_failed')
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 10)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 2)
        self.assertEqual(env.modules.action('agent/alice')['remaining'], 5)

    def test_without_caller_is_rejected(self):
        env = self.make()
        result = env.bob.tools['give'](coins=1)
        self.assertEqual(result['reason'], 'no_caller')
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 2)

    def test_zero_action_cost_still_gives(self):
        config = {
            'channels': ['social.give'],
            'presence_channel': 'place.presence',
            'action_cost': 0,
        }
        env = self.make(config=config)
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['remaining'], 5)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 3)

    def test_custom_channels_place_field_and_component_ids(self):
        config = {
            'channels': ['exchange.gift'],
            'presence_channel': 'scene.presence',
            'place_field': 'location',
            'entity_module': 'my.profile',
            'action_module': 'my.points',
            'action_cost': 3,
        }
        env = self.make(
            config=config,
            place_id='scene/hall',
            alice_place='scene/hall',
            bob_place='scene/hall',
            entity_module='my.profile',
            action_module='my.points',
            presence_channel='scene.presence',
            place_field='location',
        )
        self.assertEqual(env.bob.tool_definitions['give']['access_channels'],
                         ['exchange.gift'])
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](coins=1)
        self.assertTrue(result['ok'])
        self.assertEqual(result['remaining'], 2)
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 9)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 3)

    def test_display_name_is_used_when_receiver_profile_is_missing(self):
        square = FakeNode('place/square', '中央广场', signal_type='node')
        alice = FakeNode('agent/alice', '爱丽丝')
        bob = FakeNode('agent/bob', '鲍勃')
        nodes = {'place/square': square, 'agent/alice': alice, 'agent/bob': bob}
        square.connect('agent/alice', ['place.presence'])
        alice.connect('place/square', ['place.presence'])
        modules = FakeModules()
        modules.seed('agent/alice', {'name': '爱丽丝', 'place': 'place/square'}, ap=5)
        backend = FakeBackend(modules, nodes)
        module = Module(backend, bob, {
            'channels': ['social.give'],
            'display_name': '阿岚',
        }, {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        self.assertIn('阿岚', bob.tool_definitions['give']['description'])

    def test_missing_channel_config_is_rejected(self):
        node = FakeNode('agent/bob', '鲍勃')
        backend = FakeBackend(FakeModules(), {'agent/bob': node})
        module = Module(backend, node, {}, {})
        module.manifest = deepcopy(MANIFEST)
        with self.assertRaises(Exception):
            module.install()

    def test_install_with_minimal_backend_uses_display_name(self):
        # 与工作室契约探针一致：backend 只有 network，没有 modules。
        node = FakeNode('agent/bob', '鲍勃')
        backend = SimpleNamespace(network=FakeNetwork({'agent/bob': node}), directory=ROOT)
        example = json.loads((ROOT / 'example.json').read_text(encoding='utf-8'))
        module = Module(backend, node, deepcopy(example['config']), {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        self.assertEqual(node.tool_definitions['give']['access_channels'], ['social.give'])
        self.assertIn('阿岚', node.tool_definitions['give']['description'])

    def test_repeated_gifts_accumulate(self):
        env = self.make()
        with acting_as('agent/alice'):
            first = env.bob.tools['give'](coins=1)
            second = env.bob.tools['give'](coins=2)
        self.assertEqual(first['remaining'], 4)
        self.assertEqual(second['remaining'], 3)
        self.assertEqual(env.modules.entity('agent/alice')['coins'], 7)
        self.assertEqual(env.modules.entity('agent/bob')['coins'], 5)

    def test_item_name_whitespace_is_trimmed_for_matching(self):
        env = self.make(alice_items={'bread': 1})
        with acting_as('agent/alice'):
            result = env.bob.tools['give'](items={' bread ': 1})
        self.assertTrue(result['ok'])
        self.assertEqual(result['items'], {'bread': 1})
        self.assertEqual(env.modules.entity('agent/alice')['items'], {})
        self.assertEqual(env.modules.entity('agent/bob')['items'], {'bread': 1})


if __name__ == '__main__':
    unittest.main()
