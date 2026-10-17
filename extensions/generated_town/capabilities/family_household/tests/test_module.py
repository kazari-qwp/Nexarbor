"""family.household 的业务测试：三种模式、前提拒绝、重复调用与事务回滚。"""

import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from datanet.core.access_budget import active_agent
from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.studio.contract import factory

FOLDER = Path(__file__).resolve().parents[1]


class FakeModules:
    """只实现本组件用到的依赖操作，状态可直接断言。"""

    def __init__(self, backend):
        self.backend = backend
        self.profiles = {}
        self.balances = {}
        self.ticks = {}
        self.instances = {}
        self.mounted = {}
        self.refresh_count = 0
        self.fail_update = False
        self.max_balance = 10

    def install_person(self, node_id, profile, balance=10):
        self.profiles[node_id] = deepcopy(profile)
        self.balances[node_id] = balance

    def call(self, node_id, name, operation, arguments=None):
        arguments = {} if arguments is None else arguments
        if name == 'entity.profile':
            if node_id not in self.profiles:
                raise ValueError('缺少实体资料：' + node_id)
            if operation == 'read':
                return {'profile': deepcopy(self.profiles[node_id]), 'coins': 0, 'items': {}}
            if operation == 'update_profile':
                if self.fail_update:
                    raise RuntimeError('模拟资料写入失败')
                self.profiles[node_id].update(deepcopy(arguments['fields']))
                return {'profile': deepcopy(self.profiles[node_id]), 'coins': 0, 'items': {}}
            raise ValueError('未实现的操作：' + operation)
        if name == 'action.points':
            if operation == 'get_balance':
                balance = self.balances[node_id]
                return {'ok': True, 'remaining': balance, 'max': self.max_balance, 'message': '余额'}
            if operation == 'check':
                balance = self.balances[node_id]
                return {'ok': balance >= arguments['amount'], 'remaining': balance, 'max': self.max_balance}
            if operation == 'spend':
                amount = arguments['amount']
                balance = self.balances[node_id]
                if balance < amount:
                    return {'ok': False, 'reason': 'insufficient', 'spent': 0, 'remaining': balance,
                            'max': self.max_balance, 'message': f'行动值不足：需要 {amount}，剩余 {balance}。'}
                self.balances[node_id] = balance - amount
                return {'ok': True, 'spent': amount, 'remaining': balance - amount, 'max': self.max_balance,
                        'message': '已扣除'}
            raise ValueError('未实现的操作：' + operation)
        if name == 'time.text':
            if operation == 'get_tick':
                return {'tick': self.ticks[node_id]}
            raise ValueError('未实现的操作：' + operation)
        raise ValueError('未知组件：' + name)

    def mount(self, node_id, name, config=None, state=None, bind=True):
        config = deepcopy({} if config is None else config)
        self.mounted.setdefault(node_id, []).append((name, config))
        if name == 'entity.profile':
            self.profiles[node_id] = deepcopy(config.get('profile') or {})
            self.mounted[node_id][-1] = (name, config)

    def unmount(self, node_id, name):
        entries = self.mounted.get(node_id, [])
        self.mounted[node_id] = [item for item in entries if item[0] != name]
        self.profiles.pop(node_id, None)

    def transaction(self, *node_ids):
        modules = self

        @contextmanager
        def scope():
            profiles = deepcopy(modules.profiles)
            balances = deepcopy(modules.balances)
            states = {
                key: deepcopy(instance.state)
                for key, instance in modules.instances.items()
                if not node_ids or key[0] in node_ids
            }
            try:
                yield
            except BaseException:
                modules.profiles.clear()
                modules.profiles.update(profiles)
                modules.balances.clear()
                modules.balances.update(balances)
                for key, state in states.items():
                    target = modules.instances[key].state
                    target.clear()
                    target.update(state)
                raise

        return scope()

    def refresh(self):
        self.refresh_count += 1


@contextmanager
def acting(node_id):
    token = active_agent.set((SimpleNamespace(max_signal_strength=2), node_id))
    try:
        yield
    finally:
        active_agent.reset(token)


BASE_CONFIG = {
    'mode': 'civil',
    'channels': ['family.test'],
    'place': 'place/civil',
    'presence_channel': 'presence',
    'entity_component': 'entity.profile',
    'action_component': 'action.points',
}


class ModuleCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.network = Network()
        self.modules = FakeModules(None)
        self.backend = SimpleNamespace(network=self.network, directory=self.directory, modules=self.modules)
        self.modules.backend = self.backend
        self._spec = None

    def add_node(self, node_id, name=None):
        node = Node(node_id, name or node_id, None)
        self.network.add_node(node)
        return node

    def mount(self, config, mount_id='service/node', name='业务节点'):
        node = self.add_node(mount_id, name)
        spec, create = factory(FOLDER)
        instance = create(self.backend, node, deepcopy(config), {})
        instance.install()
        self.modules.instances[(node.node_id, spec['id'])] = instance
        self._spec = spec
        return instance, node

    def assert_interfaces(self, source, target, channels, threshold=1):
        edges = [edge for edge in source.interfaces if edge.target_node_id == target]
        self.assertEqual(len(edges), 1, f'{source.node_id} -> {target} 应有一条连接')
        self.assertEqual(tuple(edges[0].metadata.channels), tuple(channels))
        self.assertEqual(edges[0].metadata.threshold, threshold)

    def add_presence(self, place_id, person_id, channel='presence', reverse=True):
        place = self.network.nodes[place_id]
        person = self.network.nodes[person_id]
        place.connect(person_id, channels=[channel], threshold=1)
        if reverse:
            person.connect(place_id, channels=[channel], threshold=1)

    def remove_presence(self, source_id, target_id, channel='presence'):
        source = self.network.nodes[source_id]
        source.interfaces[:] = [
            edge for edge in source.interfaces
            if not (edge.target_node_id == target_id and channel in edge.metadata.channels)
        ]


