"""social.same_place 的业务测试（unittest）。"""
import importlib.util
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from datanet.core.access_budget import active_agent
from datanet.core.agent_inputs import AgentInputs

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'social_same_place_module_under_test', ROOT / 'module.py'
)
MODULE_FILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE_FILE)
Module = MODULE_FILE.Module
MANIFEST = json.loads((ROOT / 'module.json').read_text(encoding='utf-8'))
GONE_MESSAGE = '他好像已经去了某地点，已经不在这里了'


@contextmanager
def acting_as(node_id):
    token = active_agent.set((SimpleNamespace(max_signal_strength=3), node_id))
    try:
        yield
    finally:
        active_agent.reset(token)


class FakeNode:
    signal_type = 'agent'

    def __init__(self, node_id='agent/bob', name='鲍勃'):
        self.node_id = node_id
        self.name = name
        self.inputs = AgentInputs()
        self.tools = {}
        self.tool_definitions = {}
        self.tool_refusals = {}
        self.expose = []

    def register_tool(self, name, function, *, description, parameters, access_channels,
                      refusal=None):
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
    def __init__(self, profiles, balances, max_points=10):
        self.profiles = profiles
        self.balances = balances
        self.max_points = max_points
        self.calls = []

    def call(self, node_id, module, operation, arguments=None):
        arguments = {} if arguments is None else dict(arguments)
        self.calls.append((node_id, module, operation, arguments))
        if module == 'entity.profile' and operation == 'read':
            if node_id not in self.profiles:
                raise KeyError(node_id)
            return {'profile': dict(self.profiles[node_id]), 'coins': 0, 'items': {}}
        if module == 'action.points' and operation == 'spend':
            amount = arguments.get('amount', 0)
            remaining = self.balances.get(node_id, self.max_points)
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
            remaining -= amount
            self.balances[node_id] = remaining
            return {
                'ok': True,
                'amount': amount,
                'spent': amount,
                'remaining': remaining,
                'max': self.max_points,
                'message': f'扣除 {amount} 行动值，剩余 {remaining}/{self.max_points}。',
            }
        raise KeyError((node_id, module, operation))


class FakeBackend:
    def __init__(self, profiles, balances, nodes=None, max_points=10):
        self.modules = FakeModules(profiles, balances, max_points)
        self.network = FakeNetwork(nodes or {})


