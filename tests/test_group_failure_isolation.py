"""Failure isolation, loss thresholds and surviving member completion."""
import json, unittest
from collections import Counter
import test_application as fixtures
import test_cooperation as cooperation

class GroupFailureTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team

    def begin_team(self, count):
        group = self.team(count=count)
        queue = self.app.plugins['tools/agent_delegation']
        queue.start_worker = lambda target: None
        self.invoke('datanet_cooperate', dict(group_id='team', action='start', task='自主交付并验收'))
        return group, self.backend.cooperative_groups['team']

    def fail(self, g, member):
        queue = self.app.plugins['tools/agent_delegation']
        id = g['jobs'][member]
        queue.jobs[id].update(status='failed', result=dict(status='failed', error='MALFORMED_RESPONSE: invalid JSON'))
        queue.store.save()
        self.app.emit('delegation/settled', actor=member, delegation_id=id)

    def notices(self, kind):
        found = []
        for name,p in self.native.calls:
            if name != 'steer': continue
            try: value = json.loads(p.get('text', ''))
            except (ValueError, TypeError): continue
            if value.get('type') == kind: found.append((p['actor'],value))
        return found

    def test_loss_releases_claims_and_survivors_complete_with_one_notice(self):
        group,g = self.begin_team(4);a,b,c,d = group['members']
        personal = self.app.plugins['network_presets/decentralized_group'].workspace(g).personal(a)
        preserved = personal / 'unfinished.py';preserved.write_text('valuable partial work',encoding='utf-8')
        claim = self.invoke('datanet_team_claim',dict(action='claim',scope='实现',paths=['src/main.py']),a)
        self.fail(g,a)
        self.assertEqual(g['phase'],'running');self.assertEqual(g['claims'][claim['id']]['state'],'released')
        self.assertEqual(preserved.read_text(encoding='utf-8'),'valuable partial work')
        self.assertFalse(self.notices('cooperation_degraded'))
        replacement = self.invoke('datanet_team_claim',dict(action='claim',scope='实现',paths=['src/main.py']),c)
        self.invoke('datanet_team_claim',dict(action='complete',claim_id=replacement['id'],evidence='接续完成'),c)
        self.fail(g,b);self.fail(g,b)
        self.assertEqual(g['phase'],'running');self.assertEqual(len(self.notices('cooperation_degraded')),1)
        recipient,notice = self.notices('cooperation_degraded')[0]
        self.assertEqual(recipient,'root');self.assertEqual(notice['exited_count'],2)
        self.assertEqual(notice['active_members'],[c,d])
        self.assertFalse(any(name=='cancel-agent' and p['actor'] in (c,d) for name,p in self.native.calls))
        candidate=self.invoke('datanet_team_finish',dict(action='propose',content='成果',evidence='已验证'),c)['candidate']
        with self.assertRaises(PermissionError):self.invoke('datanet_team_finish',dict(action='approve',candidate_id=candidate['id'],evidence='迟到'),a)
        result=self.invoke('datanet_team_finish',dict(action='approve',candidate_id=candidate['id'],evidence='通过'),d)
        self.assertEqual(result['phase'],'completed')
        status=self.invoke('datanet_cooperate',dict(group_id='team',action='status'))
        self.assertEqual(status['members'],[a,b,c,d]);self.assertEqual(status['active_members'],[c,d])
        self.assertEqual(set(status['unavailable']),{a,b})
        archive=json.loads((self.backend.directory/g['archive_path']/'run.json').read_text(encoding='utf-8'))
        self.assertEqual(set(archive['unavailable']),{a,b})
        self.invoke('datanet_cooperate',dict(group_id='team',action='start',task='新任务'))
        self.assertEqual(g['unavailable'],{});self.assertFalse(g['loss_notice_sent'])

    def test_native_fatal_event_retires_before_delegation_settles(self):
        group,g=self.begin_team(2);a,b=group['members']
        queue=self.app.plugins['tools/agent_delegation'];queue.jobs[g['jobs'][a]]['status']='running'
        self.app.emit('agent/error',actor=a,error='parser stopped',failure=dict(code='MALFORMED_RESPONSE',message='tool input is invalid JSON'))
        self.assertIn(a,g['unavailable']);self.assertEqual(g['phase'],'running')
        self.assertEqual(queue.jobs[g['jobs'][a]]['status'],'running')
        self.invoke('datanet_team_finish',dict(action='propose',content='剩余成员完成',evidence='完整验证'),b)
        with self.assertRaisesRegex(RuntimeError,'成员已退出本轮协作'):self.app.emit('agent/pre-step',actor=a,messages=[])

    def test_last_remaining_member_can_propose_and_complete(self):
        group,g=self.begin_team(3);a,b,c=group['members']
        self.fail(g,a);self.assertFalse(self.notices('cooperation_degraded'))
        self.fail(g,b);self.assertEqual(g['phase'],'running')
        self.assertEqual(len(self.notices('cooperation_degraded')),1)
        result=self.invoke('datanet_team_finish',dict(action='propose',content='单人完成',evidence='完整验收'),c)
        self.assertEqual(result['phase'],'completed')

    def test_exit_during_review_does_not_wait_for_dead_reviewer(self):
        group,g=self.begin_team(2);a,b=group['members']
        self.invoke('datanet_team_finish',dict(action='propose',content='有效候选',evidence='证据'),a)
        self.assertEqual(g['phase'],'review')
        self.fail(g,b);self.assertEqual(g['phase'],'completed')
        self.assertEqual(len(self.notices('cooperation_result')),1)

    def test_only_all_failed_terminates_group_and_preserves_reason(self):
        group,g=self.begin_team(2);a,b=group['members']
        self.fail(g,a);self.assertEqual(g['phase'],'running')
        self.fail(g,b);self.assertEqual(g['phase'],'failed')
        self.assertIn('MALFORMED_RESPONSE',g['failure'])
        self.assertEqual(self.notices('cooperation_result')[0][1]['status'],'failed')

    def test_member_request_budget_is_local_and_stale_run_cannot_retire_member(self):
        group,g=self.begin_team(2);a,b=group['members'];old_id=g['jobs'][a]
        self.app.config['cooperativeRequestLimit']=1;g['requests'][a]=1
        with self.assertRaisesRegex(RuntimeError,'成员请求预算'):self.app.emit('agent/request',actor=a)
        self.assertEqual(g['phase'],'running');self.assertIn(a,g['unavailable'])
        self.assertFalse(any(name=='cancel-agent' and p['actor']==b for name,p in self.native.calls))
        self.invoke('datanet_team_finish',dict(action='propose',content='完成',evidence='验证'),b)
        self.invoke('datanet_cooperate',dict(group_id='team',action='start',task='下一轮'))
        self.app.emit('delegation/settled',actor=a,delegation_id=old_id)
        self.assertEqual(g['unavailable'],{})

    def discussion_faults(self, faulty):
        self.invoke('datanet_create_network_channel',dict(preset='discussion_group'))
        group=self.invoke('datanet_create_network',dict(preset='discussion_group',instance_id='discussion',project='讨论目标',member_count=3,rounds=2))
        original=self.native.__class__.__call__;counts=Counter()
        class Port(fixtures.NativePort):
            def __call__(native,name,p):
                if name=='run':
                    counts[p['actor']]+=1
                    if p['actor'] in faulty:raise RuntimeError('MALFORMED_RESPONSE: '+p['actor'])
                return original(native,name,p)
        self.native.__class__=Port
        return group,counts

    def test_all_ordinary_members_can_exit_and_new_task_reenables_them(self):
        faulty={f'discussion/member_{i}' for i in range(1,4)};group,counts=self.discussion_faults(faulty)
        result=self.invoke('datanet_discuss',dict(group_id='discussion',task='只剩主持与记录'))
        self.assertEqual(result['status'],'ok');self.assertEqual(set(result['unavailable']),faulty)
        self.assertTrue(self.backend.groups['discussion']['completed'])
        self.assertEqual(counts['discussion/leader'],2);self.assertEqual(counts['discussion/recorder'],3)
        for member in faulty:self.assertEqual(counts[member],1)
        notice=self.notices('discussion_degraded');self.assertEqual(len(notice),1)
        self.assertEqual(notice[0][0],'root');self.assertEqual(notice[0][1]['total_ordinary_members'],3)
        self.assertEqual(notice[0][1]['exited_count'],2)
        self.assertFalse(any(name=='cancel-agent' for name,p in self.native.calls))
        faulty.clear();again=self.invoke('datanet_discuss',dict(group_id='discussion',task='全员重新参与'))
        self.assertEqual(again['unavailable'],{});self.assertNotEqual(result['run_id'],again['run_id'])
        self.assertEqual(len(self.notices('discussion_degraded')),1)

    def test_discussion_leader_failure_is_not_misreported_as_completion(self):
        group,counts=self.discussion_faults({'discussion/leader'})
        with self.assertRaisesRegex(RuntimeError,'MALFORMED_RESPONSE'):self.invoke('datanet_discuss',dict(group_id='discussion',task='核心角色失败'))
        self.assertFalse(self.backend.groups['discussion']['completed'])
        self.assertFalse(self.notices('discussion_degraded'))

    def test_execution_records_keep_original_native_error_code(self):
        diagnostics=self.app.plugins['tools/execution_records'];diagnostics.start('root')
        self.app.emit('agent/error',actor='root',error='native stream failure',failure=dict(code='MALFORMED_RESPONSE',message='tool input is invalid JSON'))
        with self.assertRaisesRegex(RuntimeError,'MALFORMED_RESPONSE: tool input is invalid JSON'):diagnostics.complete('root',[])

if __name__=='__main__':unittest.main()
