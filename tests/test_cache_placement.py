"""Cache-sensitive placement contracts; complete records remain queryable."""
import json, unittest
import test_application as fixtures
import test_cooperation as cooperation

class CachePlacementTests(unittest.TestCase):
    setUp = fixtures.ApplicationTests.setUp
    tearDown = fixtures.ApplicationTests.tearDown
    invoke = fixtures.ApplicationTests.invoke
    team = cooperation.CooperationTests.team

    def test_message_pending_changes_do_not_replace_system(self):
        group = self.team(count=2)
        member = group['members'][0]
        plugin = self.app.plugins['toolboxes/agent_messaging']
        before = self.app.view(member)
        self.app.event(member, 'context/prepare', {})
        contacts = self.native.documents[(member, 'state:contacts')]
        self.assertIn('root', contacts)
        sent = plugin.deliver('root', member, '回复一次')
        after = self.app.view(member)
        self.assertEqual(before, after)
        tail = dict(actor=member, texts=[])
        self.app.emit('context/tail', **tail)
        self.assertIn(sent['message_id'], '\n'.join(tail['texts']))
        self.assertNotIn(sent['message_id'], '\n'.join(v for (actor, _), v in self.native.documents.items() if actor==member))
        entry = plugin.pending(member)[0]
        plugin.invoke(member, entry['reply_tool'], {'content':'收到'})
        tail['texts'].clear(); self.app.emit('context/tail', **tail)
        self.assertNotIn(sent['message_id'], '\n'.join(tail['texts']))
        self.assertEqual(before, self.app.view(member))
        self.app.event(member, 'context/prepare', {})
        self.assertEqual(contacts, self.native.documents[(member, 'state:contacts')])

    def test_discussion_count_and_problem_stage_are_ephemeral(self):
        group = self.team(count=1)
        member = group['members'][0]
        self.invoke('datanet_create_network_channel', {'preset':'discussion_group'})
        dg=self.invoke('datanet_create_network', {'preset':'discussion_group','instance_id':'discuss','project':'资料','member_count':1,'rounds':1})
        actor=dg['members'][0]
        discussion=self.app.plugins['network_presets/discussion_group']
        discussion.turns[actor].update(active=True,count=0)
        before=self.app.view(actor)
        self.app.event(actor,'agent/request',{})
        tail=dict(actor=actor,texts=[]);self.app.emit('context/tail',**tail)
        self.assertIn('当前请求次数：1/10', '\n'.join(tail['texts']))
        self.assertEqual(before,self.app.view(actor))
        discussion.turns[actor]['active']=False
        self.invoke('handle_problem', {'problem':'依赖不可用','origin':'dependency'}, member)
        self.invoke('experience_query', actor=member)
        before=self.app.view(member)
        p=self.app.plugins['toolboxes/problem_handling'].active(member)
        p['stage']='attempt_failed'
        tail=dict(actor=member,texts=[]);self.app.emit('context/tail',**tail)
        self.assertIn('阶段：attempt_failed','\n'.join(tail['texts']))
        self.assertEqual(before,self.app.view(member))
        self.app.event(member,'context/prepare',{})
        self.assertNotIn('当前问题：','\n'.join(v for (a,_),v in self.native.documents.items() if a==member))

    def test_large_shared_records_have_small_preview_and_full_id_lookup(self):
        group=self.team(count=1); actor=group['members'][0]
        self.app.plugins['tools/agent_delegation'].start_worker=lambda target:None
        self.invoke('datanet_cooperate',{'group_id':'team','action':'start','task':'TASK_LONG_'+'目标'*3000})
        content='FULL_RECORD_'+'记录'*10000
        note=self.invoke('datanet_team_note',{'kind':'FACT','content':content},actor)
        row=note.get('entry',note)
        tail=dict(actor=actor,texts=[]);self.app.emit('context/tail',**tail)
        text=next(t for t in tail['texts'] if t.startswith('[协作状态：'))
        state=json.loads(text.split('\n',1)[1])
        self.assertNotIn('task',state);self.assertLess(len(text),1500)
        preview=state['recent_entries'][-1]
        self.assertEqual(len(preview['preview']),160)
        result=self.invoke('datanet_team_status',{'query':preview['id']},actor)
        self.assertEqual(result['entries'][0]['content'],content)
        candidate=self.invoke('datanet_team_finish',{'action':'propose','content':'候选'*10000,'evidence':'提交验收'},actor)
        tail['texts'].clear();self.app.emit('context/tail',**tail)
        state=json.loads(next(t for t in tail['texts'] if t.startswith('[协作状态：')).split('\n',1)[1])
        self.assertNotIn('content',state['candidate'])
        self.assertIn('review',state['candidate'])
        self.assertEqual(self.invoke('datanet_team_status',actor=actor)['candidate']['content'],'候选'*10000)

if __name__=='__main__':unittest.main()