class CivilTests(ModuleCase):
    def setUp(self):
        super().setUp()
        self.add_node('place/civil', '民政局')
        self.add_node('place/other', '别处')
        self.add_node('npc/a', '阿岚')
        self.add_node('npc/b', '北')
        self.add_node('npc/c', '石子')
        self.instance, self.node = self.mount(dict(BASE_CONFIG))
        self.modules.install_person('npc/a', {'name': '阿岚', 'age': 20, 'gender': 'female', 'place': 'place/civil'}, 5)
        self.modules.install_person('npc/b', {'name': '北', 'age': 22, 'gender': 'male', 'place': 'place/civil'}, 5)
        self.add_presence('place/civil', 'npc/a')
        self.add_presence('place/civil', 'npc/b')

    def invoke(self, node_id, partner):
        with acting(node_id):
            return self.node.invoke_tool('register_marriage', partner=partner)

    def test_tool_set_only_exposes_current_mode(self):
        self.assertEqual(set(self.node.tool_definitions), {'register_marriage'})

    def test_both_sides_consent_then_register_without_double_charge(self):
        first = self.invoke('npc/a', 'npc/b')
        self.assertTrue(first['ok'])
        self.assertTrue(first['waiting'])
        self.assertFalse(first['registered'])
        self.assertEqual(first['charged'], 1)
        self.assertEqual(self.modules.balances['npc/a'], 4)
        self.assertEqual(self.modules.profiles['npc/a'].get('spouse'), None)

        same = self.invoke('npc/a', 'npc/b')
        self.assertTrue(same['waiting'])
        self.assertEqual(same['charged'], 0)
        self.assertEqual(self.modules.balances['npc/a'], 4)

        second = self.invoke('npc/b', 'npc/a')
        self.assertTrue(second['ok'])
        self.assertTrue(second['registered'])
        self.assertFalse(second['waiting'])
        self.assertEqual(second['charged'], 1)
        self.assertEqual(self.modules.balances['npc/b'], 4)
        self.assertEqual(self.modules.profiles['npc/a']['spouse'], 'npc/b')
        self.assertEqual(self.modules.profiles['npc/b']['spouse'], 'npc/a')
        self.assertEqual(self.instance.state['marriage_consents'], {})

        repeated = self.invoke('npc/a', 'npc/b')
        self.assertTrue(repeated['ok'])
        self.assertTrue(repeated['already'])
        self.assertEqual(repeated['charged'], 0)
        self.assertEqual(self.modules.balances['npc/a'], 4)

    def test_rejects_non_adult_wrong_place_and_existing_spouse(self):
        self.modules.profiles['npc/b']['age'] = 17
        minor = self.invoke('npc/a', 'npc/b')
        self.assertFalse(minor['ok'])
        self.assertEqual(minor['reason'], 'not_adult')
        self.assertEqual(self.modules.balances['npc/a'], 5)
        self.assertEqual(self.instance.state['marriage_consents'], {})

        self.modules.profiles['npc/b']['age'] = 22
        self.modules.profiles['npc/b']['place'] = 'place/other'
        wrong = self.invoke('npc/a', 'npc/b')
        self.assertFalse(wrong['ok'])
        self.assertEqual(wrong['reason'], 'wrong_place')
        self.assertEqual(self.modules.balances['npc/a'], 5)

        self.modules.profiles['npc/b']['place'] = 'place/civil'
        self.modules.profiles['npc/a']['spouse'] = 'npc/c'
        conflict = self.invoke('npc/a', 'npc/b')
        self.assertFalse(conflict['ok'])
        self.assertEqual(conflict['reason'], 'spouse_conflict')
        self.assertEqual(self.modules.balances['npc/a'], 5)

    def test_insufficient_action_points_does_not_record_consent(self):
        self.modules.balances['npc/a'] = 0
        rejected = self.invoke('npc/a', 'npc/b')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'insufficient')
        self.assertEqual(self.instance.state['marriage_consents'], {})
        self.assertIsNone(self.modules.profiles['npc/a'].get('spouse'))

    def test_failed_profile_write_rolls_back_action_points(self):
        self.modules.install_person('npc/a', {'name': '阿岚', 'age': 20, 'gender': 'female',
                                              'place': 'place/civil'}, 5)
        self.invoke('npc/a', 'npc/b')
        self.modules.fail_update = True
        with acting('npc/b'):
            with self.assertRaises(RuntimeError):
                self.node.invoke_tool('register_marriage', partner='npc/a')
        self.assertEqual(self.modules.balances['npc/b'], 5)
        self.assertEqual(self.modules.profiles['npc/a'].get('spouse'), None)
        self.assertEqual(self.modules.profiles['npc/b'].get('spouse'), None)
        self.assertIn('\x1f'.join(sorted(('npc/a', 'npc/b'))), self.instance.state['marriage_consents'])

    def test_forged_place_without_presence_is_rejected(self):
        self.remove_presence('npc/a', 'place/civil')
        self.remove_presence('place/civil', 'npc/a')
        rejected = self.invoke('npc/a', 'npc/b')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'not_present')
        self.assertEqual(self.modules.balances['npc/a'], 5)
        self.assertEqual(self.instance.state['marriage_consents'], {})
        self.assertIsNone(self.modules.profiles['npc/a'].get('spouse'))

    def test_missing_reverse_presence_is_rejected(self):
        self.remove_presence('npc/a', 'place/civil')
        rejected = self.invoke('npc/a', 'npc/b')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'not_present')
        self.assertEqual(self.modules.balances['npc/a'], 5)
        self.assertEqual(self.instance.state['marriage_consents'], {})

    def test_presence_rejection_keeps_pending_consent(self):
        first = self.invoke('npc/a', 'npc/b')
        self.assertTrue(first['waiting'])
        self.assertEqual(self.modules.balances['npc/a'], 4)
        key = '\x1f'.join(sorted(('npc/a', 'npc/b')))
        self.assertEqual(self.instance.state['marriage_consents'][key], ['npc/a'])

        self.remove_presence('npc/b', 'place/civil')
        rejected = self.invoke('npc/b', 'npc/a')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'not_present')
        self.assertEqual(self.modules.balances['npc/b'], 5)
        self.assertEqual(self.instance.state['marriage_consents'][key], ['npc/a'])
        self.assertIsNone(self.modules.profiles['npc/b'].get('spouse'))


FAMILY_CONFIG = {
    'mode': 'family',
    'channels': ['family.test'],
    'place': 'place/home',
    'presence_channel': 'presence',
    'entity_component': 'entity.profile',
    'action_component': 'action.points',
    'clock_node': 'clock/tick',
    'clock_component': 'time.text',
}