class SamePlaceTalkTests(unittest.TestCase):
    def make(self, config=None, profiles=None, balances=None):
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'place': '广场'},
            'agent/bob': {'name': '鲍勃', 'place': '广场'},
        } if profiles is None else profiles
        balances = {'agent/alice': 5} if balances is None else balances
        node = FakeNode()
        backend = FakeBackend(profiles, balances, nodes={'agent/bob': node})
        config = {'channels': ['social.same_place']} if config is None else config
        module = Module(backend, node, config, {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        return module, backend, node

    def test_install_registers_talk_on_configured_channel(self):
        module, backend, node = self.make()
        definition = node.tool_definitions['talk']
        self.assertEqual(definition['access_channels'], ['social.same_place'])
        self.assertEqual(definition['parameters']['required'], ['message'])
        self.assertIn('鲍勃', definition['description'])
        self.assertIn('talk', node.tools)
        self.assertEqual(module.state, {})

    def test_talk_delivers_sender_name_and_unique_id_to_receiver_inputs(self):
        module, backend, node = self.make()
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertTrue(result['ok'])
        self.assertTrue(result['sent'])
        self.assertEqual(result['remaining'], 4)
        self.assertEqual(result['max'], 10)
        self.assertEqual(result['receiver'], '鲍勃')
        pending = node.inputs.pending()
        self.assertEqual(len(pending), 1)
        source, event = pending[0]
        self.assertEqual(source, 'social.same_place')
        self.assertEqual(event['id'], result['input_id'])
        self.assertEqual(event['status'], 'pending')
        self.assertIn('爱丽丝', event['text'])
        self.assertIn('agent/alice', event['text'])
        self.assertIn('你好', event['text'])
        self.assertIn('剩余行动值 4/10', result['message'])

    def test_receiver_left_returns_gone_message_without_spending(self):
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'place': '广场'},
            'agent/bob': {'name': '鲍勃', 'place': '集市'},
        }
        module, backend, node = self.make(profiles=profiles)
        with acting_as('agent/alice'):
            result = module.talk(message='还在吗')
        self.assertFalse(result['ok'])
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'receiver_not_present')
        self.assertEqual(result['message'], GONE_MESSAGE)
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 5)

    def test_receiver_without_place_counts_as_left(self):
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'place': '广场'},
            'agent/bob': {'name': '鲍勃'},
        }
        module, backend, node = self.make(profiles=profiles)
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertEqual(result['reason'], 'receiver_not_present')
        self.assertEqual(node.inputs.pending(), [])

    def test_sender_without_place_does_not_send(self):
        profiles = {
            'agent/alice': {'name': '爱丽丝'},
            'agent/bob': {'name': '鲍勃', 'place': '广场'},
        }
        module, backend, node = self.make(profiles=profiles)
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertEqual(result['reason'], 'sender_not_present')
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 5)

    def test_missing_sender_profile_does_not_send(self):
        profiles = {'agent/bob': {'name': '鲍勃', 'place': '广场'}}
        module, backend, node = self.make(profiles=profiles)
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertEqual(result['reason'], 'sender_profile_unavailable')
        self.assertEqual(node.inputs.pending(), [])

    def test_insufficient_action_value_blocks_delivery(self):
        module, backend, node = self.make(balances={'agent/alice': 0})
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient_action')
        self.assertEqual(result['remaining'], 0)
        self.assertIn('行动值不足', result['message'])
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 0)

    def test_action_cost_is_configurable(self):
        module, backend, node = self.make(
            config={'channels': ['social.same_place'], 'action_cost': 3}
        )
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertTrue(result['ok'])
        self.assertEqual(result['remaining'], 2)
        self.assertEqual(backend.modules.balances['agent/alice'], 2)

    def test_zero_action_cost_still_sends(self):
        module, backend, node = self.make(
            config={'channels': ['social.same_place'], 'action_cost': 0}
        )
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertTrue(result['ok'])
        self.assertEqual(result['remaining'], 5)
        self.assertEqual(len(node.inputs.pending()), 1)

    def test_self_talk_is_rejected(self):
        module, backend, node = self.make()
        with acting_as('agent/bob'):
            result = module.talk(message='自言自语')
        self.assertEqual(result['reason'], 'self_talk')
        self.assertEqual(node.inputs.pending(), [])

    def test_without_caller_is_rejected(self):
        module, backend, node = self.make()
        result = module.talk(message='你好')
        self.assertEqual(result['reason'], 'no_caller')
        self.assertEqual(node.inputs.pending(), [])

    def test_empty_message_is_rejected(self):
        module, backend, node = self.make()
        with acting_as('agent/alice'):
            result = module.talk(message='   ')
        self.assertEqual(result['reason'], 'empty_message')
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 5)

    def test_repeated_talks_create_distinct_pending_inputs(self):
        module, backend, node = self.make()
        with acting_as('agent/alice'):
            first = module.talk(message='第一句')
            second = module.talk(message='第二句')
        self.assertNotEqual(first['input_id'], second['input_id'])
        self.assertEqual(second['remaining'], 3)
        pending = node.inputs.pending()
        self.assertEqual(len(pending), 2)
        self.assertEqual([event['id'] for _, event in pending],
                         [first['input_id'], second['input_id']])

    def test_custom_place_field_and_channel(self):
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'location': '月台'},
            'agent/bob': {'name': '鲍勃', 'location': '月台'},
        }
        module, backend, node = self.make(
            config={'channels': ['scene.hall'], 'place_field': 'location'},
            profiles=profiles,
        )
        self.assertEqual(node.tool_definitions['talk']['access_channels'], ['scene.hall'])
        with acting_as('agent/alice'):
            result = module.talk(message='车来了')
        self.assertTrue(result['ok'])
        self.assertEqual(len(node.inputs.pending()), 1)

    def test_description_falls_back_to_display_name(self):
        profiles = {'agent/alice': {'name': '爱丽丝', 'place': '广场'}}
        module, backend, node = self.make(
            config={'channels': ['social.same_place'], 'display_name': '阿岚'},
            profiles=profiles,
        )
        self.assertIn('阿岚', node.tool_definitions['talk']['description'])

    def test_missing_channel_config_is_rejected(self):
        node = FakeNode()
        backend = FakeBackend({}, {})
        module = Module(backend, node, {}, {})
        module.manifest = deepcopy(MANIFEST)
        with self.assertRaises(Exception):
            module.install()

    def test_dependency_module_ids_are_configurable(self):
        node = FakeNode()
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'place': '广场'},
            'agent/bob': {'name': '鲍勃', 'place': '广场'},
        }
        backend = FakeBackend(profiles, {'agent/alice': 5})
        seen = []
        module = Module(
            backend,
            node,
            {
                'channels': ['social.same_place'],
                'profile_module': 'my.profile',
                'action_module': 'my.points',
            },
            {},
        )
        module.manifest = deepcopy(MANIFEST)

        def fake_call(node_id, module, operation, arguments=None):
            seen.append(module)
            if module == 'my.profile' and operation == 'read':
                return {'profile': dict(profiles[node_id])}
            if module == 'my.points' and operation == 'spend':
                return {
                    'ok': True,
                    'remaining': 4,
                    'max': 10,
                    'message': '扣除 1 行动值，剩余 4/10。',
                }
            raise KeyError((node_id, module, operation))

        backend.modules.call = fake_call
        module.install()
        self.assertIn('my.profile', seen)
        with acting_as('agent/alice'):
            result = module.talk(message='你好')
        self.assertTrue(result['ok'])
        self.assertEqual(result['remaining'], 4)
        self.assertIn('my.points', seen)

    def test_tool_refusal_reports_receiver_current_place(self):
        module, backend, node = self.make()
        self.assertIn('talk', node.tool_refusals)
        backend.modules.calls.clear()
        backend.modules.profiles['agent/bob']['place'] = '集市'
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        message = node.tool_refusals['talk']('agent/alice', reason)
        self.assertEqual(message, '鲍勃好像已经去了「集市」，已经不在这里了')
        self.assertEqual(module.state, {})
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 5)
        self.assertNotIn('spend', [call[2] for call in backend.modules.calls])

    def test_tool_refusal_resolves_place_id_to_node_name(self):
        module, backend, node = self.make()
        backend.network.nodes['place/home1'] = SimpleNamespace(
            node_id='place/home1', name='居民楼1'
        )
        backend.modules.profiles['agent/bob']['place'] = 'place/home1'
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        message = node.tool_refusals['talk']('agent/alice', reason)
        self.assertEqual(message, '鲍勃好像已经去了「居民楼1」，已经不在这里了')
        self.assertEqual(module.state, {})
        self.assertEqual(node.inputs.pending(), [])
        self.assertEqual(backend.modules.balances['agent/alice'], 5)

    def test_tool_refusal_keeps_place_id_when_node_missing(self):
        module, backend, node = self.make()
        backend.modules.profiles['agent/bob']['place'] = 'place/missing'
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        message = node.tool_refusals['talk']('agent/alice', reason)
        self.assertEqual(message, '鲍勃好像已经去了「place/missing」，已经不在这里了')

    def test_on_tool_denied_same_place_returns_framework_reason(self):
        module, backend, node = self.make()
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        self.assertEqual(module.on_tool_denied('talk', 'agent/alice', reason), reason)

    def test_on_tool_denied_unknown_position_returns_framework_reason(self):
        profiles = {'agent/bob': {'name': '鲍勃', 'place': '广场'}}
        module, backend, node = self.make(profiles=profiles)
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        self.assertEqual(module.on_tool_denied('talk', 'agent/alice', reason), reason)

    def test_on_tool_denied_receiver_without_place_returns_framework_reason(self):
        profiles = {
            'agent/alice': {'name': '爱丽丝', 'place': '广场'},
            'agent/bob': {'name': '鲍勃'},
        }
        module, backend, node = self.make(profiles=profiles)
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        self.assertEqual(module.on_tool_denied('talk', 'agent/alice', reason), reason)

    def test_on_tool_denied_other_cases_return_framework_reason(self):
        module, backend, node = self.make()
        reason = '这个工具已离开你当前可达的范围，不能执行。'
        self.assertEqual(module.on_tool_denied('entity_view', 'agent/alice', reason), reason)
        self.assertEqual(module.on_tool_denied('talk', None, reason), reason)
        self.assertEqual(module.on_tool_denied('talk', 'agent/bob', reason), reason)

    def test_install_with_minimal_backend_uses_display_name(self):
        # 与工作室契约探针一致：backend 只有 network，没有 modules。
        node = FakeNode()
        backend = SimpleNamespace(network=FakeNetwork({'agent/bob': node}), directory=ROOT)
        example = json.loads((ROOT / 'example.json').read_text(encoding='utf-8'))
        module = Module(backend, node, deepcopy(example['config']), {})
        module.manifest = deepcopy(MANIFEST)
        module.install()
        self.assertEqual(node.tool_definitions['talk']['access_channels'], ['social.same_place'])
        self.assertIn('阿岚', node.tool_definitions['talk']['description'])


if __name__ == '__main__':
    unittest.main()
