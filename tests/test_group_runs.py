"""Repeated tasks on the same members, with isolated run state and durable history."""
import json
import unittest
from threading import Event
from pathlib import Path
from uuid import uuid4
import test_application as fixtures
import test_cooperation as cooperation


class GroupRunTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = cooperation.CooperationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    discussion = cooperation.CooperationTests.discussion
    team = cooperation.CooperationTests.team
    start = cooperation.CooperationTests.start

    def distinct_discussion_results(self):
        original = self.native.__class__.__call__

        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'run':
                    actor = p['actor']
                    turn = native.app.plugins['capabilities/discussion_group'].turns.get(actor)
                    if turn and turn['final']:
                        group = native.app.backend.groups[native.app.backend.agents[actor]['group_id']]
                        native.app.invoke(actor, 'node_write', dict(target=turn['expected_output'], key='content', value=group['task'] + '成果'))
                        message = dict(id=str(uuid4()), role='assistant', content=[dict(type='text', text=group['task'] + '成果')])
                        native.messages.setdefault(actor, []).append(message)
                        return dict(messages=[message], session_id=native.agents[actor]['session_id'],completion='completed')
                return original(native, name, p)

        self.native.__class__ = Port

    def complete_team(self, group, content):
        workers = group['members']
        result = self.invoke('datanet_team_finish', dict(action='propose', content=content, evidence='已验证'), workers[0])
        for worker in workers[1:]:
            result = self.invoke('datanet_team_finish', dict(action='approve', candidate_id=result['candidate']['id'], evidence='已复核'), worker)
        self.assertEqual(result['phase'], 'completed')

    def reopen(self, corrupt=None):
        if hasattr(self, 'release'):
            self.release.set()
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        if corrupt:
            corrupt()
        self.backend = fixtures.Backend(self.temp.name)
        self.native = fixtures.NativePort()
        self.app = fixtures.Application(self.backend, self.native, dict(rootNetwork='project_root', rootToolboxes=['network_access', 'node_creation', 'agent_management', 'interface_management', 'discussion'], maxSignalStrength=100))
        self.native.app = self.app
        self.app.plugins['capabilities/tools_network_management'].bind_root('root-session')
        for actor in self.backend.agents:
            self.app.emit('agent/ensure-mounted', target=actor)

    def test_discussion_new_task_and_explicit_same_task_run_again(self):
        group = self.discussion(1)
        self.distinct_discussion_results()
        sessions = {m: self.app.state(m)['session_id'] for m in group['members']}
        a = self.invoke('datanet_discuss', dict(group_id='discussion', task='甲'))
        first = self.backend.groups['discussion']
        first_round = Path(self.temp.name, first['archives'][0])
        notebook_id = first['board'].notebook_id
        self.backend.network.nodes[notebook_id].write('content', '旧公共笔记')
        actor = group['members'][0]
        self.backend.network.nodes[actor].write_memory('个人经验', 'append')
        before = len([c for c in self.native.calls if c[0] == 'run'])
        read = self.invoke('datanet_discuss', dict(group_id='discussion'))
        self.assertEqual(read['run_id'], a['run_id'])
        self.assertEqual(len([c for c in self.native.calls if c[0] == 'run']), before)
        b = self.invoke('datanet_discuss', dict(group_id='discussion', task='乙'))
        c = self.invoke('datanet_discuss', dict(group_id='discussion', task='乙'))
        self.assertEqual(len({a['run_id'], b['run_id'], c['run_id']}), 3)
        self.assertEqual(b['output'][0]['content'], '乙成果')
        self.assertEqual(Path(self.temp.name, a['archive_path'], 'result.md').read_text(encoding='utf-8'), '甲成果')
        self.assertTrue(first_round.exists())
        self.assertEqual(self.backend.network.nodes[notebook_id].file_path.read_text(encoding='utf-8'), '')
        self.assertIn('个人经验', self.backend.network.nodes[actor].file_path.read_text(encoding='utf-8'))
        self.assertEqual(sessions, {m: self.app.state(m)['session_id'] for m in group['members']})
        self.assertEqual(len(self.backend.groups['discussion']['runs']), 3)
        self.assertNotEqual(a['report_reference']['delegation_id'], b['report_reference']['delegation_id'])
        first_messages = [p['text'] for name, p in self.native.calls if name == 'run' and p['actor'] == actor]
        self.assertEqual(len(first_messages), 3)
        self.assertNotIn('## 第1轮', first_messages[1])

    def test_discussion_interrupted_task_resumes_then_restarts_after_restore(self):
        group = self.discussion(1)
        original = self.native.__class__.__call__
        fail_actor = group['members'][1]
        first_actor = group['members'][0]
        called = []
        submitted = Event()

        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'run':
                    called.append(p['actor'])
                    if p['actor'] == fail_actor and called.count(fail_actor) == 1:
                        if not submitted.wait(5):
                            raise RuntimeError('首个成员未完成提交')
                        raise RuntimeError('模拟中断')
                result = original(native, name, p)
                if name == 'run' and p['actor'] == first_actor:
                    submitted.set()
                return result

        self.native.__class__ = Port
        with self.assertRaises(RuntimeError):
            self.invoke('datanet_discuss', dict(group_id='discussion', task='原任务'))
        run_id = self.backend.groups['discussion']['run']
        with self.assertRaises(ValueError):
            self.invoke('datanet_discuss', dict(group_id='discussion', task='新任务'))
        resumed = self.invoke('datanet_discuss', dict(group_id='discussion'))
        self.assertEqual(resumed['run_id'], run_id)
        self.assertEqual(called.count(first_actor), 1)
        archived = Path(self.temp.name, resumed['archive_path'], 'result.md')
        self.reopen()
        self.assertEqual(archived.read_text(encoding='utf-8'), '全部测试完成')
        restarted = self.invoke('datanet_discuss', dict(group_id='discussion', task='新任务'))
        self.assertNotEqual(restarted['run_id'], run_id)

    def test_cooperation_restarts_before_previous_delegations_settle(self):
        group = self.team(count=2)
        a = self.start(group)
        actor = group['members'][0]
        sessions = {m: self.app.state(m)['session_id'] for m in group['members']}
        path = Path(self.invoke('datanet_team_workspace', dict(action='inspect'), actor)['personal_path'])
        (path / 'kept.txt').write_text('已完成代码', encoding='utf-8')
        integrated = self.invoke('datanet_team_workspace', dict(action='publish'), actor)
        self.invoke('datanet_team_note', dict(kind='FACT', content='上一任务发现'), actor)
        self.backend.network.nodes[actor].write_memory('保留经验', 'append')
        old_jobs = dict(self.backend.cooperative_groups['team']['jobs'])
        self.complete_team(group, '第一份成果')
        archive = self.backend.cooperative_groups['team']['archive_path']
        b = self.start(group)
        self.assertNotEqual(a['run_id'], b['run_id'])
        state = self.invoke('datanet_cooperate', dict(group_id='team', action='status'))
        self.assertEqual(state['entries'], [])
        self.assertEqual(state['claims'], {})
        self.assertIsNone(state['candidate'])
        self.assertEqual(self.backend.network.nodes[state['entry_points']['output']].file_path.read_text(encoding='utf-8'), '')
        self.assertEqual(Path(integrated['integrated_path'], 'kept.txt').read_text(encoding='utf-8'), '已完成代码')
        self.assertIn('保留经验', self.backend.network.nodes[actor].file_path.read_text(encoding='utf-8'))
        self.assertEqual(sessions, {m: self.app.state(m)['session_id'] for m in group['members']})
        old_record = json.loads(Path(self.temp.name, archive, 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(old_record['run_id'], a['run_id'])
        self.assertEqual(Path(self.temp.name, archive, 'output.md').read_text(encoding='utf-8'), '第一份成果')
        queue = self.app.plugins['capabilities/agent_delegation']
        old = queue.jobs[next(iter(old_jobs.values()))]
        old['status'] = 'failed'
        plugin = self.app.plugins['capabilities/decentralized_group']
        plugin.settled(dict(actor=old['target'], delegation_id=old['id']))
        plugin.expire('team', a['run_id'])
        self.assertEqual(self.backend.cooperative_groups['team']['phase'], 'running')
        self.complete_team(group, '第二份成果')
        results = [json.loads(m['content'][0]['text']) for m in self.native.messages['root'] if 'cooperation_result' in json.dumps(m)]
        self.assertEqual([m['run_id'] for m in results], [a['run_id'], b['run_id']])

    def test_cooperation_terminal_states_can_start_after_restore(self):
        group = self.team(count=1)
        a = self.start(group)
        with self.assertRaises(ValueError):
            self.invoke('datanet_cooperate', dict(group_id='team', action='start', task='不能覆盖进行中的任务'))
        self.assertEqual(self.backend.cooperative_groups['team']['run_id'], a['run_id'])
        self.invoke('datanet_team_note', dict(kind='FACT', content='停止前的发现'), group['members'][0])
        self.invoke('datanet_cooperate', dict(group_id='team', action='stop'))
        self.reopen()
        b = self.start(group)
        state = self.invoke('datanet_cooperate', dict(group_id='team', action='status'))
        self.assertNotEqual(a['run_id'], b['run_id'])
        self.assertEqual(state['runs'][a['run_id']]['phase'], 'stopped')
        plugin = self.app.plugins['capabilities/decentralized_group']
        for terminal in ('failed', 'interrupted', 'budget_exhausted'):
            plugin.stop_group(self.backend.cooperative_groups['team'], terminal, '模拟结束')
            previous = self.backend.cooperative_groups['team']['run_id']
            self.start(group)
            self.assertNotEqual(self.backend.cooperative_groups['team']['run_id'], previous)

    def test_both_group_archives_restore_and_remain_immutable(self):
        self.discussion(1)
        discussion = self.invoke('datanet_discuss', dict(group_id='discussion', task='讨论归档'))
        discussion_file = Path(discussion['archive_path'], 'result.md')
        group = self.team(count=1)
        receipt = self.start(group)
        self.complete_team(group, '协作归档')
        state = self.invoke('datanet_cooperate', dict(group_id='team', action='status'))
        cooperation_file = Path(state['archive_path'], 'output.md')
        self.backend.dispatch('save', {})
        self.reopen(lambda: (discussion_file.write_text('外部改动', encoding='utf-8'),
                             cooperation_file.write_text('外部改动', encoding='utf-8')))
        self.assertEqual(discussion_file.read_text(encoding='utf-8'), '全部测试完成')
        self.assertEqual(cooperation_file.read_text(encoding='utf-8'), '协作归档')
        self.backend.network.nodes[self.backend.groups['discussion']['board'].output_id].write('content', '后来修改的当前成果')
        current = self.backend.cooperative_groups['team']
        self.backend.network.nodes[current['entry_points']['output']].write('content', '后来修改的当前成果')
        self.invoke('datanet_discuss', dict(group_id='discussion', task='下一次讨论'))
        self.start(group)
        self.assertEqual(discussion_file.read_text(encoding='utf-8'), '全部测试完成')
        self.assertEqual(cooperation_file.read_text(encoding='utf-8'), '协作归档')
        self.assertIn(receipt['run_id'], self.backend.cooperative_groups['team']['runs'])


if __name__ == '__main__':
    unittest.main()
