import copy
import unittest
import test_application as fixtures


class GuideDisclosureTests(unittest.TestCase):
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke

    def setUp(self):
        fixtures.ApplicationTests.setUp(self)
        self.admissions = []
        admissions = self.admissions
        original = self.native.__class__.__call__
        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'load-document' and native.documents.get((p['actor'], p['document'])) != p['text']:
                    admissions.append((p['actor'], p['document']))
                return original(native, name, p)
        self.native.__class__ = Port

    def direct_root(self):
        state = self.app.state('root')
        state['grant'] = self.app.resolve(['network_access', 'node_creation', 'discussion'])
        self.app.refresh('root')
        self.assertNotIn('datanet_skill', self.native.tools['root'])
        return state

    def loads(self, actor='root'):
        return self.admissions.count((actor, 'network_management'))

    def test_direct_channel_guide_without_skill_or_extra_permissions(self):
        state = self.direct_root()
        grant = copy.deepcopy(state['grant'])
        self.invoke('datanet_create_network_channel', {'preset': 'discussion_group'})
        self.assertIn('节点网络组装指南', self.native.documents[('root', 'network_management')])
        self.invoke('datanet_create_network_channel', {'preset': 'discussion_group'})
        self.assertEqual(self.loads(), 1)
        self.assertEqual(state['grant'], grant)
        self.assertNotIn('network_management', state.get('loaded_skills', set()))

    def test_open_tool_and_discuss_reload_after_compaction(self):
        self.direct_root()
        self.invoke('datanet_create_network_channel', {'preset': 'discussion_group'})
        self.native.documents.pop(('root', 'network_management'))
        self.invoke('datanet_create_network', {'preset': 'discussion_group', 'instance_id': 'group', 'project': '资料', 'member_count': 1, 'rounds': 1})
        self.assertEqual(self.loads(), 2)
        self.native.documents.pop(('root', 'network_management'))
        self.invoke('datanet_discuss', {'group_id': 'group', 'task': '讨论并归档'})
        self.assertEqual(self.loads(), 3)

    def test_skill_and_direct_routes_share_one_guide(self):
        self.invoke('datanet_skill', {'action': 'load', 'name': 'network_management'})
        self.invoke('datanet_create_node_channel')
        self.invoke('datanet_skill', {'action': 'load', 'name': 'network_management'})
        self.assertEqual(self.loads(), 1)
        self.assertIn('network_management', self.app.state('root')['loaded_skills'])

    def test_member_data_access_does_not_disclose_management_guide(self):
        self.invoke('datanet_create_network_channel', {'preset': 'discussion_group'})
        group = self.invoke('datanet_create_network', {'preset': 'discussion_group', 'instance_id': 'group', 'project': '资料', 'member_count': 1, 'rounds': 1})
        member = group['members'][2]
        self.invoke('datanet_memory_read', actor=member)
        self.invoke('node_tools', {'target': member}, member)
        self.assertEqual(self.loads(member), 0)
        self.assertNotIn((member, 'network_management'), self.native.documents)


if __name__ == '__main__':
    unittest.main()