class FamilyTests(ModuleCase):
    def setUp(self):
        super().setUp()
        self.add_node('place/home', '家')
        self.add_node('place/other', '别处')
        self.add_node('clock/tick', '时钟')
        self.add_node('npc/wife', '阿岚')
        self.add_node('npc/husband', '北')
        self.modules.ticks['clock/tick'] = 3
        self.instance, self.node = self.mount(dict(FAMILY_CONFIG))
        self.modules.install_person('npc/wife', {'name': '阿岚', 'age': 24, 'gender': 'female',
                                                  'place': 'place/home', 'home': 'place/home',
                                                  'spouse': 'npc/husband'}, 5)
        self.modules.install_person('npc/husband', {'name': '北', 'age': 26, 'gender': 'male',
                                                    'place': 'place/home', 'home': 'place/home',
                                                    'spouse': 'npc/wife'}, 5)
        self.add_presence('place/home', 'npc/wife')
        self.add_presence('place/home', 'npc/husband')

    def invoke(self, node_id):
        with acting(node_id):
            return self.node.invoke_tool('plan_child')

    def test_tool_set_only_exposes_current_mode(self):
        self.assertEqual(set(self.node.tool_definitions), {'plan_child'})

    def test_both_consents_set_due_tick_on_female(self):
        first = self.invoke('npc/wife')
        self.assertTrue(first['ok'])
        self.assertTrue(first['waiting'])
        self.assertEqual(first['charged'], 1)
        self.assertNotIn('due_tick', self.modules.profiles['npc/wife'])

        same = self.invoke('npc/wife')
        self.assertTrue(same['waiting'])
        self.assertEqual(same['charged'], 0)

        second = self.invoke('npc/husband')
        self.assertTrue(second['ok'])
        self.assertTrue(second['planned'])
        self.assertEqual(second['due_tick'], 13)
        self.assertEqual(second['due_day'], 3)
        self.assertEqual(self.modules.profiles['npc/wife']['due_tick'], 13)
        self.assertNotIn('due_tick', self.modules.profiles['npc/husband'])
        self.assertEqual(self.modules.balances['npc/wife'], 4)
        self.assertEqual(self.modules.balances['npc/husband'], 4)
        self.assertEqual(self.instance.state['family_consents'], {})

        again = self.invoke('npc/wife')
        self.assertFalse(again['ok'])
        self.assertEqual(again['reason'], 'already_planned')
        self.assertEqual(self.modules.balances['npc/wife'], 4)

    def test_rejects_unmarried_wrong_place_and_existing_child(self):
        self.modules.profiles['npc/husband']['spouse'] = None
        unmarried = self.invoke('npc/wife')
        self.assertFalse(unmarried['ok'])
        self.assertEqual(unmarried['reason'], 'not_married')

        self.modules.profiles['npc/husband']['spouse'] = 'npc/wife'
        self.modules.profiles['npc/husband']['place'] = 'place/other'
        away = self.invoke('npc/wife')
        self.assertFalse(away['ok'])
        self.assertEqual(away['reason'], 'wrong_place')

        self.modules.profiles['npc/husband']['place'] = 'place/home'
        self.modules.profiles['npc/wife']['children'] = ['child/已有']
        parent = self.invoke('npc/wife')
        self.assertFalse(parent['ok'])
        self.assertEqual(parent['reason'], 'already_has_child')
        self.assertEqual(self.modules.balances['npc/wife'], 5)

    def test_no_female_refuses(self):
        self.modules.profiles['npc/wife']['gender'] = 'male'
        rejected = self.invoke('npc/wife')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'no_female')
        self.assertEqual(self.modules.balances['npc/wife'], 5)

    def test_other_peoples_home_is_rejected(self):
        self.modules.profiles['npc/husband']['home'] = 'place/other'
        rejected = self.invoke('npc/wife')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'wrong_home')
        self.assertEqual(self.modules.balances['npc/wife'], 5)
        self.assertEqual(self.instance.state['family_consents'], {})
        self.assertNotIn('due_tick', self.modules.profiles['npc/wife'])

    def test_forged_position_without_presence_is_rejected(self):
        self.remove_presence('npc/wife', 'place/home')
        self.remove_presence('place/home', 'npc/wife')
        rejected = self.invoke('npc/wife')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'not_present')
        self.assertEqual(self.modules.balances['npc/wife'], 5)
        self.assertEqual(self.instance.state['family_consents'], {})
        self.assertNotIn('due_tick', self.modules.profiles['npc/wife'])

    def test_missing_reverse_presence_is_rejected(self):
        self.remove_presence('npc/husband', 'place/home')
        rejected = self.invoke('npc/wife')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'not_present')
        self.assertEqual(self.modules.balances['npc/wife'], 5)
        self.assertEqual(self.instance.state['family_consents'], {})


HOSPITAL_CONFIG = {
    'mode': 'hospital',
    'channels': ['family.test'],
    'place': 'place/hospital',
    'entity_component': 'entity.profile',
    'action_component': 'action.points',
    'clock_node': 'clock/tick',
    'clock_component': 'time.text',
    'presence_channel': 'presence',
    'time_node': 'clock/tick',
    'save_node': 'save/tick',
    'adult_age': 18,
    'costs': {'give_birth': 1},
    'child_template': {
        'memory_path': 'memory/children/{node_id}.md',
        'memory_text': '',
        'description': '新生儿',
        'profile': {'role': 'child', 'hair': 'black'},
        'management_parent_id': 'npc/mother',
        'execution': {'executor': 'harness', 'strength': 2, 'max_steps': 8, 'timeout_seconds': 30},
        'modules': {
            'entity.profile': {'profile': {'age_group': 'baby', 'role': 'child'}, 'coins': 0},
        },
    },
}


