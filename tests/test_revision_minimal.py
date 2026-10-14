"""Focused contracts for concurrent rounds, acceptance waiting and saved logs."""
import json, re, unittest
from pathlib import Path
from threading import Barrier, Event
import test_application as fixtures
import test_cooperation as cooperation
import test_group_runs as runs


class RevisionTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = cooperation.CooperationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team
    start = cooperation.CooperationTests.start
    reopen = runs.GroupRunTests.reopen

    def test_round_notebook_snapshot_survives_disk_restore(self):
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        group = self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='restored', project='资料', member_count=1, rounds=1))
        self.app.rpc('group_begin', group_id='restored', task='恢复快照')
        initial = self.app.rpc('start_round', group_id='restored')
        self.invoke('write_resident_text', dict(content='本轮新写入'), group['recorder_id'])
        self.reopen()
        recovered = self.app.rpc('start_round', group_id='restored')
        self.assertEqual(recovered['notebook_snapshot'], initial['notebook_snapshot'])
        self.assertNotIn('本轮新写入', recovered['notebook_snapshot'])

    def test_parallel_rounds_share_notebook_snapshot_and_wait_for_everyone(self):
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        group = self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='parallel', project='资料', member_count=1, rounds=2))
        barriers = {n: Barrier(3) for n in (1, 2)}
        updated = {n: Event() for n in (1, 2)}
        observed = []
        original = self.native.__class__.__call__
        testcase = self
        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'run' and p['actor'] in group['members']:
                    turn = native.app.plugins['network_presets/discussion_group'].turns[p['actor']]
                    if not turn['final']:
                        n = turn['round']
                        testcase.assertNotIn('当前轮数：', p['text'])
                        testcase.assertEqual(p['execution_id'], 'round-parent')
                        if n == 2:
                            testcase.assertEqual(len([o for o in observed if o[0] == 1]), 3)
                        barriers[n].wait(timeout=5)
                        if p['actor'] == group['recorder_id']:
                            native.app.invoke(p['actor'], 'write_resident_text', dict(content=f'第{n}轮新笔记'))
                            updated[n].set()
                        testcase.assertTrue(updated[n].wait(5))
                        texts = []
                        native.app.emit('context/tail', actor=p['actor'], texts=texts)
                        notebook = next(t for t in texts if t.startswith('[公共笔记：'))
                        testcase.assertNotIn(f'第{n}轮新笔记', notebook)
                        if n == 2:
                            testcase.assertIn('第1轮新笔记', notebook)
                        observed.append((n, p['actor']))
                if name == 'cancel-agent':
                    native.calls.append((name, p))
                    return {'ok': True}
                return original(native, name, p)
        self.native.__class__ = Port
        result = self.app.invoke('root', 'datanet_discuss', dict(group_id='parallel', task='两轮并行'), execution_id='round-parent')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(observed), 6)

    def test_parallel_failure_cancels_other_running_members(self):
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        group = self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='failed', project='资料', member_count=1, rounds=1))
        barrier, release = Barrier(3), Event()
        original = self.native.__class__.__call__
        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'cancel-agent':
                    native.calls.append((name, p)); release.set(); return {'ok': True}
                if name == 'run' and p['actor'] in group['members']:
                    barrier.wait(5)
                    if p['actor'] == group['members'][0]:
                        raise RuntimeError('成员异常')
                    if not release.wait(5):
                        raise RuntimeError('未取消其他成员')
                return original(native, name, p)
        self.native.__class__ = Port
        with self.assertRaisesRegex(RuntimeError, '成员异常'):
            self.invoke('datanet_discuss', dict(group_id='failed', task='故障最小测试'))
        cancelled = {p['actor'] for name, p in self.native.calls if name == 'cancel-agent'}
        self.assertEqual(cancelled, set(group['members']))

    def test_saved_spill_logs_and_stable_review_approved_member_waits(self):
        group = self.team(count=3)
        self.start(group)
        a, b, c = group['members']
        workspace = self.invoke('datanet_team_workspace', dict(action='inspect'), a)
        own, artifacts = Path(workspace['personal_path']), Path(workspace['artifacts_path'])
        self.assertFalse(artifacts.is_relative_to(own))
        (own / 'test.py').write_text('assert 1 + 1 == 2', encoding='utf-8')
        self.invoke('datanet_team_workspace', dict(action='publish'), a)
        report = artifacts / 'report.json'
        report.write_text('{"passed":1}', encoding='utf-8')
        spill = artifacts / 'spill.txt'
        full = 'START\n' + 'log\n' * 5000 + 'END\n'
        spill.write_text(full, encoding='utf-8')
        self.app.emit('tool/result', actor=a, name='pwsh', arguments={'command':'python test.py'}, result={'content':[{'type':'text','text':'tail'}], 'value':{'stdout':{'text':'tail','truncated':True,'spillPath':str(spill)},'stderr':{'text':'','truncated':False},'exitCode':0}})
        entries = self.invoke('datanet_command_logs', {'action':'list'}, a)['logs']
        log = entries[0]
        saved = json.loads(Path(log['path']).read_text(encoding='utf-8'))
        self.assertEqual(saved['streams']['stdout']['text'], full)
        pieces, offset = [], 0
        while True:
            chunk = self.invoke('datanet_command_logs', dict(action='read',log_id=log['id'],offset=offset,limit=3000), a)
            pieces.append(chunk['content'])
            if chunk['next_offset'] is None: break
            offset = chunk['next_offset']
        self.assertEqual(json.loads(''.join(pieces)), saved)
        with self.assertRaises(ValueError):
            self.invoke('datanet_command_logs', dict(action='read',log_id=log['id']), b)
        proposal = self.invoke('datanet_team_finish', dict(action='propose',content='完成',evidence='测试通过',test_scripts=['test.py'],test_results=[str(report)]), a)
        candidate, review = proposal['candidate']['id'], proposal['candidate']['review']
        self.assertEqual(review['execution_log_count'],1)
        self.assertEqual(Path(review['test_scripts'][0]).read_text(), 'assert 1 + 1 == 2')
        report.write_text('{"passed":0}', encoding='utf-8')
        self.assertEqual(Path(review['test_results'][0]).read_text(), '{"passed":1}')
        self.assertFalse((Path(review['source_path']) / 'report.json').exists())
        self.invoke('datanet_team_finish', dict(action='approve',candidate_id=candidate,evidence='材料无异议'), b)
        before = len(self.native.calls)
        self.app.emit('agent/turn-stopping', actor=b)
        self.assertFalse(any(name=='steer' and p['actor']==b for name,p in self.native.calls[before:]))
        self.app.emit('agent/turn-stopping', actor=c)
        self.assertTrue(any(name=='steer' and p['actor']==c for name,p in self.native.calls[before:]))
        before = len(self.native.calls)
        self.invoke('datanet_team_finish', dict(action='reject',candidate_id=candidate,evidence='需补充边界条件'), c)
        self.assertTrue(any(name=='steer' and p['actor']==b for name,p in self.native.calls[before:]))
        self.assertTrue(Path(review['manifest_path']).exists())
        self.invoke('datanet_cooperate', dict(group_id='team',action='stop'))


if __name__ == '__main__':
    unittest.main()
