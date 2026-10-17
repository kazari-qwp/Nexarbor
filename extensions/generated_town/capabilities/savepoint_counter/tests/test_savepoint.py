import json
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from jsonschema.exceptions import ValidationError

from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.signals import Signal
from datanet.studio.contract import factory

FOLDER = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(FOLDER)


class SavepointCounterTests(unittest.TestCase):
    def mount(self, config=None, state=None):
        node = Node('counter-1', 'Counter', None)
        saves = []

        def dispatch(*args, **kwargs):
            saves.append((args, kwargs))
            return {'saved': True}

        backend = SimpleNamespace(network=Network(), dispatch=dispatch)
        backend.network.add_node(node)
        instance = CREATE(backend, node, {} if config is None else config,
                          {} if state is None else state)
        instance.install()
        self.addCleanup(instance.close)
        return instance, node, saves

    def context(self, instance, node, signal_id):
        signal = Signal('clock', ['world.tick'], 2, content={'tick': 1}, signal_id=signal_id)
        return SimpleNamespace(
            signal=signal,
            delivery=SimpleNamespace(node_id=node.node_id, strength=1),
            network=instance.backend.network,
        )

    def tick(self, instance, node, signal_id):
        return instance.on_signal(self.context(instance, node, signal_id))

    def test_manifest_declares_node_surface(self):
        self.assertEqual(SPEC['id'], 'savepoint.counter')
        self.assertEqual(SPEC['node_types'], ['node'])
        self.assertEqual(SPEC['signals'], ['world.tick'])
        self.assertEqual(SPEC['tools'], [])
        self.assertEqual([item['name'] for item in SPEC['operations']], ['get_count'])

    def test_example_config_uses_default_interval_five(self):
        defaults = json.loads((FOLDER / 'example.json').read_text(encoding='utf-8'))
        self.assertEqual(defaults['config'], {'interval': 5})
        instance, _, _ = self.mount(defaults['config'])
        self.assertEqual(instance.invoke_operation('get_count', {})['interval'], 5)

    def test_setup_initializes_missing_state(self):
        instance, _, _ = self.mount()
        self.assertEqual(instance.state['count'], 0)
        self.assertIsNone(instance.state['last_signal'])
        self.assertEqual(instance.state['recent_signals'], [])

    def test_new_signal_counts_once_and_reports_not_full(self):
        instance, node, saves = self.mount()
        result = self.tick(instance, node, 'sig-1')
        self.assertEqual(result, {'count': 1, 'full_snapshot': False, 'reused': False})
        self.assertEqual(saves, [])
        self.assertEqual(instance.state['last_signal'], 'sig-1')

    def test_same_signal_is_not_counted_twice(self):
        instance, node, saves = self.mount()
        self.tick(instance, node, 'sig-1')
        before = deepcopy(instance.state)
        result = self.tick(instance, node, 'sig-1')
        self.assertEqual(result, {'count': 1, 'full_snapshot': False, 'reused': True})
        self.assertEqual(instance.state, before)
        self.assertEqual(saves, [])

    def test_same_content_with_new_signal_ids_counts_each_time(self):
        instance, node, _ = self.mount()
        self.tick(instance, node, 'sig-1')
        result = self.tick(instance, node, 'sig-2')
        self.assertEqual(result['count'], 2)

    def test_non_consecutive_repeat_is_ignored(self):
        instance, node, _ = self.mount()
        self.tick(instance, node, 'sig-1')
        self.tick(instance, node, 'sig-2')
        result = self.tick(instance, node, 'sig-1')
        self.assertEqual(result['count'], 2)
        self.assertTrue(result['reused'])
        self.assertEqual(instance.state['last_signal'], 'sig-2')

    def test_default_interval_requests_full_save_every_five_counts(self):
        instance, node, saves = self.mount()
        for index in range(1, 11):
            self.tick(instance, node, 'sig-%d' % index)
        self.assertEqual([item[0][0] for item in saves], ['save', 'save'])
        self.assertEqual(saves[0][0], ('save', {'full': True}))
        self.assertEqual(instance.state['count'], 10)

    def test_configured_interval_requests_save_at_each_multiple(self):
        instance, node, saves = self.mount({'interval': 3})
        for index in range(1, 7):
            result = self.tick(instance, node, 'sig-%d' % index)
            self.assertEqual(result['full_snapshot'], index % 3 == 0)
        self.assertEqual(len(saves), 2)

    def test_duplicate_does_not_request_extra_save(self):
        instance, node, saves = self.mount({'interval': 1})
        self.tick(instance, node, 'sig-1')
        self.assertEqual(len(saves), 1)
        self.tick(instance, node, 'sig-1')
        self.assertEqual(len(saves), 1)

    def test_persisted_state_continues_counting(self):
        instance, node, saves = self.mount(
            {'interval': 5}, {'count': 4, 'last_signal': 'sig-4'})
        duplicate = self.tick(instance, node, 'sig-4')
        self.assertEqual(duplicate['count'], 4)
        result = self.tick(instance, node, 'sig-5')
        self.assertEqual(result['count'], 5)
        self.assertTrue(result['full_snapshot'])
        self.assertEqual(len(saves), 1)

    def test_get_count_reports_persisted_values(self):
        instance, node, _ = self.mount({'interval': 7})
        self.tick(instance, node, 'sig-1')
        self.assertEqual(instance.invoke_operation('get_count', {}),
                         {'count': 1, 'last_signal': 'sig-1', 'interval': 7})

    def test_invalid_interval_is_rejected_at_mount(self):
        with self.assertRaises(ValidationError):
            self.mount({'interval': 0})
        with self.assertRaises(ValidationError):
            self.mount({'interval': '5'})

    def test_unknown_config_field_is_rejected_at_mount(self):
        with self.assertRaises(ValidationError):
            self.mount({'intervals': 5})


if __name__ == '__main__':
    unittest.main()
