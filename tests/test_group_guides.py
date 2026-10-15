"""Caller/member guide routing through component events, without paid inference."""
import json
import unittest
import test_application as fixtures
import test_cooperation as cooperation


class GroupGuideTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team
    discussion = cooperation.CooperationTests.discussion

    def test_network_creation_grant_creates_preset_members_without_generic_agent_creation(self):
        root = self.app.state('root')
        root['grant']['framework'].pop('datanet_create_agent', None)
        root['dynamic'].pop('datanet_create_agent_channel', None)
        self.app.refresh('root')
        discussion = self.discussion(3)
        team = self.team(count=4)
        self.assertEqual(len(discussion['members']), 5)
        self.assertEqual(len(team['members']), 4)
        status = self.app.rpc('cooperative_status', actor='root', group_id=team['group_id'], strength=100)
        workspace = self.app.plugins['capabilities/decentralized_group'].workspace(self.backend.cooperative_groups[team['group_id']])
        self.assertEqual(status['workspace'], str(workspace.main))
        self.assertNotIn('datanet_create_agent_channel', self.native.tools['root'])
        self.assertTrue(all(actor in self.native.agents for actor in discussion['members'] + team['members']))

    def text(self, preset, member=False):
        path = fixtures.ROOT / 'extensions/multi_agent/network_presets' / preset
        return (path / ('members/AGENTS.md' if member else 'AGENTS.md')).read_text(encoding='utf-8')

    def test_descriptions_reach_the_preset_directory(self):
        directory = json.dumps(self.invoke('datanet_presets'), ensure_ascii=False)
        self.assertIn('去中心化的项目小组，用类似github协作的方式完成项目方案，默认具有相关工具来提交代码和自己测试。适合并行完成项目目标。最好是拥有详细方案或者初始框架后再下达任务。', directory)
        self.assertIn('讨论小组：一个讨论小组，默认只有讨论工具，无终端等其他工具。适合讨论和指定方案。', directory)

    def test_cooperative_caller_and_members_get_separate_guides(self):
        group = self.team(count=2)
        caller_key = ('root', 'preset:decentralized_group')
        self.assertEqual(self.native.documents[caller_key], self.text('decentralized_group'))
        self.app.plugins['capabilities/agent_delegation'].start_worker = lambda target: None
        self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='start', task='指南验证'))
        for actor in group['members']:
            key = (actor, 'preset:decentralized_group:member')
            self.assertEqual(self.native.documents[key], self.text('decentralized_group', True))
            self.assertNotIn((actor, 'preset:decentralized_group'), self.native.documents)
            # A compaction removes the document marker; the next step reloads its guide.
            self.native.documents.pop(key)
            self.app.event(actor, 'agent/pre-step', dict(messages=[]))
            self.assertEqual(self.native.documents[key], self.text('decentralized_group', True))
        self.assertNotIn(('root', 'preset:decentralized_group:member'), self.native.documents)
        self.native.documents.pop(caller_key)
        self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='status'))
        self.assertEqual(self.native.documents[caller_key], self.text('decentralized_group'))
        self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='stop'))

    def test_discussion_members_get_guide_before_their_first_run(self):
        group = self.discussion(1)
        caller_key = ('root', 'preset:discussion_group')
        self.assertEqual(self.native.documents[caller_key], self.text('discussion_group'))
        original = self.native.__class__.__call__
        testcase = self

        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'run' and p['actor'] in group['members']:
                    key = (p['actor'], 'preset:discussion_group:member')
                    testcase.assertEqual(native.documents[key], testcase.text('discussion_group', True))
                return original(native, name, p)

        self.native.__class__ = Port
        self.native.documents.pop(caller_key)
        self.invoke('datanet_discuss', dict(group_id=group['group_id'], task='讨论指南验证'))
        self.assertEqual(self.native.documents[caller_key], self.text('discussion_group'))
        for actor in group['members']:
            self.assertNotIn((actor, 'preset:discussion_group'), self.native.documents)
            key = (actor, 'preset:discussion_group:member')
            self.native.documents.pop(key)
            turn = self.app.plugins['capabilities/discussion_group'].turns[actor]
            turn.update(active=True, count=0)
            try:
                self.app.event(actor, 'agent/pre-step', dict(messages=[]))
                self.assertEqual(self.native.documents[key], self.text('discussion_group', True))
            finally:
                turn['active'] = False
        self.assertNotIn(('root', 'preset:discussion_group:member'), self.native.documents)


if __name__ == '__main__':
    unittest.main()
