import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'adapters/harness/backend'))
from server import Backend

class SharedTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Backend(self.tmp.name)

    def tearDown(self):
        self.b.close()
        self.tmp.cleanup()

    def create(self, child, mode='query'):
        r = self.b.dispatch('create_node', {'actor': 'root', 'child_id': child, 'node_spec': {'preset': mode + '_text'}, 'options': {'scope': 'descendants'}})
        self.assertEqual(r.status, 'ok', r.errors)
        target = 'root/' + child
        self.b.dispatch('write', {'actor': 'root', 'target': target, 'key': 'content', 'value': child, 'strength': 100})
        return target

    def group(self, name, **source):
        return self.b.dispatch('create_network', {'actor': 'root', 'preset': 'discussion_group', 'instance_id': name, 'rounds': 1, 'strength': 100, **source})

    def test_modes_bindings_and_permissions(self):
        q = self.create('q')
        r = self.create('r', 'resident')
        bindings = self.b.dispatch('text_bindings', {'actor': 'root', 'strength': 100})
        self.assertEqual([x['node_id'] for x in bindings['write']], [r])
        self.assertEqual(self.b.dispatch('resident_texts', {'actor': 'root', 'strength': 100})['texts'][0]['text'], '[常驻文本：root/r](正文随读取连接自动放入Agent请求尾部。)\nr')
        self.assertEqual(self.b.dispatch('read', {'actor': 'root', 'target': r, 'request': {'method': 'key', 'key': 'content'}, 'strength': 100}).status, 'unsupported')
        self.assertNotIn('read', self.b.network.nodes[r].tools)
        with self.assertRaises(PermissionError):
            self.b.dispatch('write_resident_text', {'actor': 'root', 'target': q, 'content': 'wrong', 'strength': 100})
        wrote = self.b.dispatch('write_resident_text', {'actor': 'root', 'content': 'new', 'strength': 100})
        self.assertEqual(wrote.items, [{'node_id': r, 'written': True}])
        self.assertEqual(self.b.dispatch('query_text', {'actor': 'root', 'target': q, 'strength': 100})['text'].split('\n')[-1], 'q')

    def test_group_inline_and_shared_sources(self):
        with self.assertRaises(ValueError):
            self.group('missing')
        self.assertNotIn('missing/board', self.b.network.nodes)
        inline = self.group('inline', project='真实项目说明')
        self.assertEqual(inline['status'], 'ok')
        notebook = self.b.network.nodes['inline/notebook']
        self.assertEqual(notebook.delivery, 'resident')
        q1 = self.create('first')
        q2 = self.create('second')
        external = self.group('external', project_nodes=[q1, q2])
        self.assertEqual(external['status'], 'ok')
        self.assertNotIn('external/project', self.b.network.nodes)
        self.assertEqual(self.b.network.nodes[q1].management_parent_id, 'root')
        for member in external['members']:
            result = self.b.dispatch('load_project', {'actor': member, 'group_id': 'external', 'strength': 100})
            self.assertEqual([x['node_id'] for x in result.items], [q1, q2])
            self.assertEqual(self.b.dispatch('resident_texts', {'actor': member, 'strength': 100})['texts'][0]['text'], '[公共笔记：external/notebook](由recorder维护)\n')
        with self.assertRaises(PermissionError):
            self.b.dispatch('write_resident_text', {'actor': 'external/member_1', 'target': 'external/notebook', 'content': 'bad', 'strength': 100})
        self.b.dispatch('write_resident_text', {'actor': 'external/recorder', 'content': '共享笔记更新', 'strength': 100})
        self.b.close()
        self.b = Backend(self.tmp.name)
        info = self.b.dispatch('group_info', {'group_id': 'external'})
        self.assertEqual(info['project_ids'], [q1, q2])
        self.assertEqual(self.b.network.nodes['external/notebook'].delivery, 'resident')
        self.assertNotIn('read', self.b.network.nodes['external/notebook'].tools)
        self.assertIn('共享笔记更新', self.b.dispatch('resident_texts', {'actor': 'external/member_2', 'strength': 100})['texts'][0]['text'])

    def test_root_documents_are_query_only(self):
        self.b.dispatch('load_root_network', {'package': 'project_root'})
        bindings = self.b.dispatch('text_bindings', {'actor': 'root', 'strength': 100})
        self.assertEqual({x['delivery'] for x in bindings['read']}, {'query'})
        self.assertEqual(len(bindings['read']), 3)
        self.assertEqual(self.b.dispatch('resident_texts', {'actor': 'root', 'strength': 100}), {'texts': []})
if __name__ == '__main__':
    unittest.main(verbosity=2)