class HospitalTests(ModuleCase):
    def setUp(self):
        super().setUp()
        self.add_node('place/hospital', '医院')
        self.add_node('place/other', '别处')
        self.add_node('clock/tick', '时钟')
        self.add_node('save/tick', '存档脉冲')
        self.add_node('npc/mother', '阿岚')
        self.add_node('npc/father', '北')
        self.modules.ticks['clock/tick'] = 10
        self.instance, self.node = self.mount(dict(HOSPITAL_CONFIG))
        self.modules.install_person('npc/mother', {'name': '阿岚', 'age': 24, 'gender': 'female',
                                                   'place': 'place/hospital', 'spouse': 'npc/father',
                                                   'due_tick': 10}, 5)
        self.modules.install_person('npc/father', {'name': '北', 'age': 26, 'gender': 'male',
                                                   'place': 'place/hospital', 'spouse': 'npc/mother'}, 5)
        self.add_presence('place/hospital', 'npc/mother')
        self.add_presence('place/hospital', 'npc/father')

    def invoke(self, node_id, name='小满', gender='female'):
        with acting(node_id):
            return self.node.invoke_tool('give_birth', name=name, gender=gender)

    def test_tool_set_only_exposes_current_mode(self):
        self.assertEqual(set(self.node.tool_definitions), {'give_birth'})

    def test_birth_creates_independent_child_and_wires_network(self):
        result = self.invoke('npc/mother')
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['created'])
        child_id = result['child']
        self.assertEqual(child_id, 'child/小满')
        self.assertIn(child_id, self.network.nodes)
        child = self.network.nodes[child_id]
        self.assertIsInstance(child, AgentNode)
        self.assertEqual(child.name, '小满')
        self.assertEqual(child.divergence, -1)
        self.assertEqual(child.management_parent_id, 'npc/mother')
        self.assertEqual(child.execution_binding['executor'], 'harness')

        profile = self.modules.profiles[child_id]
        self.assertEqual(profile['name'], '小满')
        self.assertEqual(profile['gender'], 'female')
        self.assertEqual(profile['age_group'], 'child')
        self.assertEqual(profile['parents'], ['npc/mother', 'npc/father'])
        self.assertEqual(profile['place'], 'place/hospital')
        self.assertEqual(profile['role'], 'child')
        self.assertEqual(profile['hair'], 'black')

        memory = self.directory / 'memory' / 'children' / 'child' / '小满.md'
        self.assertTrue(memory.exists())
        self.assertEqual(memory.read_text(encoding='utf-8'), '')

        self.assertEqual(self.modules.profiles['npc/mother']['children'], [child_id])
        self.assertEqual(self.modules.profiles['npc/father']['children'], [child_id])
        self.assertIsNone(self.modules.profiles['npc/mother'].get('due_tick'))
        self.assertEqual(self.modules.balances['npc/mother'], 4)

        self.assert_interfaces(self.network.nodes['clock/tick'], child_id, ('world.tick',))
        self.assert_interfaces(child, 'save/tick', ('world.tick',))
        self.assert_interfaces(self.network.nodes['place/hospital'], child_id, ('presence',))
        self.assert_interfaces(child, 'place/hospital', ('presence',))
        self.assertEqual(self.modules.mounted[child_id][0][0], 'entity.profile')
        self.assertEqual(self.modules.refresh_count, 1)

        before = len(self.network.nodes)
        repeated = self.invoke('npc/mother', name='另一个名字')
        self.assertTrue(repeated['ok'])
        self.assertFalse(repeated['created'])
        self.assertTrue(repeated['already'])
        self.assertEqual(repeated['child'], child_id)
        self.assertEqual(repeated['charged'], 0)
        self.assertEqual(len(self.network.nodes), before)
        self.assertEqual(self.modules.balances['npc/mother'], 4)

    def test_refuses_not_due_and_wrong_place(self):
        self.modules.profiles['npc/mother']['due_tick'] = 11
        early = self.invoke('npc/mother')
        self.assertFalse(early['ok'])
        self.assertEqual(early['reason'], 'not_due')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertEqual(self.modules.balances['npc/mother'], 5)

        self.modules.profiles['npc/mother']['due_tick'] = 10
        self.modules.profiles['npc/mother']['place'] = 'place/other'
        away = self.invoke('npc/mother')
        self.assertFalse(away['ok'])
        self.assertEqual(away['reason'], 'wrong_place')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertEqual(self.modules.balances['npc/mother'], 5)

    def test_presence_must_be_real_and_bidirectional(self):
        self.remove_presence('npc/mother', 'place/hospital')
        self.remove_presence('place/hospital', 'npc/mother')
        forged = self.invoke('npc/mother')
        self.assertFalse(forged['ok'])
        self.assertEqual(forged['reason'], 'not_present')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertEqual(self.modules.balances['npc/mother'], 5)

        self.add_presence('place/hospital', 'npc/mother')
        self.remove_presence('npc/mother', 'place/hospital')
        reverse = self.invoke('npc/mother')
        self.assertFalse(reverse['ok'])
        self.assertEqual(reverse['reason'], 'not_present')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertEqual(self.modules.balances['npc/mother'], 5)
        self.assertIsNotNone(self.modules.profiles['npc/mother'].get('due_tick'))
        self.assertNotIn('children', self.modules.profiles['npc/mother'])

    def test_no_due_and_no_spouse_are_explicit(self):
        self.modules.profiles['npc/mother']['due_tick'] = None
        no_due = self.invoke('npc/mother')
        self.assertFalse(no_due['ok'])
        self.assertEqual(no_due['reason'], 'no_due')

        self.modules.profiles['npc/mother']['due_tick'] = 10
        self.modules.profiles['npc/father']['spouse'] = None
        unmarried = self.invoke('npc/mother')
        self.assertFalse(unmarried['ok'])
        self.assertEqual(unmarried['reason'], 'not_married')

    def test_insufficient_action_points_does_not_create_child(self):
        self.modules.balances['npc/mother'] = 0
        rejected = self.invoke('npc/mother')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'insufficient')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertNotIn('child/小满', self.modules.profiles)
        self.assertFalse((self.directory / 'memory' / 'children' / 'child' / '小满.md').exists())
        self.assertEqual(self.modules.balances['npc/mother'], 0)

    def test_profile_write_failure_removes_child_and_keeps_action_points(self):
        self.modules.fail_update = True
        rejected = self.invoke('npc/mother')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['reason'], 'birth_failed')
        self.assertNotIn('child/小满', self.network.nodes)
        self.assertNotIn('child/小满', self.modules.profiles)
        self.assertFalse((self.directory / 'memory' / 'children' / 'child' / '小满.md').exists())
        self.assertEqual(self.modules.balances['npc/mother'], 5)


