import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'adapters/harness/backend'))
os.environ['DATANET_COMPONENT_ROOT']=str(Path(__file__).resolve().parents[1]/'extensions/multi_agent')
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

    def test_query_bindings_and_removed_delivery_modes(self):
        q=self.create('q')
        bindings=self.b.dispatch('text_bindings',dict(actor='root',strength=100))
        self.assertEqual([x['node_id'] for x in bindings['read']],[q])
        self.assertNotIn('write',bindings)
        self.assertEqual(self.b.dispatch('query_text',dict(actor='root',target=q,strength=100))['text'].split('\n')[-1],'q')
        absent=self.b.dispatch('create_node',dict(actor='root',child_id='obsolete',node_spec=dict(preset='resident_text'),options=dict(scope='descendants')))
        self.assertEqual(absent.status,'error')
        with self.assertRaises(ValueError):self.b.dispatch('resident_texts',dict(actor='root',strength=100))

    def test_group_inline_and_shared_sources(self):
        with self.assertRaises(ValueError):
            self.group('missing')
        self.assertNotIn('missing/board', self.b.network.nodes)
        inline = self.group('inline', project='真实项目说明')
        self.assertEqual(inline['status'], 'ok')
        notebook = self.b.network.nodes['inline/notebook']
        self.assertEqual(notebook.delivery, 'plain')
        q1 = self.create('first')
        q2 = self.create('second')
        external = self.group('external', project_nodes=[q1, q2])
        self.assertEqual(external['status'], 'ok')
        self.assertNotIn('external/project', self.b.network.nodes)
        self.assertEqual(self.b.network.nodes[q1].management_parent_id, 'root')
        for member in external['members']:
            result = self.b.dispatch('load_project', {'actor': member, 'group_id': 'external', 'strength': 100})
            self.assertEqual([x['node_id'] for x in result.items], [q1, q2])
            self.assertEqual(self.b.dispatch('read',dict(actor=member,target='external/notebook',request=dict(method='key',key='content'),strength=100)).status,'not_found')
        denied=self.b.dispatch('write',dict(actor='external/member_1',target='external/notebook',key='content',value='bad',strength=100))
        self.assertEqual(denied.status,'forbidden')
        self.assertEqual(self.b.dispatch('write',dict(actor='external/recorder',target='external/notebook',key='content',value='共享笔记更新',strength=100)).status,'ok')
        self.b.close()
        self.b = Backend(self.tmp.name)
        info = self.b.dispatch('group_info', {'group_id': 'external'})
        self.assertEqual(info['project_ids'], [q1, q2])
        self.assertEqual(self.b.network.nodes['external/notebook'].delivery, 'plain')
        self.assertNotIn('read', self.b.network.nodes['external/notebook'].expose)
        self.assertEqual(self.b.dispatch('read',dict(actor='external/member_2',target='external/notebook',request=dict(method='key',key='content'),strength=100)).items[0]['content'],'共享笔记更新')

    def test_root_documents_are_query_only(self):
        self.b.dispatch('load_root_network', {'package': 'project_root'})
        bindings = self.b.dispatch('text_bindings', {'actor': 'root', 'strength': 100})
        self.assertEqual({x['delivery'] for x in bindings['read']}, {'query'})
        self.assertEqual(len(bindings['read']), 3)
        self.assertNotIn('resident_texts', self.b.components.routes)
if __name__ == '__main__':
    unittest.main(verbosity=2)
