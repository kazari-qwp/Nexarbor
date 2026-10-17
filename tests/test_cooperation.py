"""Member expansion and peer collaboration contracts, without paid inference."""
import json
import time
import unittest
from pathlib import Path
from threading import Event
import test_application as fixtures


class CooperationTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke

    def discussion(self, count):
        self.invoke('datanet_create_network_channel', dict(preset='discussion_group'))
        return self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='discussion', project='讨论资料', member_count=count, rounds=1))

    def team(self, name='team', count=3):
        self.invoke('datanet_create_network_channel', dict(preset='decentralized_group'))
        return self.invoke('datanet_create_network', dict(preset='decentralized_group', instance_id=name, project='交付三个文件，每个文件内容须为测试。', member_count=count))

    def test_status_distinguishes_pending_native_approval(self):
        group = self.team(count=2)
        member = group['members'][0]
        self.native.agents[member].update(status='running', pending_approvals=[dict(tool='pwsh', call_id='cleanup', reason='remove own empty directories', since=1)])
        status = self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='status'))
        self.assertEqual(status['member_runtime'][member]['pending_approvals'][0]['call_id'], 'cleanup')
        self.assertEqual(status['member_runtime'][member]['status'], 'running')
        self.native.agents[member]['pending_approvals'] = []
        self.assertEqual(self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='status'))['member_runtime'][member]['pending_approvals'], [])

    def start(self, group):
        self.release = Event()
        original = self.native.__class__.__call__
        release = self.release

        class Port(fixtures.NativePort):
            def __call__(native, name, p):
                if name == 'run' and p['actor'] in group['members']:
                    release.wait(10)
                    message = dict(id=p['actor'] + '-done', role='assistant', content=[dict(type='text', text='协作完毕')])
                    return dict(messages=[message], session_id=native.agents[p['actor']]['session_id'],completion='completed')
                if name == 'cancel-agent':
                    release.set()
                    return {'ok': True}
                return original(native, name, p)

        self.native.__class__ = Port
        receipt = self.invoke('datanet_cooperate', dict(group_id=group['group_id'], action='start', task='共同交付并验收', budget_minutes=1))
        self.assertEqual(receipt['status'], 'accepted')
        return receipt

    def tearDown(self):
        if hasattr(self, 'release'):
            self.release.set()
        fixtures.ApplicationTests.tearDown(self)

    def test_discussion_count_and_complete_round(self):
        group = self.discussion(7)
        self.assertEqual(group['member_count'], 7)
        self.assertEqual(len(group['members']), 9)
        self.assertEqual(len({self.app.state(m)['session_id'] for m in group['members']}), 9)
        result = self.invoke('datanet_discuss', dict(group_id=group['group_id'], task='所有成员提交并归档'))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(set(self.backend.groups['discussion']['submitted']), set(group['members']))
        for member in group['members']:
            self.assertNotIn(member + '_notes', self.backend.network.nodes)

    def test_minimum_count_and_invalid_count_before_mount(self):
        group = self.discussion(1)
        self.assertEqual(len(group['members']), 3)
        for invalid in (0, True, 1.5, 65):
            with self.assertRaises(ValueError):
                self.invoke('datanet_create_network', dict(preset='discussion_group', instance_id='invalid', project='资料', member_count=invalid))
            self.assertNotIn('invalid/board', self.backend.network.nodes)

    def test_python_template_entrypoint(self):
        from datanet.components.networks.discussion_group.setup import build_discussion_group
        network, mounted = build_discussion_group('manual', storage_dir=Path(self.temp.name) / 'manual', member_count=2)
        board = network.nodes[mounted.entry_points['board']]
        self.assertEqual(len(board.members), 4)
        self.assertEqual(len({network.nodes[m].file_path for m in board.members}), 4)

    def test_peers_claim_merge_and_quorum_completion(self):
        group = self.team()
        receipt = self.start(group)
        workers = group['members']
        outsider = self.team('outside', 1)['members'][0]
        with self.assertRaises(PermissionError):
            self.invoke('datanet_team_send', dict(target=outsider, content='越界'), workers[0])
        send = self.invoke('datanet_team_send', dict(target=workers[1], content='请负责第二个文件'), workers[0])
        self.assertEqual(send['status'], 'accepted')
        with self.assertRaises(PermissionError):
            self.invoke('datanet_send_message', dict(target=workers[1], content='普通管理通道不能横向发信'), workers[0])
        claims = []
        for i, worker in enumerate(workers):
            c = self.invoke('datanet_team_claim', dict(action='claim', scope=f'文件{i}'), worker)
            claims.append(c['id'])
            path = self.invoke('datanet_team_workspace', dict(action='inspect'), worker)['personal_path']
            Path(path, f'result{i}.txt').write_text('测试', encoding='utf-8')
            integrated = self.invoke('datanet_team_workspace', dict(action='publish', message=f'交付文件{i}'), worker)
            self.assertEqual(integrated['status'], 'integrated')
            duplicate = self.invoke('datanet_team_claim', dict(action='claim', scope=f'文件{i}'), workers[(i + 1) % len(workers)])
            self.assertTrue(duplicate['conflict'])
            self.assertEqual(duplicate['claim']['actor'], worker)
            self.invoke('datanet_team_claim', dict(action='complete', claim_id=c['id'], evidence=integrated['commit']), worker)
        note = self.invoke('datanet_team_note', dict(kind='FACT', content='三个文件已整合'), workers[0])
        state = self.invoke('datanet_team_status', dict(query='已整合'), workers[1])
        self.assertEqual(state['entries'][0]['id'], note['id'])
        self.assertEqual(state['run_id'], receipt['run_id'])
        proposal = self.invoke('datanet_team_finish', dict(action='propose', content='三个文件全部完成', evidence='共同工作区内逐个读取验证'), workers[0])
        self.assertEqual(proposal['phase'], 'review')
        candidate = proposal['candidate']['id']
        self.invoke('datanet_team_finish', dict(action='approve', candidate_id=candidate, evidence='三个文件内容正确'), workers[1])
        self.assertEqual(self.backend.cooperative_groups['team']['phase'], 'review')
        final = self.invoke('datanet_team_finish', dict(action='approve', candidate_id=candidate, evidence='验证完成'), workers[2])
        self.assertEqual(final['phase'], 'completed')
        messages = [m for m in self.native.messages['root'] if 'cooperation_result' in json.dumps(m)]
        self.assertEqual(len(messages), 1)
        workspace = self.app.plugins['capabilities/decentralized_group'].workspace(self.backend.cooperative_groups['team'])
        head = workspace.git(workspace.main, 'rev-parse', 'HEAD')['stdout'].strip()
        status = self.invoke('datanet_cooperate', dict(group_id='team', action='status'))
        self.assertEqual(status['repository']['head_commit'], head)
        self.assertIn(head, json.dumps(messages[0]))
        output = self.backend.network.nodes[final['output_id']].file_path.read_text(encoding='utf-8')
        self.assertEqual(output, '三个文件全部完成')
        root_output = self.invoke('node_read', dict(target=final['output_id'], request=dict(method='key', key='content'), strength=100))
        self.assertEqual(root_output['items'][0]['content'], '三个文件全部完成')
        self.release.set()
        queue = self.app.plugins['capabilities/agent_delegation']
        end = time.monotonic() + 5
        while any(j['status'] in ('queued', 'running') for j in queue.jobs.values()) and time.monotonic() < end:
            time.sleep(.01)
        self.assertFalse(any(j['status'] in ('queued', 'running') for j in queue.jobs.values()))
        self.assertFalse(any('delegation_result' in json.dumps(m) for m in self.native.messages['root']))
        self.assertEqual(len(queue.jobs), 3)

    def test_reject_stale_vote_budget_stop_and_restore(self):
        group = self.team(count=2)
        self.start(group)
        a, b = group['members']
        self.invoke('datanet_team_claim', dict(action='claim', scope='尚未结束'), a)
        with self.assertRaises(ValueError):
            self.invoke('datanet_team_finish', dict(action='propose', content='未完成', evidence='有任务未完成'), a)
        claim = next(iter(self.backend.cooperative_groups['team']['claims']))
        self.invoke('datanet_team_claim', dict(action='release', claim_id=claim), a)
        proposal = self.invoke('datanet_team_finish', dict(action='propose', content='候选', evidence='初步检查'), a)
        self.invoke('datanet_team_finish', dict(action='reject', candidate_id=proposal['candidate']['id'], evidence='缺少第三个文件'), b)
        self.assertEqual(self.backend.cooperative_groups['team']['phase'], 'running')
        with self.assertRaises(ValueError):
            self.invoke('datanet_team_finish', dict(action='approve', candidate_id=proposal['candidate']['id'], evidence='旧候选'), a)
        plugin = self.app.plugins['capabilities/decentralized_group']
        plugin.expire('team')
        self.assertEqual(self.backend.cooperative_groups['team']['phase'], 'budget_exhausted')
        self.assertIsNone(self.backend.cooperative_groups['team']['candidate'])
        self.release.set()
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        self.backend = fixtures.Backend(self.temp.name)
        saved = self.backend.dispatch('cooperative_status', dict(actor='root', group_id='team', strength=100))
        self.assertEqual(saved['phase'], 'budget_exhausted')
        self.assertTrue(saved['entries'])

    def test_workspace_conflict_retains_both_contributions(self):
        group = self.team(count=2)
        self.start(group)
        a, b = group['members']
        for actor, content in [(a, '版本A'), (b, '版本B')]:
            directory = self.invoke('datanet_team_workspace', dict(action='inspect'), actor)['personal_path']
            Path(directory, 'shared.txt').write_text(content, encoding='utf-8')
        self.assertEqual(self.invoke('datanet_team_workspace', dict(action='publish'), a)['status'], 'integrated')
        conflict = self.invoke('datanet_team_workspace', dict(action='publish'), b)
        self.assertEqual(conflict['status'], 'conflict')
        self.assertEqual(Path(conflict['integrated_path'], 'shared.txt').read_text(encoding='utf-8'), '版本A')
        own = self.invoke('datanet_team_workspace', dict(action='inspect'), b)['personal_path']
        self.assertEqual(Path(own, 'shared.txt').read_text(encoding='utf-8'), '版本B')
        self.invoke('datanet_cooperate', dict(group_id='team', action='stop'))

    def test_unplug_retains_state(self):
        self.team(count=1)
        self.app.disable('capabilities/decentralized_group')
        self.assertNotIn('datanet_cooperate', self.native.tools['root'])
        with self.assertRaises(PermissionError):
            self.invoke('datanet_cooperate', dict(group_id='team', action='start', task='不能运行'))
        self.assertIn('team', self.backend.cooperative_groups)

    def test_interrupted_workers_are_not_replayed_after_restart(self):
        group = self.team(count=2)
        queue = self.app.plugins['capabilities/agent_delegation']
        queue.start_worker = lambda target: None
        self.invoke('datanet_cooperate', dict(group_id='team', action='start', task='重启测试'))
        first = next(iter(queue.jobs.values()))
        first['status'] = 'running'
        queue.store.save()
        for plugin in self.app.plugins.values():
            if hasattr(plugin, 'close'):
                plugin.close()
        self.backend.close()
        self.backend = fixtures.Backend(self.temp.name)
        self.native = fixtures.NativePort()
        self.app = fixtures.Application(self.backend, self.native, dict(rootNetwork='project_root', rootToolboxes=['network_access','node_creation','agent_management'], maxSignalStrength=100))
        self.native.app = self.app
        self.app.plugins['capabilities/tools_network_management'].bind_root('root-session')
        self.app.event('root', 'agent/pre-step', dict(messages=[]))
        state = self.invoke('datanet_cooperate', dict(group_id='team', action='status'))
        self.assertEqual(state['phase'], 'interrupted')
        jobs = self.app.plugins['capabilities/agent_delegation'].jobs
        self.assertEqual({j['status'] for j in jobs.values()}, {'interrupted', 'cancelled'})
        self.assertFalse(any(name == 'run' for name, p in self.native.calls))

    def test_member_reuse_joins_new_group(self):
        old = self.team('old', count=2)
        self.invoke('datanet_interfaces_channel')
        pending = self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(target_node_id='old/board')))
        self.invoke('datanet_interfaces', dict(action='remove', arguments=dict(confirmation_id=pending['confirmation_id'], choice=3)))
        self.app.plugins['capabilities/agent_lifecycle'].settle()
        new = self.team('new', count=2)
        self.assertEqual(set(new['members']), set(old['members']))
        for member in new['members']:
            state = self.invoke('datanet_team_status', actor=member)
            self.assertEqual(state['group_id'], 'new')


if __name__ == '__main__':
    unittest.main()
