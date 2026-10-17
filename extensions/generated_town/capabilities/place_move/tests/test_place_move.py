"""place.move 的业务测试：移动成功、拒绝条件、频道迁移、到达事件与事务回滚。"""
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from datanet.core.access_budget import active_agent
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.studio.contract import factory

FOLDER = Path(__file__).resolve().parents[1]
CONFIG = json.loads((FOLDER / 'example.json').read_text(encoding='utf-8'))['config']
BASE_CONFIG = {key: value for key, value in CONFIG.items() if key != 'events_ref'}
SPEC, CREATE = factory(FOLDER)


class FakeModules:
    """最小可信组件替身：entity.profile、action.points 与 chance.events 的公开操作。"""

    def __init__(self):
        self.profiles = {}
        self.balances = {}
        self.counts = {}
        self.draw_result = {'events': []}
        self.draw_calls = []
        self.adjust_calls = []
        self.fail_profile_update = False
        self.fail_adjust = False
        self.fail_draw = False

    def seed(self, node_id, profile, balance):
        self.profiles[node_id] = {'profile': deepcopy(profile), 'coins': 0, 'items': {}}
        self.balances[node_id] = balance

    def call(self, node_id, name, operation, arguments=None):
        arguments = {} if arguments is None else arguments
        if name == 'entity.profile':
            state = self.profiles[node_id]
            if operation == 'read':
                return deepcopy(state)
            if operation == 'update_profile':
                if self.fail_profile_update:
                    raise RuntimeError('profile update failed')
                state['profile'].update(deepcopy(arguments['fields']))
                return deepcopy(state)
            if operation == 'adjust':
                if self.fail_adjust:
                    raise ValueError('实体调整失败')
                coins = arguments.get('coins')
                items = arguments.get('items') or {}
                fields = arguments.get('fields')
                if coins is not None and state['coins'] + coins < 0:
                    raise ValueError('金币不足')
                for item, delta in items.items():
                    if state['items'].get(item, 0) + delta < 0:
                        raise ValueError('物品不足')
                if coins is not None:
                    state['coins'] += coins
                for item, delta in items.items():
                    count = state['items'].get(item, 0) + delta
                    if count:
                        state['items'][item] = count
                    else:
                        state['items'].pop(item, None)
                if fields:
                    state['profile'].update(deepcopy(fields))
                self.adjust_calls.append((node_id, deepcopy(arguments)))
                return deepcopy(state)
        elif name == 'action.points':
            balance = self.balances[node_id]
            if operation == 'get_balance':
                return {'ok': True, 'remaining': balance, 'max': 10, 'message': ''}
            if operation == 'check':
                amount = arguments['amount']
                return {'ok': balance >= amount, 'amount': amount, 'remaining': balance, 'max': 10, 'message': ''}
            if operation == 'spend':
                amount = arguments['amount']
                if balance < amount:
                    return {'ok': False, 'reason': 'insufficient', 'amount': amount, 'spent': 0,
                            'remaining': balance, 'max': 10, 'message': '行动值不足。'}
                self.balances[node_id] = balance - amount
                return {'ok': True, 'amount': amount, 'spent': amount,
                        'remaining': balance - amount, 'max': 10, 'message': ''}
        elif name == 'chance.events':
            if self.fail_draw:
                raise KeyError((node_id, name))
            self.draw_calls.append((node_id, deepcopy(arguments)))
            events = deepcopy(self.draw_result.get('events', []))
            for event in events:
                self.counts[event['id']] = self.counts.get(event['id'], 0) + 1
            return {'events': events}
        raise KeyError((node_id, name))

    @contextmanager
    def transaction(self, *node_ids):
        profiles = deepcopy(self.profiles)
        balances = deepcopy(self.balances)
        counts = deepcopy(self.counts)
        try:
            yield
        except BaseException:
            self.profiles = profiles
            self.balances = balances
            self.counts = counts
            raise


