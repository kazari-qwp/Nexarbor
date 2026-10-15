"""Focused workflow checks: optional replies, persistent receipts and scoped queries."""
import json, unittest
import test_application as fixtures
import test_cooperation as cooperation
import test_group_runs as runs

class MessageTailTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team
    reopen = runs.GroupRunTests.reopen

    def tail(self, actor):
        texts=[]
        self.app.emit('context/tail', actor=actor, texts=texts)
        return '\n'.join(texts)

    def test_work_order_replied_once_and_optional_reply_read_without_ack(self):
        group=self.team(count=2); a,b=group['members']; messaging=self.app.plugins['capabilities/agent_messaging']
        receipt=self.invoke('datanet_send_message', {'target':a,'content':'确认接口'}, 'root')
        self.assertIn('存在待处理工单。',self.tail(a))
        msg=self.invoke('datanet_pending_messages',actor=a)['messages'][0]
        self.assertEqual(msg['message_type'],'work_order')
        self.assertIn('存在待处理工单。',self.tail(a))
        answer=self.invoke(msg['reply_tool'],{'content':'接口已确定'},a)
        entry=messaging.store.data['messages'][answer['message_id']]
        self.assertEqual(entry['message_type'],'reply')
        self.assertTrue(self.native.messages['root'][-1]['content'][0]['text'].startswith('此为回复，可以不回。\n'))
        self.assertIn('存在未读回复。',self.tail('root'))
        original={'id':entry['inbox_id'],'role':'user'}
        self.app.event('root','context/admitted',{'message_ids':[original['id']]})
        self.assertNotIn('存在未读回复。',self.tail('root'))
        self.assertIn(entry['reply_tool'],self.native.tools['root'])
        self.assertEqual(self.invoke('datanet_pending_messages')['messages'][0]['notice'],'此为回复，可以不回。')
        self.assertNotIn('存在未读回复。',self.tail('root'))
        with self.assertRaises(PermissionError): self.invoke(msg['reply_tool'],{'content':'再回复'},a)
        self.invoke('datanet_pending_messages',{'action':'close','message_id':answer['message_id']})
        self.assertNotIn(entry['reply_tool'],self.native.tools['root'])

    def test_direct_optional_reply_query_marks_read_but_work_order_requires_close(self):
        a=self.team(count=1)['members'][0]
        sent=self.invoke('datanet_send_message',{'target':a,'content':'仅供参考','message_type':'reply'})
        self.assertIn('存在未读回复。',self.tail(a))
        reply=self.invoke('datanet_pending_messages',actor=a)['messages'][0]
        self.assertNotIn('存在未读回复。',self.tail(a))
        self.assertIn(reply['reply_tool'],self.native.tools[a])
        order=self.invoke('datanet_send_message',{'target':a,'content':'需要处理'})
        self.invoke('datanet_pending_messages',actor=a)
        self.assertIn('存在待处理工单。',self.tail(a))
        with self.assertRaises(ValueError):self.invoke('datanet_pending_messages',{'action':'close','message_id':order['message_id']})
        self.invoke('datanet_pending_messages',{'action':'close','message_id':order['message_id']},a)
        self.assertNotIn('存在待处理工单。',self.tail(a))

    def test_tail_is_constant_sized_and_review_notice_tracks_current_candidate(self):
        group=self.team(count=2);a,b=group['members']
        self.app.plugins['capabilities/agent_delegation'].start_worker=lambda target:None
        self.invoke('datanet_cooperate',{'group_id':'team','action':'start','task':'测试'})
        claim=self.invoke('datanet_team_claim',{'action':'claim','scope':'工作'*1000,'paths':['src/a.py']},a)
        note=self.invoke('datanet_team_note',{'kind':'FACT','content':'记录'*10000},a)
        tail=self.tail(b)
        self.assertEqual(tail,'[协作组：team]\n阶段：执行。')
        self.assertEqual(self.invoke('datanet_team_status',{'section':'records','query':note['id']},b)['entries'][0]['content'],'记录'*10000)
        self.assertEqual(set(self.invoke('datanet_team_status',{'section':'claims'},b)),{'group_id','phase','claims'})
        self.assertIn('task',self.invoke('datanet_team_status',{'section':'summary'},b))
        self.invoke('datanet_team_claim',{'action':'complete','claim_id':claim['id'],'evidence':'完成'},a)
        proposal=self.invoke('datanet_team_finish',{'action':'propose','content':'成果','evidence':'自测完成'},a)
        self.assertNotIn('目前有成果等待审核。',self.tail(a))
        self.assertIn('目前有成果等待审核。',self.tail(b))
        candidate=proposal['candidate']['id']
        self.assertIn('review',self.invoke('datanet_team_status',{'section':'candidate'},b)['candidate'])
        self.invoke('datanet_team_finish',{'action':'reject','candidate_id':candidate,'evidence':'补充边界'},b)
        next_candidate=self.invoke('datanet_team_finish',{'action':'propose','content':'修正成果','evidence':'已补充'},b)['candidate']['id']
        self.assertNotEqual(candidate,next_candidate)
        self.assertIn('目前有成果等待审核。',self.tail(a))
        self.assertNotIn('目前有成果等待审核。',self.tail(b))
        self.invoke('datanet_team_finish',{'action':'approve','candidate_id':next_candidate,'evidence':'通过'},a)
        self.assertNotIn('目前有成果等待审核。',self.tail(a))
        self.invoke('datanet_cooperate',{'group_id':'team','action':'stop'})

    def test_read_state_survives_restore_and_legacy_messages_get_types(self):
        a=self.team(count=1)['members'][0]
        order=self.invoke('datanet_send_message',{'target':a,'content':'请答复'})
        plugin=self.app.plugins['capabilities/agent_messaging']
        original=plugin.store.data['messages'][order['message_id']]
        reply=self.invoke(original['reply_tool'],{'content':'已完成'},a)
        entry=plugin.store.data['messages'][reply['message_id']]
        entry.pop('message_type');entry.pop('read_at');plugin.store.save()
        self.reopen()
        plugin=self.app.plugins['capabilities/agent_messaging']
        self.assertEqual(plugin.store.data['messages'][reply['message_id']]['message_type'],'reply')
        self.assertIn('存在未读回复。',self.tail('root'))
        self.invoke('datanet_pending_messages')
        self.reopen()
        self.assertNotIn('存在未读回复。',self.tail('root'))
        entry=self.app.plugins['capabilities/agent_messaging'].store.data['messages'][reply['message_id']]
        self.assertIn(entry['reply_tool'],self.native.tools['root'])

    def test_peer_message_type_is_forwarded(self):
        group=self.team(count=2);a,b=group['members']
        self.app.plugins['capabilities/agent_delegation'].start_worker=lambda target:None
        self.invoke('datanet_cooperate',{'group_id':'team','action':'start','task':'测试'})
        message=self.invoke('datanet_team_send',{'target':b,'content':'无需回复','message_type':'reply'},a)
        plugin=self.app.plugins['capabilities/agent_messaging']
        self.assertEqual(plugin.store.data['messages'][message['message_id']]['message_type'],'reply')
        self.assertIn('存在未读回复。',self.tail(b))
        self.invoke('datanet_pending_messages',actor=b)
        self.assertNotIn('存在未读回复。',self.tail(b))
        self.invoke('datanet_cooperate',{'group_id':'team','action':'stop'})

if __name__=='__main__':unittest.main()
