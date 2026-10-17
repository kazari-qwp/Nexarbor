"""概率事件组件的业务测试：触发筛选、独立抽取、概率 0/1、命中上限、持久化与配置校验。"""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError, validate

from datanet.studio.contract import factory

ROOT = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(ROOT)
EMPTY = {"counts": {}}


class FakeNode:
    signal_type = 'node'

    def __init__(self):
        self.node_id = 'chance'
        self.tools = {}
        self.tool_definitions = {}
        self.expose = []


def event(event_id, triggers=('explore',), probability=1.0, max_hits=None,
          message=..., effects=...):
    raw = {
        'id': event_id,
        'triggers': list(triggers),
        'probability': probability,
        'max_hits': max_hits,
        'message': '消息-' + event_id if message is ... else message,
    }
    if effects is not ...:
        raw['effects'] = effects
    return raw


def config(*events):
    return {'events': list(events)}


class ChanceEventsTests(unittest.TestCase):
    def setUp(self):
        self.backend = SimpleNamespace()
        self.node = FakeNode()

    def instance(self, cfg=None, state=None):
        return CREATE(self.backend, self.node, dict(config() if cfg is None else cfg),
                      dict(EMPTY if state is None else state))

    def mount(self, cfg=None, state=None):
        module = self.instance(cfg, state)
        module.install()
        return module

    def test_manifest_declares_contract_surface(self):
        spec = json.loads((ROOT / 'module.json').read_text(encoding='utf-8'))
        self.assertEqual(SPEC['id'], 'chance.events')
        self.assertEqual(SPEC['version'], '1.0.0')
        self.assertEqual(spec['format'], 'nexarbor-module/v1')
        self.assertEqual(spec['node_types'], ['node'])
        self.assertEqual(spec['requires'], [])
        self.assertEqual(spec['tools'], [])
        self.assertEqual(spec['signals'], [])
        self.assertEqual([item['name'] for item in spec['operations']], ['draw'])
        instance = self.instance()
        for item in spec['operations']:
            Draft202012Validator.check_schema(item['parameters'])
            self.assertEqual(item['parameters']['type'], 'object')
            self.assertTrue(callable(getattr(instance, item['name'])))
        defaults = json.loads((ROOT / 'example.json').read_text(encoding='utf-8'))
        validate(defaults['config'], spec['config_schema'])
        Draft202012Validator.check_schema(spec['state_schema'])
        validate(EMPTY, spec['state_schema'])

    def test_probability_one_always_hits_and_zero_never_hits(self):
        module = self.mount(config(
            event('always', probability=1, message='命中'),
            event('never', probability=0, message='不命中'),
        ))
        with patch('random.random', side_effect=AssertionError('0/1 不应消耗随机数')):
            for expected in (1, 2, 3):
                result = module.invoke_operation('draw', {'trigger': 'explore'})
                self.assertEqual([item['id'] for item in result['events']], ['always'])
                self.assertEqual(module.state['counts'], {'always': expected})
        self.assertNotIn('never', module.state['counts'])

    def test_events_are_drawn_independently_of_counts(self):
        module = self.mount(config(
            event('a', probability=0.5),
            event('b', probability=0.5),
        ))
        with patch('random.random', side_effect=[0.1, 0.9]) as draw:
            first = module.invoke_operation('draw', {'trigger': 'explore', 'context': {'who': '甲'}})
        self.assertEqual([item['id'] for item in first['events']], ['a'])
        self.assertEqual(draw.call_count, 2)
        self.assertEqual(module.state['counts'], {'a': 1})
        # a 已有 1 次命中，但下一次判定仍按固定概率 0.5 抽取，不把次数当权重。
        with patch('random.random', side_effect=[0.1, 0.1]):
            second = module.invoke_operation('draw', {'trigger': 'explore'})
        self.assertEqual([item['id'] for item in second['events']], ['a', 'b'])
        self.assertEqual(module.state['counts'], {'a': 2, 'b': 1})

    def test_miss_does_not_increment_count(self):
        module = self.mount(config(event('rare', probability=0.2)))
        with patch('random.random', return_value=0.9):
            result = module.invoke_operation('draw', {'trigger': 'explore'})
        self.assertEqual(result, {'events': []})
        self.assertEqual(module.state['counts'], {})
        with patch('random.random', return_value=0.1):
            result = module.invoke_operation('draw', {'trigger': 'explore'})
        self.assertEqual([item['id'] for item in result['events']], ['rare'])
        self.assertEqual(module.state['counts'], {'rare': 1})

    def test_trigger_filters_events_without_consuming_random(self):
        module = self.mount(config(
            event('look_only', triggers=['look'], probability=0.5),
            event('any_explore', triggers=['explore'], probability=1),
        ))
        with patch('random.random', side_effect=AssertionError('没有适用事件时不应抽随机')) as draw:
            self.assertEqual(module.invoke_operation('draw', {'trigger': 'travel'}),
                             {'events': []})
            self.assertEqual(draw.call_count, 0)
        self.assertEqual(module.state['counts'], {})

    def test_max_hits_stops_one_event_but_not_others(self):
        module = self.mount(config(
            event('twice', probability=1, max_hits=2),
            event('open', probability=1, max_hits=None),
        ))
        reports = [module.invoke_operation('draw', {'trigger': 'explore'}) for _ in range(4)]
        self.assertEqual([[item['id'] for item in report['events']] for report in reports],
                         [['twice', 'open'], ['twice', 'open'], ['open'], ['open']])
        self.assertEqual(module.state['counts'], {'twice': 2, 'open': 4})

    def test_zero_max_hits_never_draws(self):
        module = self.mount(config(event('disabled', probability=1, max_hits=0)))
        with patch('random.random', side_effect=AssertionError('达到上限不应抽随机')):
            self.assertEqual(module.invoke_operation('draw', {'trigger': 'explore'}),
                             {'events': []})
        self.assertEqual(module.state['counts'], {})

    def test_result_shape_keeps_effects_and_does_not_leak_config(self):
        effects = {'item': 'coin', 'nested': [1, 2]}
        module = self.mount(config(event('coin', effects=effects)))
        result = module.invoke_operation('draw', {'trigger': 'explore'})
        self.assertEqual(result, {'events': [
            {'id': 'coin', 'message': '消息-coin', 'effects': effects},
        ]})
        result['events'][0]['effects']['nested'].append(3)
        again = module.invoke_operation('draw', {'trigger': 'explore'})
        self.assertEqual(again['events'][0]['effects'], {'item': 'coin', 'nested': [1, 2]})
        missing = self.mount(config(event('plain')))
        self.assertIsNone(missing.invoke_operation('draw', {'trigger': 'explore'})
                          ['events'][0]['effects'])

    def test_counts_survive_json_restore_and_limit(self):
        module = self.mount(config(event('twice', probability=1, max_hits=2)))
        module.invoke_operation('draw', {'trigger': 'explore'})
        saved = json.loads(json.dumps(module.state, ensure_ascii=False))
        self.assertEqual(saved, {'counts': {'twice': 1}})
        restored = self.mount(config(event('twice', probability=1, max_hits=2)), saved)
        self.assertEqual(restored.invoke_operation('draw', {'trigger': 'explore'})
                         ['events'][0]['id'], 'twice')
        self.assertEqual(restored.invoke_operation('draw', {'trigger': 'explore'}),
                         {'events': []})
        self.assertEqual(restored.state, {'counts': {'twice': 2}})

    def test_setup_initializes_and_repairs_state(self):
        module = self.mount(state={})
        self.assertEqual(module.state, EMPTY)
        module = self.mount(state={'counts': 'bad'})
        self.assertEqual(module.state, EMPTY)
        module = self.mount(state={'counts': {'ok': 2, 'negative': -1, 'text': '3', 7: 1}})
        self.assertEqual(module.state, {'counts': {'ok': 2}})

    def test_invalid_config_fails_at_install(self):
        invalid = [
            {'events': 'no'},
            config(event('dup'), event('dup')),
            config(event('', probability=1)),
            config(event('p', probability=1.5)),
            config(event('p', probability=-0.1)),
            config(event('p', max_hits=-1)),
            config(event('p', triggers=[])),
            config(event('p', triggers=['  '])),
            config(event('p', message=None)),
        ]
        for cfg in invalid:
            with self.subTest(cfg=cfg):
                with self.assertRaises((ValidationError, ValueError)):
                    self.mount(cfg)

    def test_draw_arguments_are_validated(self):
        module = self.mount(config(event('one')))
        with self.assertRaises(ValidationError):
            module.invoke_operation('draw', {'trigger': 'explore', 'surprise': 1})
        with self.assertRaises(ValidationError):
            module.invoke_operation('draw', {})
        with self.assertRaises(ValidationError):
            module.invoke_operation('draw', {'trigger': 'explore', 'context': 'bad'})
        with self.assertRaises(ValueError):
            module.invoke_operation('unknown', {})
        with self.assertRaises(ValueError):
            module.draw('   ')
        with self.assertRaises(ValueError):
            module.draw('explore', context=[])
        # context 可以省略，也可以提供任意对象，不影响抽取结果。
        self.assertEqual(module.invoke_operation('draw', {'trigger': 'explore'})
                         ['events'][0]['id'], 'one')
        self.assertEqual(module.invoke_operation('draw', {
            'trigger': 'explore', 'context': {'anything': [1, 2]}})['events'][0]['id'], 'one')

    def test_empty_event_list_returns_empty_result(self):
        module = self.mount(config())
        self.assertEqual(module.invoke_operation('draw', {'trigger': 'explore'}),
                         {'events': []})
        self.assertEqual(module.state, EMPTY)


if __name__ == '__main__':
    unittest.main()
