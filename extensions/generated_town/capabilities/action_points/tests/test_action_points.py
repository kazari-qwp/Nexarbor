import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from jsonschema.exceptions import ValidationError

from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.signals import Signal
from datanet.studio.contract import factory

FOLDER = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(FOLDER)


class ActionPointsTests(unittest.TestCase):
    def mount(self, config=None, state=None, node=None):
        if node is None:
            node = AgentNode('agent-1', 'Agent', file_path=FOLDER / 'tests' / '.memory.md')
        backend = SimpleNamespace(network=Network(), dispatch=lambda *args, **kwargs: {'saved': True})
        backend.network.add_node(node)
        instance = CREATE(backend, node, {} if config is None else config,
                          {} if state is None else state)
        instance.install()
        self.addCleanup(instance.close)
        return instance, node, backend

    def context(self, instance, node, signal):
        return SimpleNamespace(
            signal=signal,
            delivery=SimpleNamespace(node_id=node.node_id, strength=1),
            network=instance.backend.network,
        )

    def tick(self, signal_id=None):
        options = {} if signal_id is None else {'signal_id': signal_id}
        return Signal('clock', ['world.tick'], 2, content={'tick': 1}, **options)

    def test_manifest_declares_agent_surface(self):
        self.assertEqual(SPEC['id'], 'action.points')
        self.assertEqual(SPEC['node_types'], ['agent'])
        self.assertEqual(SPEC['signals'], ['world.tick'])
        self.assertEqual(SPEC['tools'], [])
        self.assertEqual({item['name'] for item in SPEC['operations']},
                         {'get_balance', 'check', 'spend'})

    def test_default_mount_is_full_and_balance_mentions_remaining(self):
        instance, _, _ = self.mount()
        balance = instance.invoke_operation('get_balance', {})
        self.assertEqual((balance['remaining'], balance['max']), (10, 10))
        self.assertIn('10/10', balance['message'])

    def test_configured_max_drives_balance_and_spend(self):
        instance, _, _ = self.mount({'max': 3})
        self.assertEqual(instance.state['remaining'], 3)
        checked = instance.invoke_operation('check', {'amount': 2})
        self.assertTrue(checked['ok'])
        self.assertEqual(checked['remaining'], 3)
        self.assertEqual(instance.state['remaining'], 3)
        result = instance.invoke_operation('spend', {'amount': 2})
        self.assertTrue(result['ok'])
        self.assertEqual(result['spent'], 2)
        self.assertEqual(result['remaining'], 1)
        self.assertIn('1/3', result['message'])

    def test_insufficient_spend_is_rejected_without_deduction(self):
        instance, _, _ = self.mount({'max': 2})
        instance.invoke_operation('spend', {'amount': 2})
        result = instance.invoke_operation('spend', {'amount': 1})
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'insufficient')
        self.assertEqual(result['spent'], 0)
        self.assertEqual(result['remaining'], 0)
        self.assertEqual(instance.state['remaining'], 0)
        self.assertIn('未扣除', result['message'])
        self.assertIn('0/2', result['message'])

    def test_check_does_not_spend_and_reports_remaining(self):
        instance, _, _ = self.mount({'max': 2})
        result = instance.invoke_operation('check', {'amount': 3})
        self.assertFalse(result['ok'])
        self.assertEqual(instance.state['remaining'], 2)
        self.assertIn('2/2', result['message'])

    def test_zero_amount_is_safe(self):
        instance, _, _ = self.mount({'max': 2})
        checked = instance.invoke_operation('check', {'amount': 0})
        self.assertTrue(checked['ok'])
        spent = instance.invoke_operation('spend', {'amount': 0})
        self.assertTrue(spent['ok'])
        self.assertEqual(spent['spent'], 0)
        self.assertEqual(instance.state['remaining'], 2)

    def test_new_moment_restores_to_max(self):
        instance, node, _ = self.mount({'max': 5})
        instance.invoke_operation('spend', {'amount': 4})
        self.assertEqual(instance.state['remaining'], 1)
        signal = self.tick()
        result = instance.on_signal(self.context(instance, node, signal))
        self.assertTrue(result['changed'])
        self.assertEqual(instance.state['remaining'], 5)
        self.assertEqual(instance.state['last_signal_id'], signal.signal_id)
        self.assertIn('5/5', result['message'])

    def test_repeated_same_signal_does_not_reset(self):
        instance, node, _ = self.mount({'max': 5})
        signal = self.tick()
        context = self.context(instance, node, signal)
        instance.on_signal(context)
        instance.invoke_operation('spend', {'amount': 2})
        before = deepcopy(instance.state)
        result = instance.on_signal(context)
        self.assertFalse(result['changed'])
        self.assertEqual(instance.state, before)
        self.assertEqual(instance.state['remaining'], 3)
        self.assertIn('3/5', result['message'])

    def test_new_signal_with_same_payload_starts_new_moment(self):
        instance, node, _ = self.mount({'max': 5})
        first = self.tick()
        second = self.tick()
        self.assertNotEqual(first.signal_id, second.signal_id)
        instance.on_signal(self.context(instance, node, first))
        instance.invoke_operation('spend', {'amount': 4})
        result = instance.on_signal(self.context(instance, node, second))
        self.assertTrue(result['changed'])
        self.assertEqual(instance.state['remaining'], 5)

    def test_state_restores_and_continues(self):
        instance, _, _ = self.mount({'max': 6})
        instance.invoke_operation('spend', {'amount': 5})
        state = deepcopy(instance.state)
        node = AgentNode('agent-2', 'Agent 2', file_path=FOLDER / 'tests' / '.memory-2.md')
        restored, _, _ = self.mount({'max': 6}, state=state, node=node)
        balance = restored.invoke_operation('get_balance', {})
        self.assertEqual(balance['remaining'], 1)
        self.assertEqual(restored.state['last_signal_id'], state['last_signal_id'])

    def test_restored_duplicate_signal_is_ignored(self):
        signal = self.tick()
        state = {'remaining': 2, 'last_signal_id': signal.signal_id}
        instance, node, _ = self.mount({'max': 4}, state=state)
        result = instance.on_signal(self.context(instance, node, signal))
        self.assertFalse(result['changed'])
        self.assertEqual(instance.state['remaining'], 2)

    def test_restored_balance_is_clamped_to_new_max(self):
        state = {'remaining': 99, 'last_signal_id': None}
        instance, _, _ = self.mount({'max': 4}, state=state)
        self.assertEqual(instance.state['remaining'], 4)

    def test_zero_max_allows_no_spending(self):
        instance, _, _ = self.mount({'max': 0})
        self.assertEqual(instance.invoke_operation('get_balance', {})['remaining'], 0)
        result = instance.invoke_operation('spend', {'amount': 1})
        self.assertFalse(result['ok'])
        self.assertEqual(instance.state['remaining'], 0)

    def test_mount_on_plain_node_is_rejected(self):
        node = Node('plain', 'Plain', None)
        with self.assertRaises(ValueError):
            self.mount(node=node)

    def test_invalid_arguments_are_rejected_by_schema(self):
        instance, _, _ = self.mount()
        with self.assertRaises(ValidationError):
            instance.invoke_operation('spend', {'amount': -1})
        with self.assertRaises(ValidationError):
            instance.invoke_operation('check', {'amount': 1, 'extra': True})
        with self.assertRaises(ValueError):
            instance.invoke_operation('reset', {})
        self.assertEqual(instance.state['remaining'], 10)


if __name__ == '__main__':
    unittest.main()
