import asyncio
import json
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from datanet.core.signals import Signal, SignalContext, SignalDelivery
from datanet.studio.contract import factory

FOLDER = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(FOLDER)
DEFAULTS = json.loads((FOLDER / 'example.json').read_text(encoding='utf-8'))['config']
NODE_ID = 'agent-a'


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.error = None

    async def execute_agent(self, node_id, message=''):
        self.calls.append({'node_id': node_id, 'message': message})
        if self.error is not None:
            raise self.error
        return {'status': 'completed', 'session_id': 'session-a', 'steps': 0, 'output': ''}


def make_signal(origin='town/pulse'):
    return Signal(origin, ['world.tick'], 2)


def make_context(signal):
    delivery = SignalDelivery(node_id=NODE_ID, depth=1, strength=1, path=(), parents=())
    return SignalContext(signal=signal, delivery=delivery, network=None)


class ActivityTests(unittest.TestCase):
    def mount(self, config=None, state=None):
        backend = FakeBackend()
        node = SimpleNamespace(node_id=NODE_ID, signal_type='agent')
        module = CREATE(backend, node, dict(DEFAULTS if config is None else config), {} if state is None else state)
        module.install()
        return module, backend

    def run_signal(self, module, signal):
        return asyncio.run(module.on_signal(make_context(signal)))

    def test_setup_seeds_missing_state(self):
        module, _ = self.mount()
        self.assertEqual(module.state['processed_signal_ids'], [])
        self.assertIsNone(module.state['last_signal_id'])
        self.assertEqual(module.state['completed_count'], 0)
        Draft202012Validator(SPEC['state_schema']).validate(module.state)

    def test_setup_keeps_existing_state(self):
        state = {'processed_signal_ids': ['old'], 'last_signal_id': 'old', 'completed_count': 7}
        module, _ = self.mount(state=state)
        self.assertEqual(module.state, state)

    def test_success_executes_once_and_records_signal_id(self):
        module, backend = self.mount()
        signal = make_signal()
        result = self.run_signal(module, signal)

        self.assertEqual(backend.calls, [{'node_id': NODE_ID, 'message': DEFAULTS['message']}])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['signal_id'], signal.signal_id)
        self.assertEqual(module.state['processed_signal_ids'], [signal.signal_id])
        self.assertEqual(module.state['last_signal_id'], signal.signal_id)
        self.assertEqual(module.state['completed_count'], 1)
        Draft202012Validator(SPEC['state_schema']).validate(module.state)

    def test_same_signal_does_not_execute_twice(self):
        module, backend = self.mount()
        signal = make_signal()
        self.run_signal(module, signal)
        snapshot = deepcopy(module.state)

        result = self.run_signal(module, signal)

        self.assertEqual(result, {'status': 'duplicate', 'signal_id': signal.signal_id})
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(module.state, snapshot)

    def test_distinct_signals_each_execute(self):
        module, backend = self.mount()
        first, second = make_signal(), make_signal()

        self.run_signal(module, first)
        self.run_signal(module, second)

        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(module.state['processed_signal_ids'], [first.signal_id, second.signal_id])
        self.assertEqual(module.state['completed_count'], 2)

    def test_failure_is_not_recorded_and_can_retry(self):
        module, backend = self.mount()
        signal = make_signal()
        backend.error = RuntimeError('executor failed')
        before = deepcopy(module.state)

        with self.assertRaises(RuntimeError):
            self.run_signal(module, signal)

        self.assertEqual(module.state, before)
        self.assertNotIn(signal.signal_id, module.state['processed_signal_ids'])

        backend.error = None
        result = self.run_signal(module, signal)

        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(module.state['processed_signal_ids'], [signal.signal_id])
        self.assertEqual(module.state['completed_count'], 1)

    def test_history_is_bounded_by_config(self):
        module, backend = self.mount(config={'message': 'act', 'max_history': 2})
        signals = [make_signal() for _ in range(3)]

        for signal in signals:
            self.run_signal(module, signal)

        self.assertEqual(module.state['processed_signal_ids'], [signals[1].signal_id, signals[2].signal_id])
        self.assertEqual(module.state['completed_count'], 3)

        # 被移出窗口的信号不再去重，会重新执行；这是有界历史的预期行为。
        self.run_signal(module, signals[0])
        self.assertEqual(len(backend.calls), 4)

    def test_install_rejects_non_agent_node(self):
        backend = FakeBackend()
        node = SimpleNamespace(node_id=NODE_ID, signal_type='node')
        module = CREATE(backend, node, dict(DEFAULTS), {})
        with self.assertRaises(ValueError):
            module.install()


if __name__ == '__main__':
    unittest.main()