class ConsentPersistenceTests(ModuleCase):
    def test_pending_consent_survives_module_reinstall(self):
        self.add_node('place/home', '家')
        self.add_node('clock/tick', '时钟')
        self.add_node('npc/wife', '阿岚')
        self.add_node('npc/husband', '北')
        self.modules.ticks['clock/tick'] = 1
        instance, node = self.mount(dict(FAMILY_CONFIG), mount_id='service/one', name='业务一')
        self.modules.install_person('npc/wife', {'name': '阿岚', 'age': 24, 'gender': 'female',
                                                  'place': 'place/home', 'home': 'place/home',
                                                  'spouse': 'npc/husband'}, 5)
        self.modules.install_person('npc/husband', {'name': '北', 'age': 26, 'gender': 'male',
                                                    'place': 'place/home', 'home': 'place/home',
                                                    'spouse': 'npc/wife'}, 5)
        self.add_presence('place/home', 'npc/wife')
        self.add_presence('place/home', 'npc/husband')
        with acting('npc/wife'):
            first = node.invoke_tool('plan_child')
        self.assertTrue(first['waiting'], first)

        saved = deepcopy(instance.state)
        node2 = self.add_node('service/two', '业务二')
        spec, create = factory(FOLDER)
        rebuilt = create(self.backend, node2, dict(FAMILY_CONFIG), saved)
        rebuilt.install()
        self.modules.instances[(node2.node_id, spec['id'])] = rebuilt
        with acting('npc/husband'):
            second = node2.invoke_tool('plan_child')
        self.assertTrue(second['planned'], second)
        self.assertEqual(self.modules.profiles['npc/wife']['due_tick'], 11)


if __name__ == '__main__':
    unittest.main()
