"""Cache-sensitive placement contracts; complete records remain queryable."""
import json, unittest
import test_application as fixtures
import test_cooperation as cooperation

class CachePlacementTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team

    def test_message_queries_and_short_notice_leave_no_automatic_contacts(self):
        group = self.team(count=2)
        member = group['members'][0]
        plugin = self.app.plugins['capabilities/agent_messaging']
        before = self.app.view(member)
        self.app.event(member, 'context/prepare', {})
        self.assertNotIn((member, 'state:contacts'), self.native.documents)
        self.assertNotIn((member, 'tool:datanet_messages'), self.native.documents)
        self.assertEqual(self.invoke('datanet_pending_messages', actor=member)['messages'], [])
        contacts = self.invoke('datanet_contacts_channel', actor=member)
        self.assertEqual(contacts['contacts'], ['root'])
        self.assertIn((member, 'tool:datanet_messages'), self.native.documents)
        self.assertFalse(self.invoke('datanet_contacts_channel', actor=member)['instructions_added'])
        self.native.documents.pop((member, 'tool:datanet_messages'))
        self.assertTrue(self.invoke('datanet_contacts_channel', actor=member)['instructions_added'])
        sent = plugin.deliver('root', member, '回复一次')
        self.assertEqual(before, self.app.view(member))
        tail = dict(actor=member, texts=[]); self.app.emit('context/tail', **tail)
        self.assertIn('存在待处理工单。', tail['texts'])
        self.assertNotIn(sent['message_id'], '\n'.join(tail['texts']))
        result = self.invoke('datanet_pending_messages', actor=member)['messages']
        self.assertEqual(result[0]['message_id'], sent['message_id'])
        self.assertEqual(result[0]['content'], '回复一次')
        self.invoke(result[0]['reply_tool'], {'content':'收到'}, member)
        tail['texts'].clear(); self.app.emit('context/tail', **tail)
        self.assertNotIn('存在待处理工单。', tail['texts'])
        self.assertEqual(self.invoke('datanet_pending_messages', actor=member)['messages'], [])
        self.assertEqual(before, self.app.view(member))

    def test_discussion_members_can_query_replies_without_active_contact_permission(self):
        self.invoke('datanet_create_network_channel', {'preset':'discussion_group'})
        group=self.invoke('datanet_create_network', {'preset':'discussion_group','instance_id':'reply','project':'资料','member_count':1,'rounds':1})
        member=group['members'][2]
        self.assertNotIn('datanet_contacts_channel', self.native.tools[member])
        self.assertNotIn('datanet_send_message', self.native.tools[member])
        with self.assertRaises(PermissionError):self.invoke('datanet_contacts_channel',actor=member)
        plugin=self.app.plugins['capabilities/agent_messaging']
        entry=plugin.deliver('root',member,'定向提问')
        pending=self.invoke('datanet_pending_messages',actor=member)['messages']
        self.assertEqual([row['message_id'] for row in pending],[entry['message_id']])
        plugin.expire(entry['message_id'])
        self.assertEqual(self.invoke('datanet_pending_messages',actor=member)['messages'],[])
        tail=dict(actor=member,texts=[]);self.app.emit('context/tail',**tail)
        self.assertNotIn('存在待处理工单。',tail['texts'])

    def test_discussion_count_and_problem_stage_are_ephemeral(self):
        group = self.team(count=1)
        member = group['members'][0]
        self.invoke('datanet_create_network_channel', {'preset':'discussion_group'})
        dg=self.invoke('datanet_create_network', {'preset':'discussion_group','instance_id':'discuss','project':'资料','member_count':1,'rounds':1})
        actor=dg['members'][0]
        discussion=self.app.plugins['capabilities/discussion_group']
        discussion.turns[actor].update(active=True,count=0,round=1,total=1)
        before=self.app.view(actor)
        self.app.event(actor,'agent/request',{})
        tail=dict(actor=actor,texts=[]);self.app.emit('context/tail',**tail)
        self.assertIn('当前请求次数：1/10', '\n'.join(tail['texts']))
        self.assertIn('当前轮数：1/1', '\n'.join(tail['texts']))
        self.assertEqual(before,self.app.view(actor))
        discussion.turns[actor]['active']=False
        self.invoke('handle_problem', {'problem':'依赖不可用','origin':'dependency'}, member)
        self.invoke('experience_query', actor=member)
        before=self.app.view(member)
        p=self.app.plugins['capabilities/problem_handling'].active(member)
        self.assertEqual(self.invoke('datanet_contacts_channel',actor=member)['contacts'],['root'])
        self.assertEqual(self.invoke('datanet_pending_messages',actor=member)['messages'],[])
        p['stage']='attempt_failed'
        tail=dict(actor=member,texts=[]);self.app.emit('context/tail',**tail)
        self.assertIn('阶段：attempt_failed','\n'.join(tail['texts']))
        self.assertEqual(before,self.app.view(member))
        self.app.event(member,'context/prepare',{})
        self.assertNotIn('当前问题：','\n'.join(v for (a,_),v in self.native.documents.items() if a==member))

    def test_large_shared_records_have_small_preview_and_full_id_lookup(self):
        group=self.team(count=1); actor=group['members'][0]
        self.app.plugins['capabilities/agent_delegation'].start_worker=lambda target:None
        self.invoke('datanet_cooperate',{'group_id':'team','action':'start','task':'TASK_LONG_'+'目标'*3000})
        content='FULL_RECORD_'+'记录'*10000
        note=self.invoke('datanet_team_note',{'kind':'FACT','content':content},actor)
        row=note.get('entry',note)
        tail=dict(actor=actor,texts=[]);self.app.emit('context/tail',**tail)
        text=next(t for t in tail['texts'] if t.startswith('[协作组：'))
        self.assertLess(len(text),100)
        self.assertNotIn(content[:160], text)
        self.assertNotIn(row['id'], text)
        result=self.invoke('datanet_team_status',{'section':'records','query':row['id']},actor)
        self.assertEqual(result['entries'][0]['content'],content)
        candidate=self.invoke('datanet_team_finish',{'action':'propose','content':'候选'*10000,'evidence':'提交验收'},actor)
        tail['texts'].clear();self.app.emit('context/tail',**tail)
        self.assertNotIn('目前有成果等待审核。', '\n'.join(tail['texts']))
        self.assertEqual(self.invoke('datanet_team_status',{'section':'candidate'},actor)['candidate']['content'],'候选'*10000)

if __name__=='__main__':unittest.main()
