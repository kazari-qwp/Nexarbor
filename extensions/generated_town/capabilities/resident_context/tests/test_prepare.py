import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.studio.contract import factory

ROOT = Path(__file__).resolve().parents[1]
SPEC, CREATE = factory(ROOT)


class Stub:
    def __init__(self, **operations):
        self.operations = operations

    def invoke_operation(self, name, arguments):
        return self.operations[name]({})


class StubModules:
    def __init__(self, instances):
        self.instances = instances

    def call(self, node_id, name, operation, arguments=None):
        return self.instances[(node_id, name)].invoke_operation(operation, arguments or {})


class ResidentContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'persona.md').write_text('你是铁匠阿岚，说话直接。', encoding='utf-8')
        (self.root / 'common.md').write_text('这个小镇没有魔法。', encoding='utf-8')
        (self.root / 'map.md').write_text('广场在中心，北边是磨坊。', encoding='utf-8')

        self.network = Network()
        self.agent = self.agent_node('npc/a', '阿岚')
        self.place = self.place_node('place/square', '广场', '中央广场')
        self.mill = self.place_node('place/mill', '磨坊')
        self.inn = self.place_node('place/inn', '旅店')
        self.place.connect(self.mill.node_id, channels=['place.road'], threshold=1)
        self.inn.connect(self.place.node_id, channels=['place.road'], threshold=1)

        self.other = self.agent_node('npc/b', '北')
        self.other2 = self.agent_node('npc/c', '石子')
        self.chat_only = self.agent_node('npc/d', '路人')
        self.far = self.agent_node('npc/far', '米')
        self.place.connect(self.other.node_id, channels=['place.presence'], threshold=1)
        self.other2.connect(self.place.node_id, channels=['place.presence'], threshold=1)
        self.place.connect(self.chat_only.node_id, channels=['chat.local'], threshold=1)

        self.entity = {
            'profile': {
                'name': '阿岚',
                'gender': '女',
                'occupation': '铁匠',
                'place': self.place.node_id,
            },
            'coins': 12,
            'items': {'面包': 2},
        }
        # 远处人物即使自己写着同一地点，也不应靠资料被算作同场。
        self.people_profiles = {
            self.other.node_id: {'name': '北', 'gender': '男', 'occupation': '旅人', 'place': self.place.node_id},
            self.other2.node_id: {'name': '石子', 'gender': '女', 'occupation': '学徒', 'place': self.place.node_id},
            self.far.node_id: {'name': '米', 'gender': '女', 'occupation': '农夫', 'place': self.place.node_id},
        }
        self.remaining = 7
        self.maximum = 10
        self.clock = {'day': 2, 'slot': '中午', 'slot_index': 1, 'tick': 6, 'text': '第2天-中午'}

    def tearDown(self):
        for name in list(self.network.nodes):
            self.network.nodes.pop(name)

    def agent_node(self, node_id, name):
        node = AgentNode(node_id, name, file_path=self.root / (node_id.replace('/', '-') + '.md'))
        self.network.add_node(node)
        return node

    def place_node(self, node_id, name, description=''):
        node = Node(node_id, name, None, description=description)
        self.network.add_node(node)
        return node

    def config(self, **overrides):
        config = {
            'entity_component': 'entity.profile',
            'action_component': 'action.points',
            'clock_node': 'town/clock',
            'clock_component': 'time.text',
            'persona_file': 'persona.md',
            'common_sense_file': 'common.md',
            'map_file': 'map.md',
            'opening_line': '你醒来了。',
            'road_channels': ['place.road'],
            'presence_channels': ['place.presence'],
        }
        config.update(overrides)
        return config

    def build(self, config=None, state=None):
        instances = {
            (self.agent.node_id, 'entity.profile'): Stub(read=lambda _: self.entity),
            (self.agent.node_id, 'action.points'): Stub(
                get_balance=lambda _: {'ok': True, 'remaining': self.remaining, 'max': self.maximum}
            ),
            ('town/clock', 'time.text'): Stub(get_time=lambda _: self.clock),
        }
        for node_id, profile in self.people_profiles.items():
            instances[(node_id, 'entity.profile')] = Stub(
                read=lambda _, profile=profile: {'profile': profile, 'coins': 0, 'items': {}}
            )
        backend = SimpleNamespace(network=self.network, directory=self.root, modules=StubModules(instances))
        instance = CREATE(backend, self.agent, config or self.config(), {} if state is None else state)
        instance.install()
        return instance, backend

    @staticmethod
    def source(node):
        return node.inputs.snapshot()['resident.context']

    @staticmethod
    def tail(node):
        return '\n'.join(ResidentContextTest.source(node)['tail'])

    def test_prepare_fills_four_surfaces_from_live_state(self):
        instance, _ = self.build()
        result = instance.prepare()

        source = self.source(self.agent)
        self.assertIn('你是铁匠阿岚', source['system_prompt'])
        self.assertIn('这个小镇没有魔法', source['system_prompt'])
        self.assertEqual(source['context'], [{'id': 'map', 'text': '广场在中心，北边是磨坊。'}])
        self.assertEqual(len(source['inputs']), 1)
        self.assertEqual(source['inputs'][0]['id'], 'opening')
        self.assertEqual(source['inputs'][0]['text'], '你醒来了。')
        self.assertTrue(instance.state['opening_delivered'])
        self.assertTrue(result['delivered_opening'])

        tail = self.tail(self.agent)
        for expected in [
            '当前时间：第2天-中午',
            '自身资料：gender=女；name=阿岚；occupation=铁匠',
            '金币：12',
            '物品：面包×2',
            '行动余额：7/10',
            '本地场所：广场（中央广场）',
            '同场人物：北（男，旅人）；石子（女，学徒）',
            '相邻地点：旅店、磨坊',
        ]:
            self.assertIn(expected, tail)
        self.assertNotIn('米', tail)
        self.assertNotIn('路人', tail)
        self.assertNotIn('远山', tail)

    def test_reload_skips_opening_and_recomputes_tail(self):
        instance, _ = self.build()
        instance.prepare()
        harbor = self.place_node('place/harbor', '港口')
        harbor.connect(self.mill.node_id, channels=['place.road'], threshold=1)
        self.entity['profile']['place'] = harbor.node_id
        (self.root / 'persona.md').write_text('你换了一份人格。', encoding='utf-8')
        (self.root / 'map.md').write_text('新的地图。', encoding='utf-8')

        instance.prepare()
        source = self.source(self.agent)
        self.assertEqual(len(source['inputs']), 1)
        self.assertIn('你换了一份人格', source['system_prompt'])
        self.assertEqual(source['context'], [{'id': 'map', 'text': '新的地图。'}])
        tail = self.tail(self.agent)
        self.assertIn('本地场所：港口', tail)
        self.assertIn('相邻地点：磨坊', tail)
        self.assertNotIn('广场', tail)
        self.assertNotIn('北', tail)

    def test_saved_opening_flag_suppresses_opening_on_load(self):
        instance, _ = self.build(state={'opening_delivered': True})
        instance.prepare()
        source = self.source(self.agent)
        self.assertEqual(source['inputs'], [])
        self.assertTrue(instance.state['opening_delivered'])

    def test_empty_opening_is_never_delivered_but_is_marked(self):
        instance, _ = self.build(config=self.config(opening_line=''))
        result = instance.prepare()
        self.assertEqual(self.source(self.agent)['inputs'], [])
        self.assertTrue(instance.state['opening_delivered'])
        self.assertFalse(result['delivered_opening'])

    def test_unreadable_file_raises_without_touching_inputs(self):
        instance, _ = self.build()
        (self.root / 'common.md').unlink()
        with self.assertRaisesRegex(ValueError, '常识文件读取失败'):
            instance.prepare()
        self.assertFalse(instance.state['opening_delivered'])
        self.assertEqual(self.agent.inputs.snapshot(), {})

        (self.root / 'common.md').write_text('恢复的常识。', encoding='utf-8')
        instance.prepare()
        self.assertIn('恢复的常识', self.source(self.agent)['system_prompt'])

    def test_missing_place_raises_clear_error(self):
        instance, _ = self.build()
        self.entity['profile'].pop('place')
        with self.assertRaisesRegex(ValueError, 'profile.place'):
            instance.prepare()
        self.assertFalse(instance.state['opening_delivered'])
        self.assertEqual(self.agent.inputs.snapshot(), {})

    def test_missing_entity_component_raises_clear_error(self):
        instance, backend = self.build()
        backend.modules.instances.pop((self.agent.node_id, 'entity.profile'))
        with self.assertRaisesRegex(ValueError, '实体资料组件不可用'):
            instance.prepare()
        self.assertEqual(self.agent.inputs.snapshot(), {})


if __name__ == '__main__':
    unittest.main()
