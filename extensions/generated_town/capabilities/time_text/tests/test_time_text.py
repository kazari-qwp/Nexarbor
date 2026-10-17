"""时间文本组件的业务测试：未开始、推进、去重、配置、内部操作、失败与重启。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator, ValidationError, validate
from datanet.core.signals import Signal
from datanet.core.text_node import TextFileNode
from datanet.studio.contract import factory

ROOT = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(ROOT)
DEFAULT = {"slots": ["早上", "中午", "下午", "傍晚", "午夜"], "format": "第{day}天-{slot}"}
NOT_STARTED = {'tick': -1, 'last_signal_id': ''}


class BrokenNode:
    """写入直接抛错的替身节点，用来验证写入失败时状态不推进。"""

    signal_type = 'text_file'

    def __init__(self):
        self.node_id = 'time'
        self.tools = {}
        self.tool_definitions = {}
        self.expose = []

    def write(self, key, value, *, mode='upsert'):
        raise OSError('磁盘不可用')


class RejectingNode(BrokenNode):
    """写入返回 error 结果的替身节点。"""

    def write(self, key, value, *, mode='upsert'):
        return SimpleNamespace(status='error', errors=['磁盘已满'])


class TimeTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.file = self.folder / 'time.md'
        self.node = TextFileNode('time', '时间', 'text', self.file)
        self.backend = SimpleNamespace()

    def tearDown(self):
        self.temp.cleanup()

    def instance(self, config=None, state=None, node=None):
        return CREATE(self.backend, node or self.node, dict(DEFAULT if config is None else config), dict(state or {}))

    def mount(self, config=None, state=None, node=None):
        self.module = self.instance(config, state, node)
        self.module.install()
        return self.module

    def content(self):
        return self.file.read_text(encoding='utf-8')

    def pulse(self, signal_id, module=None):
        target = module or self.module
        signal = Signal('origin', ('world.tick',), 2, signal_id=signal_id)
        context = SimpleNamespace(signal=signal, delivery=SimpleNamespace(node_id='time', strength=1), network=None)
        return target.on_signal(context)

    def test_mount_waits_for_first_pulse(self):
        module = self.mount()
        self.assertEqual(module.state, NOT_STARTED)
        self.assertFalse(self.file.exists())

    def test_first_pulse_starts_at_first_moment(self):
        self.mount()
        first = self.pulse('signal-1')
        self.assertTrue(first['advanced'])
        self.assertEqual((first['day'], first['slot'], first['slot_index'], first['tick']), (1, '早上', 0, 0))
        self.assertEqual(first['text'], '第1天-早上')
        self.assertEqual(self.content(), '第1天-早上')
        second = self.pulse('signal-2')
        self.assertEqual((second['slot'], second['tick'], second['text']), ('中午', 1, '第1天-中午'))
        self.assertEqual(self.content(), '第1天-中午')

    def test_same_signal_does_not_advance_or_rewrite(self):
        module = self.mount()
        self.pulse('signal-1')
        self.file.write_text('外部改写', encoding='utf-8')
        again = self.pulse('signal-1')
        self.assertFalse(again['advanced'])
        self.assertEqual((again['tick'], again['slot']), (0, '早上'))
        self.assertEqual(module.state['tick'], 0)
        self.assertEqual(module.state['last_signal_id'], 'signal-1')
        self.assertEqual(self.content(), '外部改写')

    def test_same_content_with_new_identity_advances(self):
        self.mount()
        self.pulse('signal-1')
        self.assertTrue(self.pulse('signal-2')['advanced'])
        self.assertEqual(self.module.state['tick'], 1)

    def test_day_wraps_after_five_moments(self):
        self.mount()
        reports = [self.pulse('signal-%d' % index) for index in range(1, 7)]
        self.assertEqual((reports[4]['tick'], reports[4]['day'], reports[4]['slot']), (4, 1, '午夜'))
        self.assertEqual(reports[4]['text'], '第1天-午夜')
        self.assertEqual((reports[5]['tick'], reports[5]['day'], reports[5]['slot']), (5, 2, '早上'))
        self.assertEqual(reports[5]['text'], '第2天-早上')
        self.assertEqual(self.content(), '第2天-早上')

    def test_config_drives_day_length_and_text(self):
        self.mount({'slots': ['黎明', '正午', '黄昏'], 'format': '{slot}·第{day}天·{tick}'})
        self.assertFalse(self.file.exists())
        reports = [self.pulse('signal-%d' % index) for index in range(1, 5)]
        self.assertEqual(reports[0]['text'], '黎明·第1天·0')
        self.assertEqual((reports[3]['tick'], reports[3]['day'], reports[3]['slot']), (3, 2, '黎明'))
        self.assertEqual(self.content(), '黎明·第2天·3')

    def test_operations_read_day_and_tick(self):
        module = self.mount()
        self.assertEqual(module.invoke_operation('get_time', {}),
                         dict(day=0, slot='', slot_index=-1, tick=-1, text=''))
        self.assertEqual(module.invoke_operation('get_day', {}), {'day': 0})
        self.assertEqual(module.invoke_operation('get_tick', {}), {'tick': -1})
        self.pulse('signal-1')
        self.pulse('signal-2')
        self.assertEqual(module.invoke_operation('get_time', {}),
                         dict(day=1, slot='中午', slot_index=1, tick=1, text='第1天-中午'))
        self.assertEqual(module.invoke_operation('get_day', {}), {'day': 1})
        self.assertEqual(module.invoke_operation('get_tick', {}), {'tick': 1})
        with self.assertRaises(ValueError):
            module.invoke_operation('unknown_operation', {})
        with self.assertRaises(ValidationError):
            module.invoke_operation('get_day', {'surprise': 1})

    def test_state_restores_and_continues(self):
        self.mount()
        self.pulse('signal-1')
        self.pulse('signal-2')
        saved = json.loads(json.dumps(self.module.state, ensure_ascii=False))
        self.assertEqual(saved, {'tick': 1, 'last_signal_id': 'signal-2'})
        restored = self.instance(DEFAULT, saved)
        restored.install()
        self.assertEqual(self.content(), '第1天-中午')
        self.assertFalse(self.pulse('signal-2', module=restored)['advanced'])
        report = self.pulse('signal-3', module=restored)
        self.assertTrue(report['advanced'])
        self.assertEqual((report['tick'], report['slot'], report['text']), (2, '下午', '第1天-下午'))
        self.assertEqual(restored.state, {'tick': 2, 'last_signal_id': 'signal-3'})
        self.assertEqual(self.content(), '第1天-下午')

    def test_invalid_format_fails_at_install(self):
        with self.assertRaises(ValueError):
            self.mount({'slots': ['早上'], 'format': '{unknown}'})
        with self.assertRaises(ValueError):
            self.mount({'slots': ['早上'], 'format': '{slot} {0}'})
        with self.assertRaises(ValidationError):
            self.mount({'slots': [], 'format': '{slot}'})

    def test_write_failure_keeps_previous_time(self):
        module = self.instance(node=BrokenNode(), state={'tick': 3, 'last_signal_id': 'signal-3'})
        module.install()
        self.assertEqual(module.state, {'tick': 3, 'last_signal_id': 'signal-3'})
        with self.assertRaises(OSError):
            self.pulse('signal-4', module=module)
        self.assertEqual(module.state, {'tick': 3, 'last_signal_id': 'signal-3'})

    def test_rejected_write_reports_error_and_keeps_state(self):
        module = self.instance(node=RejectingNode(), state=NOT_STARTED)
        module.install()
        with self.assertRaises(RuntimeError) as caught:
            self.pulse('signal-1', module=module)
        self.assertIn('磁盘已满', str(caught.exception))
        self.assertEqual(module.state, NOT_STARTED)

    def test_manifest_declares_contract_surface(self):
        spec = json.loads((ROOT / 'module.json').read_text(encoding='utf-8'))
        self.assertEqual(SPEC['id'], 'time.text')
        self.assertEqual(SPEC['version'], '1.0.1')
        self.assertEqual(spec['format'], 'nexarbor-module/v1')
        self.assertEqual(spec['node_types'], ['text_file'])
        self.assertEqual(spec['signals'], ['world.tick'])
        self.assertEqual(spec['tools'], [])
        self.assertEqual([item['name'] for item in spec['operations']], ['get_time', 'get_day', 'get_tick'])
        instance = self.instance()
        for item in spec['operations']:
            Draft202012Validator.check_schema(item['parameters'])
            self.assertEqual(item['parameters']['type'], 'object')
            self.assertTrue(callable(getattr(instance, item['name'])))
        defaults = json.loads((ROOT / 'example.json').read_text(encoding='utf-8'))
        validate(defaults['config'], spec['config_schema'])
        Draft202012Validator.check_schema(spec['state_schema'])
        validate(NOT_STARTED, spec['state_schema'])
        with self.assertRaises(ValidationError):
            validate({'tick': -2, 'last_signal_id': ''}, spec['state_schema'])


if __name__ == '__main__':
    unittest.main()
