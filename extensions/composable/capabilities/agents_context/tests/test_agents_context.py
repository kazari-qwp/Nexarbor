"""在真实模块授权路由上验证场景、地点、图片地图和身份/记忆隔离。"""
import base64
import io
import unittest
from pathlib import Path
from PIL import Image
from datanet.studio.testing import ModuleHarness

SELF = ['self']


class AgentsContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        for key, name, description in [('town', '镇广场', '镇中心，可以休息和会面。'), ('forest', '北林', '可以砍树。')]:
            self.h.add_node(key, name=name, description=description)
            self.h.mount(key, module='place.info', config={'description': description, 'visitors_from_edges': True}, access={'strength': 0, 'channels': ['movement', 'info']})
        self.h.connect('town', 'forest', channels=['movement', 'info'], threshold=1, attributes={'relation': 'road'})
        self.h.connect('forest', 'town', channels=['movement', 'info'], threshold=1, attributes={'relation': 'road'})

    async def asyncTearDown(self):
        await self.h.close()

    async def agent(self, key='a', *, location='town', strength=4, config=None, records=None):
        self.h.add_node(key, name=key, agent=True)
        self.h.mount(key, module='records.store', config={'initial': records or {}}, access={'strength': 0, 'channels': ['records']})
        self.h.mount(key, module='place.info', config={'location': location}, access={'strength': 0, 'channels': ['movement', 'info']})
        instance = self.h.mount(key, config=config or {}, access={'strength': strength, 'channels': ['self', 'records', 'movement', 'info']})
        self.h.connect(key, location, channels=['movement', 'info'], threshold=1, attributes={'relation': 'location'})
        self.h.connect(location, key, channels=['movement', 'info'], threshold=1, attributes={'relation': 'location'})
        return instance

    async def call(self, operation, parameters=None, actor='a', target=None):
        result = await self.h.call(target or actor, operation, parameters or {}, actor=actor, channels=SELF)
        self.assertEqual(result['status'], 'ok', result)
        return result['data']

    def inputs(self, actor='a'):
        return self.h.network.nodes[actor].inputs.snapshot()['module:agents.context']

    async def test_look_is_a_small_current_scene_without_identity_map_memory_or_internal_flags(self):
        await self.agent(config={'persona': '人格秘密', 'common': '固定世界规则', 'map': '旧地图全文', 'opening': '开场内容'}, records={'coins': 7, 'ap': 4})
        await self.call('remember', {'text': '私人记忆内容'})
        value = await self.call('look')
        self.assertEqual(set(value), {'clock', 'location', 'records', 'people', 'exits'})
        self.assertEqual(value['location'], {'id': 'town', 'name': '镇广场'})
        self.assertEqual(value['records'], {'coins': 7, 'ap': 4})
        self.assertEqual(value['exits'], [{'id': 'forest', 'name': '北林'}])
        for secret in ['人格秘密', '固定世界规则', '旧地图全文', '开场内容', '私人记忆内容', 'opening_queued', 'system_prompt', 'strength', 'path']:
            self.assertNotIn(secret, repr(value))

    async def test_people_are_at_the_current_place_and_only_show_published_profile(self):
        await self.agent('a', records={'name': '阿岚'})
        await self.agent('b', config={'public_fields': ['name', 'profession']}, records={'name': '小北', 'profession': '铁匠', 'coins': 999, 'secret': '私密账本'})
        await self.agent('c', location='forest', records={'name': '远处人物'})
        await self.call('prepare', actor='b')
        await self.call('prepare', actor='c')
        value = await self.call('look')
        self.assertEqual(value['people'], [{'id': 'b', 'name': '小北', 'profile': {'name': '小北', 'profession': '铁匠'}}])
        for secret in ['999', '私密账本', '远处人物']:
            self.assertNotIn(secret, repr(value))

    async def test_move_refreshes_current_place_people_and_direct_exits(self):
        await self.agent()
        await self.agent('b', location='forest', records={'name': '小北'})
        await self.call('prepare', actor='b')
        before = await self.call('look')
        self.h.disconnect('a', 'town')
        self.h.disconnect('town', 'a')
        self.h.connect('a', 'forest', channels=['movement', 'info'], threshold=1, attributes={'relation': 'location'})
        self.h.connect('forest', 'a', channels=['movement', 'info'], threshold=1, attributes={'relation': 'location'})
        self.h.modules.instances[('a', 'place.info')].state['location'] = 'forest'
        after = await self.call('look')
        self.assertEqual(before['location']['id'], 'town')
        self.assertEqual(after['location']['name'], '北林')
        self.assertEqual(after['people'][0]['name'], '小北')
        self.assertEqual(after['exits'], [{'id': 'town', 'name': '镇广场'}])

    async def test_place_query_accepts_name_id_and_current_place(self):
        await self.agent()
        current = await self.call('place')
        self.assertEqual(current['name'], '镇广场')
        self.assertIn('会面', current['description'])
        by_name = await self.call('place', {'place': '北林'})
        by_id = await self.call('place', {'place': 'forest'})
        self.assertEqual(by_name, by_id)
        self.assertEqual(by_name['description'], '可以砍树。')
        self.assertEqual(by_name['exits'], [{'id': 'town', 'name': '镇广场'}])

    async def test_place_query_rejects_unreachable_nodes_agents_and_ambiguous_names(self):
        await self.agent()
        self.h.add_node('hidden', name='秘密地点')
        for query in ['hidden', 'a', '不存在']:
            result = await self.h.call('a', 'place', {'place': query}, actor='a', channels=SELF)
            self.assertEqual(result['status'], 'error')
        self.h.add_node('duplicate', name='北林')
        self.h.connect('town', 'duplicate', channels=['movement'], threshold=1)
        result = await self.h.call('a', 'place', {'place': '北林'}, actor='a', channels=SELF)
        self.assertEqual(result['status'], 'error')
        self.assertIn('同名', result['error'])

    async def test_map_returns_real_png_changes_with_roads_and_contains_no_people_or_memory(self):
        await self.agent(config={'map_title': '测试道路图'})
        await self.agent('b', records={'name': '私人姓名'})
        await self.call('remember', {'text': '秘密'})
        first = await self.call('map')
        self.assertEqual(first['format'], 'nexarbor-tool-content/v1')
        self.assertEqual([b['type'] for b in first['content']], ['text', 'image'])
        self.assertIn('北林=forest', first['content'][0]['text'])
        self.assertNotIn('私人姓名', first['content'][0]['text'])
        data = base64.b64decode(first['content'][1]['data'])
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertGreaterEqual(image.width, 1000)
        self.assertEqual(first, await self.call('map'))
        self.h.disconnect('forest', 'town')
        one_way = await self.call('map')
        self.assertNotEqual(first['content'][1]['data'], one_way['content'][1]['data'])

    async def test_map_scope_cannot_reveal_inaccessible_places(self):
        await self.agent(strength=1)
        value = await self.call('map')
        self.assertIn('镇广场=town', value['content'][0]['text'])
        self.assertNotIn('北林', value['content'][0]['text'])
        self.h.disconnect('a', 'town')
        result = await self.h.call('a', 'map', {}, actor='a', channels=SELF)
        self.assertEqual(result['status'], 'error')

    async def test_prepare_still_injects_identity_matched_knowledge_and_opening_once_without_map_or_memories(self):
        instance = await self.agent(config={'persona': '图书管理员', 'common': '保持简洁', 'map': '旧的固定地图', 'opening': '唯一开场', 'knowledge': [{'id': 'librarian', 'when': {'profession': '管理员'}, 'text': '懂书籍分类'}, {'id': 'doctor', 'when': {'profession': '医生'}, 'text': '医学知识'}]}, records={'profession': '管理员'})
        await self.call('remember', {'text': '私人旧事'})
        await self.call('prepare')
        await self.call('prepare')
        inputs = self.inputs()
        self.assertEqual(inputs['system_prompt'], '图书管理员\n\n保持简洁')
        self.assertEqual(inputs['context'], [{'id': 'knowledge:librarian', 'text': '懂书籍分类'}])
        self.assertEqual(len([item for item in inputs['inputs'] if item['id'] == 'agents.context.opening']), 1)
        self.assertTrue(instance.state['opening_queued'])
        self.assertNotIn('旧的固定地图', repr(inputs))
        self.assertNotIn('私人旧事', repr(inputs))
        self.assertIn('可直接前往：北林', '\n'.join(inputs['tail']))
        self.assertNotIn('路径', '\n'.join(inputs['tail']))

    async def test_clock_tail_refreshes_on_each_prepare(self):
        self.h.mount('town', module='clock.counter', config={'initial_tick': 2, 'labels': ['清晨', '上午', '下午']}, access={'strength': 0, 'channels': ['info', 'tick']})
        await self.agent(config={'clock': 'town'})
        value = await self.call('look')
        self.assertEqual(value['clock']['tick'], 2)
        self.assertEqual(value['clock']['slot'], '上午')
        self.h.modules.instances[('town', 'clock.counter')].state['tick'] = 3
        await self.call('prepare')
        self.assertTrue(any('当前时间：' in line and '下午' in line for line in self.inputs()['tail']))

    async def test_other_agent_cannot_query_any_private_entrypoint(self):
        await self.agent()
        await self.agent('b')
        self.h.connect('b', 'a', channels=SELF, threshold=1)
        for operation, args in [('look', {}), ('place', {}), ('map', {}), ('prepare', {}), ('recall', {'query': ''})]:
            result = await self.h.call('a', operation, args, actor='b', channels=SELF)
            self.assertEqual(result['status'], 'error', operation)

    async def test_memory_is_only_returned_by_memory_tools_with_idempotent_retention(self):
        await self.agent(config={'max_memories': 2})
        await self.call('remember', {'key': 'first', 'text': '旧记忆'})
        await self.call('remember', {'text': '中间记忆'})
        await self.call('remember', {'key': 'last', 'text': '新记忆'})
        duplicate = await self.call('remember', {'key': 'last', 'text': '新记忆'})
        self.assertTrue(duplicate['duplicate'])
        recalled = await self.call('recall', {'query': ''})
        self.assertEqual([item['text'] for item in recalled['memories']], ['中间记忆', '新记忆'])
        self.assertNotIn('记忆', repr(await self.call('look')))

    async def test_conflicting_memory_key_does_not_overwrite_existing_memory(self):
        await self.agent()
        await self.call('remember', {'key': 'same', 'text': '原记忆'})
        result = await self.h.call('a', 'remember', {'key': 'same', 'text': '冲突的新记忆'}, actor='a', channels=SELF)
        self.assertEqual(result['status'], 'error')
        self.assertEqual((await self.call('recall', {'query': ''}))['memories'], [{'key': 'same', 'text': '原记忆'}])

    async def test_prepare_replaces_matched_knowledge_when_own_records_change(self):
        await self.agent(config={'knowledge': [{'id': 'farmer', 'when': {'profession': '农夫'}, 'text': '农事知识'}, {'id': 'doctor', 'when': {'profession': '医生'}, 'text': '医药知识'}]}, records={'profession': '农夫'})
        await self.call('prepare')
        self.assertEqual(self.inputs()['context'], [{'id': 'knowledge:farmer', 'text': '农事知识'}])
        result = await self.h.call('a', 'apply', {'set': {'profession': '医生'}}, actor='a', module='records.store', channels=['records'])
        self.assertEqual(result['status'], 'ok')
        await self.call('prepare')
        self.assertEqual(self.inputs()['context'], [{'id': 'knowledge:doctor', 'text': '医药知识'}])

    async def test_tools_export_map_place_and_look_without_navigation(self):
        await self.agent()
        entries = await self.h.tools.visit('a', 'a', strength=1, channels=SELF)
        self.assertEqual({item['tool_id'] for item in entries}, {'remember', 'recall', 'look', 'place', 'map'})
        entry = next(item for item in entries if item['tool_id'] == 'place')
        value = await self.h.tools.invoke('a', entry, {'place': '北林'}, strength=1, channels=SELF)
        self.assertEqual(value['name'], '北林')


if __name__ == '__main__':
    unittest.main()
