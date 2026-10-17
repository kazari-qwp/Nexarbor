"""Behaviour tests for the entity.profile component."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from datanet.core.network import Network
from datanet.core.node import Node

FOLDER = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((FOLDER / 'module.json').read_text(encoding='utf-8'))


def load_module():
    spec = importlib.util.spec_from_file_location('entity_profile_under_test', FOLDER / 'module.py', submodule_search_locations=[str(FOLDER)])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()
STATE = Draft202012Validator(MANIFEST['state_schema'])


class EntityProfileTest(unittest.TestCase):
    def setUp(self):
        self.network = Network()
        self.instances = []

    def tearDown(self):
        for instance in reversed(self.instances):
            instance.close()

    def mount(self, node_id='hero', config=None, state=None):
        node = Node(node_id, node_id.title(), None)
        self.network.add_node(node)
        backend = SimpleNamespace(network=self.network, metadata_registry=self.network.metadata_registry,
                                  directory=FOLDER, dispatch=lambda *a, **k: {'saved': True})
        instance = MODULE.Module(backend, node, {} if config is None else copy.deepcopy(config),
                                 {} if state is None else copy.deepcopy(state))
        instance.manifest = copy.deepcopy(MANIFEST)
        instance.install()
        self.instances.append(instance)
        self.check(instance)
        return instance, node

    def check(self, instance):
        STATE.validate(instance.state)
        json.dumps(instance.state, ensure_ascii=False)

    def call(self, instance, operation, arguments=None):
        value = instance.invoke_operation(operation, {} if arguments is None else arguments)
        self.check(instance)
        return value

    def test_install_seeds_state_and_tool(self):
        instance, node = self.mount(config=dict(profile={'name': '阿岚', 'role': '旅人'}, coins=24, items={'面包': 2}))
        self.assertEqual(instance.state, {'profile': {'name': '阿岚', 'role': '旅人'}, 'coins': 24, 'items': {'面包': 2}})
        self.assertEqual(self.call(instance, 'read'),
                         {'profile': {'name': '阿岚', 'role': '旅人'}, 'coins': 24, 'items': {'面包': 2}})
        self.assertEqual(set(node.tool_definitions), {'entity_view'})
        self.assertEqual(node.tool_definitions['entity_view']['access_channels'], ['access.read'])

    def test_empty_config_starts_empty(self):
        instance, _ = self.mount(config={})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 0, 'items': {}})
        self.assertEqual(self.call(instance, 'read'), {'profile': {}, 'coins': 0, 'items': {}})

    def test_tool_only_reads(self):
        instance, node = self.mount(config=dict(profile={'name': '阿岚'}, coins=5, items={'面包': 1}))
        value = node.tools['entity_view']()
        self.assertEqual(value, {'profile': {'name': '阿岚'}, 'coins': 5, 'items': {'面包': 1}})
        self.check(instance)
        self.assertEqual(instance.state['coins'], 5)

    def test_snapshot_is_detached(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚'}, coins=5, items={'面包': 1}))
        value = self.call(instance, 'read')
        value['profile']['name'] = '篡改'
        value['items']['面包'] = 99
        value['coins'] = 1000
        self.assertEqual(instance.state, {'profile': {'name': '阿岚'}, 'coins': 5, 'items': {'面包': 1}})

    def test_update_profile_merges_fields(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚', 'role': '旅人'}))
        value = self.call(instance, 'update_profile', {'fields': {'role': '铁匠', 'mood': '平静'}})
        self.assertEqual(value['profile'], {'name': '阿岚', 'role': '铁匠', 'mood': '平静'})
        self.assertEqual(instance.state['profile'], {'name': '阿岚', 'role': '铁匠', 'mood': '平静'})
        self.call(instance, 'update_profile', {'fields': {'mood': '愉快'}})
        self.assertEqual(instance.state['profile']['mood'], '愉快')
        self.assertEqual(instance.state['profile']['role'], '铁匠')

    def test_update_profile_rejects_non_json_and_keeps_state(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚'}))
        with self.assertRaises(ValueError):
            self.call(instance, 'update_profile', {'fields': {'note': object()}})
        with self.assertRaises(ValueError):
            self.call(instance, 'update_profile', {'fields': {1: '数字键'}})
        self.assertEqual(instance.state['profile'], {'name': '阿岚'})

    def test_adjust_applies_every_change(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚'}, coins=10, items={'面包': 1}))
        value = self.call(instance, 'adjust', {'coins': -4, 'items': {'面包': -1, '火把': 2}, 'fields': {'mood': '疲倦'}})
        self.assertEqual(instance.state, {'profile': {'name': '阿岚', 'mood': '疲倦'}, 'coins': 6, 'items': {'火把': 2}})
        self.assertEqual(value, {'profile': {'name': '阿岚', 'mood': '疲倦'}, 'coins': 6, 'items': {'火把': 2}})

    def test_adjust_removes_zero_quantity(self):
        instance, _ = self.mount(config=dict(items={'面包': 2}))
        self.call(instance, 'adjust', {'items': {'面包': -2}})
        self.assertEqual(instance.state['items'], {})

    def test_adjust_accepts_new_item(self):
        instance, _ = self.mount(config=dict(items={}))
        self.call(instance, 'adjust', {'items': {'矿石': 3}})
        self.assertEqual(instance.state['items'], {'矿石': 3})

    def test_adjust_is_atomic_when_items_are_short(self):
        instance, _ = self.mount(config=dict(coins=10, items={'面包': 1}))
        with self.assertRaises(ValueError):
            self.call(instance, 'adjust', {'coins': -5, 'items': {'面包': -2}})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 10, 'items': {'面包': 1}})

    def test_adjust_is_atomic_when_unknown_item_is_short(self):
        instance, _ = self.mount(config=dict(coins=10, items={'面包': 1}))
        with self.assertRaises(ValueError):
            self.call(instance, 'adjust', {'coins': 5, 'items': {'矿石': -1}})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 10, 'items': {'面包': 1}})

    def test_adjust_rejects_negative_balance(self):
        instance, _ = self.mount(config=dict(coins=3, items={'面包': 2}))
        with self.assertRaises(ValueError):
            self.call(instance, 'adjust', {'coins': -4})
        self.assertEqual(instance.state['coins'], 3)
        self.call(instance, 'adjust', {'coins': -3, 'items': {'面包': 2}})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 0, 'items': {'面包': 4}})

    def test_adjust_argument_types_are_checked(self):
        instance, _ = self.mount(config=dict(coins=3))
        for arguments in ({'coins': 1.5}, {'coins': True}, {'items': {'面包': 1.5}}, {'items': {'面包': True}}):
            with self.assertRaises(ValidationError):
                self.call(instance, 'adjust', arguments)
        with self.assertRaises(ValueError):
            self.call(instance, 'adjust', {'items': {'': 1}})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 3, 'items': {}})

    def test_repeated_calls_accumulate(self):
        instance, _ = self.mount(config=dict(coins=5))
        for _ in range(3):
            self.call(instance, 'adjust', {'coins': -1, 'items': {'面包': 1}})
        self.assertEqual(instance.state, {'profile': {}, 'coins': 2, 'items': {'面包': 3}})

    def test_unknown_operation_is_rejected(self):
        instance, _ = self.mount(config={})
        with self.assertRaises(ValueError):
            instance.invoke_operation('grant', {})

    def test_saved_state_wins_over_config(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚'}, coins=10, items={'面包': 1}))
        self.call(instance, 'adjust', {'coins': 5, 'items': {'面包': 1}})
        saved = json.loads(json.dumps(instance.state, ensure_ascii=False))
        instance.close()
        other, _ = self.mount(node_id='other', config=dict(profile={'name': '新名'}, coins=999, items={'面包': 50}),
                              state=saved)
        self.assertEqual(other.state, {'profile': {'name': '阿岚'}, 'coins': 15, 'items': {'面包': 2}})
        self.call(other, 'adjust', {'coins': -15})
        self.assertEqual(other.state['coins'], 0)

    def test_invalid_config_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.mount(config={'coins': -1})
        with self.assertRaises(ValidationError):
            self.mount(node_id='other', config={'items': {'面包': -2}})
        with self.assertRaises(ValidationError):
            self.mount(node_id='third', config={'metadata_namespace': ''})

    def test_metadata_publishes_profile_only(self):
        instance, _ = self.mount(config=dict(profile={'name': '阿岚', 'role': '旅人'}, coins=7, items={'面包': 2}))
        metadata = self.network.get_metadata('hero')
        self.assertEqual(metadata['extensions']['profile'], {'name': '阿岚', 'role': '旅人'})
        self.assertNotIn('coins', metadata['extensions']['profile'])
        self.assertNotIn('items', metadata['extensions']['profile'])
        self.call(instance, 'update_profile', {'fields': {'role': '铁匠'}})
        self.assertEqual(self.network.get_metadata('hero')['extensions']['profile']['role'], '铁匠')
        instance.close()
        self.assertNotIn('profile', self.network.get_metadata('hero').get('extensions', {}))

    def test_custom_metadata_namespace(self):
        self.mount(config=dict(profile={'name': '阿岚'}, metadata_namespace='sheet'))
        self.assertEqual(self.network.get_metadata('hero')['extensions']['sheet'], {'name': '阿岚'})

    def test_two_instances_keep_separate_metadata(self):
        first, _ = self.mount(config=dict(profile={'name': '甲'}))
        self.mount(node_id='other', config=dict(profile={'name': '乙'}))
        self.assertEqual(self.network.get_metadata('hero')['extensions']['profile'], {'name': '甲'})
        self.assertEqual(self.network.get_metadata('other')['extensions']['profile'], {'name': '乙'})
        first.close()
        self.assertEqual(self.network.get_metadata('other')['extensions']['profile'], {'name': '乙'})

    def test_empty_profile_publishes_nothing(self):
        self.mount(config={})
        self.assertNotIn('profile', self.network.get_metadata('hero').get('extensions', {}))


if __name__ == '__main__':
    unittest.main()
