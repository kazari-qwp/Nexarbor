import asyncio
import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness


class KnowledgeCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node('vault', name='知识库')
        self.h.add_node('source', name='调用方')
        self.h.add_node('npc', agent=True, name='研究员')

    async def asyncTearDown(self):
        await self.h.close()

    def mount(self, config=None, node='vault'):
        return self.h.mount(
            node,
            config=config or {},
            access={'strength': 3, 'channels': ['knowledge']},
        )

    async def put(self, doc_id, title, text, tags, key=None, actor=None):
        parameters = {'id': doc_id, 'title': title, 'text': text, 'tags': tags}
        if key is not None:
            parameters['key'] = key
        return await self.h.call(
            'vault', 'put', parameters, actor=actor, strength=3, channels=['knowledge']
        )

    async def test_write_read_and_tag_keyword_search(self):
        self.mount()
        first = await self.put('potion', '月光药剂', '月光草与银粉调和，静置一夜。', ['炼金', '配方'])
        second = await self.put('ore', '矿石笔记', '银矿常见于北坡。', ['采矿'])
        self.assertEqual(first['status'], 'ok', first)
        self.assertEqual(second['status'], 'ok', second)
        self.assertEqual(first['data']['revision'], 1)

        read = await self.h.call('vault', 'get', {'id': 'potion'}, channels=['knowledge'])
        self.assertEqual(read['status'], 'ok', read)
        self.assertEqual(read['data']['document']['text'], '月光草与银粉调和，静置一夜。')

        found = await self.h.call(
            'vault', 'search', {'query': '银粉', 'tags': ['炼金'], 'limit': 10},
            channels=['knowledge'],
        )
        self.assertEqual(found['status'], 'ok', found)
        self.assertEqual([item['id'] for item in found['data']['items']], ['potion'])
        self.assertEqual(found['data']['total'], 1)

        no_tag = await self.h.call(
            'vault', 'search', {'query': '银', 'tags': ['炼金', '采矿']},
            channels=['knowledge'],
        )
        self.assertEqual(no_tag['status'], 'ok', no_tag)
        self.assertEqual(no_tag['data']['items'], [])

    async def test_soft_delete_hides_from_default_search_but_keeps_history(self):
        self.mount()
        await self.put('potion', '月光药剂', '月光草配方', ['炼金'])
        removed = await self.h.call('vault', 'remove', {'id': 'potion'}, channels=['knowledge'])
        self.assertEqual(removed['status'], 'ok', removed)
        self.assertTrue(removed['data']['deleted'])

        found = await self.h.call('vault', 'search', {}, channels=['knowledge'])
        self.assertEqual(found['status'], 'ok', found)
        self.assertEqual(found['data']['items'], [])

        read = await self.h.call('vault', 'get', {'id': 'potion'}, channels=['knowledge'])
        self.assertTrue(read['data']['document']['deleted'])

        history = await self.h.call('vault', 'history', {'id': 'potion'}, channels=['knowledge'])
        self.assertEqual(history['status'], 'ok', history)
        self.assertEqual([item['revision'] for item in history['data']['items']], [1, 2])
        self.assertTrue(history['data']['items'][-1]['deleted'])
        self.assertNotIn('text', history['data']['items'][0])

    async def test_restore_creates_new_revision_without_rewriting_old_history(self):
        self.mount()
        await self.put('note', '初稿', '第一版正文', ['草稿'])
        await self.put('note', '修订稿', '第二版正文', ['正式'])
        restored = await self.h.call(
            'vault', 'restore', {'id': 'note', 'revision': 1}, channels=['knowledge']
        )
        self.assertEqual(restored['status'], 'ok', restored)
        self.assertEqual(restored['data']['restored_from'], 1)
        self.assertEqual(restored['data']['revision'], 3)

        read = await self.h.call('vault', 'get', {'id': 'note'}, channels=['knowledge'])
        self.assertEqual(read['data']['document']['title'], '初稿')
        self.assertEqual(read['data']['document']['text'], '第一版正文')
        self.assertEqual(read['data']['document']['revision'], 3)

        history = await self.h.call('vault', 'history', {'id': 'note'}, channels=['knowledge'])
        summaries = history['data']['items']
        self.assertEqual([item['revision'] for item in summaries], [1, 2, 3])
        self.assertEqual(summaries[0], {'revision': 1, 'title': '初稿', 'deleted': False})
        self.assertEqual(summaries[1], {'revision': 2, 'title': '修订稿', 'deleted': False})

    async def test_read_only_rejects_all_mutations_without_changing_data(self):
        self.mount(config={'read_only': True})
        put = await self.put('blocked', '禁止', '不应写入', ['只读'])
        remove = await self.h.call('vault', 'remove', {'id': 'blocked'}, channels=['knowledge'])
        restore = await self.h.call(
            'vault', 'restore', {'id': 'blocked', 'revision': 1}, channels=['knowledge']
        )
        for result in (put, remove, restore):
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('只读', result['error'])

        found = await self.h.call('vault', 'search', {}, channels=['knowledge'])
        self.assertEqual(found['status'], 'ok', found)
        self.assertEqual(found['data']['items'], [])

    async def test_capacity_and_history_limits_are_enforced(self):
        module = self.mount(config={'max_entries': 2, 'history_limit': 2})
        await self.put('a', '甲', '甲正文', [])
        await self.put('b', '乙', '乙正文', [])
        full = await self.put('c', '丙', '丙正文', [])
        self.assertEqual(full['status'], 'error', full)
        self.assertIn('最大文档数', full['error'])

        await self.h.call('vault', 'remove', {'id': 'a'}, channels=['knowledge'])
        added = await self.put('c', '丙', '丙正文', [])
        self.assertEqual(added['status'], 'ok', added)

        await self.h.call('vault', 'remove', {'id': 'b'}, channels=['knowledge'])
        await self.h.call('vault', 'remove', {'id': 'c'}, channels=['knowledge'])
        await self.put('d', '版本一', '一', [])
        await self.put('d', '版本二', '二', [])
        await self.put('d', '版本三', '三', [])
        await self.put('d', '版本四', '四', [])
        history = await self.h.call('vault', 'history', {'id': 'd'}, channels=['knowledge'])
        self.assertEqual(history['status'], 'ok', history)
        self.assertEqual([item['revision'] for item in history['data']['items']], [3, 4])
        self.assertEqual(len(module.state['documents']['d']['history']), 2)

    async def test_concurrent_puts_do_not_lose_revisions(self):
        module = self.mount(config={'history_limit': 100})
        await self.put('shared', '初始', '初始正文', ['并发'])
        calls = [
            self.put('shared', '并发%d' % index, '正文%d' % index, ['并发'])
            for index in range(10)
        ]
        results = await asyncio.gather(*calls)
        self.assertTrue(all(result['status'] == 'ok' for result in results), results)

        read = await self.h.call('vault', 'get', {'id': 'shared'}, channels=['knowledge'])
        self.assertEqual(read['data']['document']['revision'], 11)
        revisions = [item['revision'] for item in module.state['documents']['shared']['history']]
        self.assertEqual(revisions, list(range(1, 12)))

    async def test_wrong_channel_and_disconnected_edge_are_rejected(self):
        self.mount()
        self.h.connect('source', 'vault', channels=['other'])
        with self.assertRaises(PermissionError):
            await self.h.call(
                'vault', 'put',
                {'id': 'x', 'title': '越权', 'text': '正文', 'tags': []},
                actor='source', strength=1, channels=['knowledge'],
            )
        with self.assertRaises(PermissionError):
            await self.h.call('vault', 'search', {}, channels=['other'])
        self.h.disconnect('source', 'vault')
        with self.assertRaises(PermissionError):
            await self.h.call('vault', 'search', {}, actor='source', strength=3, channels=['knowledge'])

    async def test_requester_key_idempotency_and_conflict(self):
        self.mount()
        first = await self.put('idem', '幂等文档', '原始正文', ['键'], key='request-1')
        self.assertEqual(first['status'], 'ok', first)
        self.assertTrue(first['data']['created'])
        self.assertFalse(first['data']['idempotent'])

        repeated = await self.put('idem', '幂等文档', '原始正文', ['键'], key='request-1')
        self.assertEqual(repeated['status'], 'ok', repeated)
        self.assertTrue(repeated['data']['idempotent'])
        self.assertEqual(repeated['data']['revision'], first['data']['revision'])

        conflict = await self.put('idem', '幂等文档', '不同正文', ['键'], key='request-1')
        self.assertEqual(conflict['status'], 'error', conflict)
        self.assertIn('不同内容', conflict['error'])

        another = await self.put('other', '另一文档', '另一正文', [], key='request-1')
        self.assertEqual(another['status'], 'error', another)

    async def test_agent_tools_reach_node_through_permission_route(self):
        self.mount()
        self.h.connect('npc', 'vault', channels=['knowledge'], threshold=1)
        entries = await self.h.tools.visit(
            'npc', 'vault', strength=2, channels=['knowledge']
        )
        by_id = {entry['tool_id']: entry for entry in entries}
        self.assertIn('knowledge_put', by_id)
        self.assertIn('knowledge_search', by_id)

        put_data = await self.h.tools.invoke(
            'npc', by_id['knowledge_put'],
            {'id': 'tool-doc', 'title': '工具记录', 'text': '通过权限路由写入', 'tags': ['工具']},
            strength=2, channels=['knowledge'],
        )
        self.assertEqual(put_data['revision'], 1)

        search_data = await self.h.tools.invoke(
            'npc', by_id['knowledge_search'], {'query': '权限路由'}, strength=2, channels=['knowledge']
        )
        self.assertEqual([item['id'] for item in search_data['items']], ['tool-doc'])

        direct = await self.h.call(
            'vault', 'get', {'id': 'tool-doc'}, actor='npc', strength=2, channels=['knowledge']
        )
        self.assertEqual(direct['status'], 'ok', direct)
        self.assertEqual(direct['data']['document']['title'], '工具记录')


if __name__ == '__main__':
    unittest.main()