class MoveHereTest(unittest.TestCase):
    def setUp(self):
        self.network = Network()
        self.here = Node('place/square', '中央广场', None)
        self.market = Node('place/market', '集市', None)
        self.agent = Node('npc/alan', '阿岚', None)
        for node in (self.here, self.market, self.agent):
            self.network.add_node(node)
        self.presence = BASE_CONFIG['presence_channel']
        self.market.connect(self.here.node_id, channels=['road'], threshold=1)
        self.here.connect(self.market.node_id, channels=['road'], threshold=1)
        self.market.connect(self.agent.node_id, channels=[self.presence, 'pulse'], threshold=1)
        self.agent.connect(self.market.node_id, channels=[self.presence, 'pulse'], threshold=1)
        self.here.connect(self.agent.node_id, channels=['pulse'], threshold=1)
        self.modules = FakeModules()
        self.modules.seed(self.agent.node_id, {'name': '阿岚', 'place': self.market.node_id}, 10)
        self.backend = SimpleNamespace(network=self.network, modules=self.modules, directory=FOLDER)
        self.instance = CREATE(self.backend, self.here, BASE_CONFIG, {})
        self.instance.install()

    def tearDown(self):
        self.instance.close()

    def move(self):
        return self.move_at(self.here)

    def move_at(self, node):
        token = active_agent.set((SimpleNamespace(max_signal_strength=3), self.agent.node_id))
        try:
            return node.invoke_tool('move_here')
        finally:
            active_agent.reset(token)

    def install_arrival(self):
        events_node = Node('events/dock', '码头事件', None)
        self.network.add_node(events_node)
        dock = Node('place/dock', '码头', None)
        self.network.add_node(dock)
        dock.connect(self.market.node_id, channels=['road'], threshold=1)
        self.market.connect(dock.node_id, channels=['road'], threshold=1)
        config = dict(CONFIG)
        config['place_name'] = '码头'
        config['events_ref'] = {'node': events_node.node_id, 'module': 'chance.events'}
        instance = CREATE(self.backend, dock, config, {})
        instance.install()
        self.addCleanup(instance.close)
        return dock

    def edge_channels(self, source, target_id):
        return [edge.metadata.channels for edge in source.interfaces if edge.target_node_id == target_id]

    def profile_place(self):
        return self.modules.profiles[self.agent.node_id]['profile'].get('place')

    def test_move_here_migrates_presence_and_charges(self):
        result = self.move()
        self.assertTrue(result['ok'])
        self.assertTrue(result['moved'])
        self.assertEqual(result['place'], self.here.node_id)
        self.assertEqual(result['place_name'], '中央广场')
        self.assertEqual(result['cost'], 3)
        self.assertEqual(result['remaining'], 7)
        self.assertIn('中央广场', result['message'])
        self.assertIn('集市', result['message'])
        self.assertNotIn('events', result)
        self.assertEqual(self.modules.draw_calls, [])
        self.assertEqual(self.profile_place(), self.here.node_id)
        self.assertEqual(self.modules.balances[self.agent.node_id], 7)
        # 旧地点：只去掉在场频道，脉冲频道保留。
        self.assertEqual(self.edge_channels(self.market, self.agent.node_id), [('pulse',)])
        self.assertEqual(self.edge_channels(self.agent, self.market.node_id), [('pulse',)])
        # 新地点：双向在场连接，门槛 1，且不覆盖既有脉冲频道。
        here_edges = [edge for edge in self.here.interfaces if edge.target_node_id == self.agent.node_id]
        self.assertEqual(len(here_edges), 1)
        self.assertEqual(set(here_edges[0].metadata.channels), {'pulse', self.presence})
        self.assertEqual(here_edges[0].metadata.threshold, 1)
        agent_edges = [edge for edge in self.agent.interfaces if edge.target_node_id == self.here.node_id]
        self.assertEqual(len(agent_edges), 1)
        self.assertEqual(agent_edges[0].metadata.channels, (self.presence,))
        self.assertEqual(agent_edges[0].metadata.threshold, 1)
        # 节点散度与道路保持原样。
        self.assertEqual(self.here.divergence, -1)
        self.assertEqual(self.market.divergence, -1)
        for source, other in ((self.here, self.market), (self.market, self.here)):
            road = next(edge for edge in source.interfaces if edge.target_node_id == other.node_id)
            self.assertEqual(road.metadata.channels, ('road',))
            self.assertEqual(road.metadata.threshold, 1)

    def test_already_here_does_not_move_or_charge(self):
        self.modules.profiles[self.agent.node_id]['profile']['place'] = self.here.node_id
        result = self.move()
        self.assertTrue(result['ok'])
        self.assertFalse(result['moved'])
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['remaining'], 10)
        self.assertIn('已经', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), self.here.node_id)
        self.assertEqual(set(self.edge_channels(self.market, self.agent.node_id)[0]), {self.presence, 'pulse'})

    def test_place_without_direct_road_is_rejected(self):
        hill = Node('place/hill', '山丘', None)
        self.network.add_node(hill)
        self.modules.profiles[self.agent.node_id]['profile']['place'] = hill.node_id
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertEqual(result['cost'], 0)
        self.assertIn('道路', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), hill.node_id)

    def test_connection_without_road_channel_is_not_a_road(self):
        self.here.interfaces[:] = [edge for edge in self.here.interfaces if edge.target_node_id != self.market.node_id]
        self.market.interfaces[:] = [edge for edge in self.market.interfaces if edge.target_node_id != self.here.node_id]
        self.here.connect(self.market.node_id, channels=['footpath'], threshold=1)
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertEqual(result['remaining'], 10)
        self.assertEqual(self.profile_place(), self.market.node_id)

    def test_insufficient_points_block_move(self):
        self.modules.balances[self.agent.node_id] = 2
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['remaining'], 2)
        self.assertIn('行动值不足', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 2)
        self.assertEqual(self.profile_place(), self.market.node_id)
        self.assertEqual(set(self.edge_channels(self.market, self.agent.node_id)[0]), {self.presence, 'pulse'})
        self.assertEqual(self.edge_channels(self.here, self.agent.node_id), [('pulse',)])

    def test_missing_place_field_is_rejected(self):
        del self.modules.profiles[self.agent.node_id]['profile']['place']
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertIn('profile.place', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)

    def test_unknown_place_is_rejected(self):
        self.modules.profiles[self.agent.node_id]['profile']['place'] = 'place/ghost'
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertIn('不在网络', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)

    def test_missing_agent_identity_is_rejected(self):
        result = self.here.invoke_tool('move_here')
        self.assertFalse(result['ok'])
        self.assertIn('身份', result['message'])

    def test_repeated_move_does_not_charge_twice(self):
        self.assertTrue(self.move()['moved'])
        second = self.move()
        self.assertTrue(second['ok'])
        self.assertFalse(second['moved'])
        self.assertEqual(second['cost'], 0)
        self.assertEqual(second['remaining'], 7)
        self.assertEqual(self.modules.balances[self.agent.node_id], 7)
        self.assertEqual(self.profile_place(), self.here.node_id)
        self.assertEqual(len([edge for edge in self.here.interfaces if edge.target_node_id == self.agent.node_id]), 1)
        self.assertEqual(len([edge for edge in self.agent.interfaces if edge.target_node_id == self.here.node_id]), 1)

    def test_failure_rolls_back_spend(self):
        self.modules.fail_profile_update = True
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertIn('未完成', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), self.market.node_id)
        self.assertEqual(set(self.edge_channels(self.market, self.agent.node_id)[0]), {self.presence, 'pulse'})
        self.assertEqual(self.edge_channels(self.here, self.agent.node_id), [('pulse',)])

    def test_missing_action_module_returns_error(self):
        self.modules.balances.pop(self.agent.node_id)
        result = self.move()
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertIn('不可用', result['message'])
        self.assertEqual(self.profile_place(), self.market.node_id)

    def test_tool_description_shows_place_name_and_cost(self):
        definition = self.here.tool_definitions['move_here']
        self.assertIn('中央广场', definition['description'])
        self.assertIn('3', definition['description'])
        self.assertEqual(definition['access_channels'], ['move.access'])
        self.assertEqual(definition['parameters'], {'type': 'object', 'additionalProperties': False, 'properties': {}})

    def test_defaults_use_node_name_and_cost_three(self):
        gate = Node('place/gate', '城门', None)
        self.network.add_node(gate)
        instance = CREATE(self.backend, gate, {'channels': ['move.access']}, {})
        instance.install()
        self.addCleanup(instance.close)
        description = gate.tool_definitions['move_here']['description']
        self.assertIn('城门', description)
        self.assertIn('3', description)

    def test_free_destination_does_not_spend(self):
        gate = Node('place/gate', '城门', None)
        self.network.add_node(gate)
        gate.connect(self.market.node_id, channels=['road'], threshold=1)
        self.market.connect(gate.node_id, channels=['road'], threshold=1)
        instance = CREATE(self.backend, gate, {'channels': ['move.access'], 'cost': 0}, {})
        instance.install()
        self.addCleanup(instance.close)
        result = self.move_at(gate)
        self.assertTrue(result['ok'])
        self.assertTrue(result['moved'])
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['remaining'], 10)
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), gate.node_id)
        self.assertEqual(self.edge_channels(gate, self.agent.node_id), [('presence',)])

    def test_arrival_event_message_and_effects(self):
        dock = self.install_arrival()
        self.modules.draw_result = {'events': [
            {'id': 'rain', 'message': '细雨落下。', 'effects': {'weather': 'rain', 'mood': -1}},
            {'id': 'coin', 'message': '你捡到两枚硬币。',
             'effects': {'coins': 2, 'items': {'旧硬币': 1}, 'fields': {'mood': '高兴'}}},
        ]}
        result = self.move_at(dock)
        self.assertTrue(result['ok'])
        self.assertTrue(result['moved'])
        self.assertEqual(result['cost'], 3)
        self.assertEqual(result['remaining'], 7)
        self.assertEqual(result['place'], dock.node_id)
        self.assertIn('细雨落下。', result['message'])
        self.assertIn('你捡到两枚硬币。', result['message'])
        self.assertIn('到达时见闻', result['message'])
        self.assertEqual([event['id'] for event in result['events']], ['rain', 'coin'])
        # 抽取参数含触发动作与 actor/place 上下文。
        self.assertEqual(len(self.modules.draw_calls), 1)
        node_id, arguments = self.modules.draw_calls[0]
        self.assertEqual(node_id, 'events/dock')
        self.assertEqual(arguments, {
            'trigger': 'arrive',
            'context': {'actor': self.agent.node_id, 'place': dock.node_id},
        })
        # 只有 coins/items/fields 形状的 effects 会 adjust 到执行者。
        self.assertEqual(self.modules.adjust_calls, [(
            self.agent.node_id,
            {'coins': 2, 'items': {'旧硬币': 1}, 'fields': {'mood': '高兴'}},
        )])
        state = self.modules.profiles[self.agent.node_id]
        self.assertEqual(state['coins'], 2)
        self.assertEqual(state['items'], {'旧硬币': 1})
        self.assertEqual(state['profile']['mood'], '高兴')
        self.assertEqual(state['profile']['place'], dock.node_id)
        self.assertEqual(self.modules.counts, {'rain': 1, 'coin': 1})
        self.assertEqual(self.edge_channels(dock, self.agent.node_id), [('presence',)])
        self.assertEqual(self.edge_channels(self.market, self.agent.node_id), [('pulse',)])

    def test_arrival_without_hits_still_moves(self):
        dock = self.install_arrival()
        self.modules.draw_result = {'events': []}
        result = self.move_at(dock)
        self.assertTrue(result['ok'])
        self.assertTrue(result['moved'])
        self.assertEqual(result['events'], [])
        self.assertNotIn('到达时见闻', result['message'])
        self.assertEqual(self.modules.adjust_calls, [])
        self.assertEqual(self.modules.counts, {})
        self.assertEqual(self.profile_place(), dock.node_id)
        self.assertEqual(self.edge_channels(dock, self.agent.node_id), [('presence',)])

    def test_arrival_effect_failure_keeps_everything_consistent(self):
        dock = self.install_arrival()
        self.modules.counts['rain'] = 4
        self.modules.draw_result = {'events': [
            {'id': 'bonus', 'message': '先捡到五枚硬币。', 'effects': {'coins': 5}},
            {'id': 'rain', 'message': '坏事发生。', 'effects': {'items': {'旧硬币': -1}}},
        ]}
        result = self.move_at(dock)
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertIn('未完成', result['message'])
        # 行动值、人物资料、资源、抽取次数都回到原状。
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), self.market.node_id)
        state = self.modules.profiles[self.agent.node_id]
        self.assertEqual(state['coins'], 0)
        self.assertEqual(state['items'], {})
        self.assertEqual(self.modules.counts, {'rain': 4})
        # 在场接口完全没有改动。
        self.assertEqual(set(self.edge_channels(self.market, self.agent.node_id)[0]), {self.presence, 'pulse'})
        self.assertEqual(set(self.edge_channels(self.agent, self.market.node_id)[0]), {self.presence, 'pulse'})
        self.assertEqual(self.edge_channels(dock, self.agent.node_id), [])
        self.assertEqual(self.edge_channels(self.agent, dock.node_id), [])

    def test_arrival_draw_failure_rolls_back_spend(self):
        dock = self.install_arrival()
        self.modules.fail_draw = True
        result = self.move_at(dock)
        self.assertFalse(result['ok'])
        self.assertFalse(result['moved'])
        self.assertIn('依赖组件不可用', result['message'])
        self.assertEqual(self.modules.balances[self.agent.node_id], 10)
        self.assertEqual(self.profile_place(), self.market.node_id)
        self.assertEqual(self.edge_channels(dock, self.agent.node_id), [])
        self.assertEqual(self.edge_channels(self.agent, dock.node_id), [])


if __name__ == '__main__':
    unittest.main()
