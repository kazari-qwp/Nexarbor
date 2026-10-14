"""Discussion context deduplication, shared draft permissions and durable text limits."""
import json,unittest
import test_application as fixtures

class DiscussionContextTests(unittest.TestCase):
    setUp=fixtures.ApplicationTests.setUp
    tearDown=fixtures.ApplicationTests.tearDown
    invoke=fixtures.ApplicationTests.invoke

    def group(self):
        self.invoke('datanet_create_network_channel',dict(preset='discussion_group'))
        return self.invoke('datanet_create_network',dict(preset='discussion_group',instance_id='discussion',project='资料',member_count=4,rounds=2))

    def test_members_query_shared_draft_only_recorder_writes(self):
        group=self.group();b=self.backend.groups['discussion']['board'];rec=b.recorder_id
        self.backend.network.nodes[b.output_id].write('content','草稿细节')
        for actor in group['members']:
            bindings=self.backend.dispatch('text_bindings',dict(actor=actor,strength=2))
            self.assertIn(b.output_id,[n['node_id'] for n in bindings['read'] if n['delivery']=='query'])
            tool=next(name for name,target in self.app.plugins['nodes/text'].targets[actor].items() if target==b.output_id)
            self.invoke(tool,{},actor)
            self.assertIn('草稿细节',self.native.documents[(actor,'query-text:'+b.output_id)])
            if actor!=rec:
                result=self.backend.dispatch('write',dict(actor=actor,target=b.output_id,key='content',value='越权',strength=2))
                self.assertEqual(result.status,'forbidden')
        receipt=self.invoke('node_write',dict(target=b.output_id,key='content',value='草稿修订'),rec)
        self.assertNotIn('草稿修订',json.dumps(receipt,ensure_ascii=False))
        self.assertEqual(self.backend.network.nodes[b.output_id]._read_key('content').items[0]['content'],'草稿修订')

    def test_public_note_limit_rejects_overflow_and_append_without_changes(self):
        self.group();b=self.backend.groups['discussion']['board'];node=self.backend.network.nodes[b.notebook_id]
        self.assertEqual(node.max_chars,200)
        result=self.invoke('write_resident_text',dict(content='字'*200),b.recorder_id)
        self.assertEqual(result['status'],'ok')
        for tool,p in [('write_resident_text',dict(content='字'*201)),('write_resident_text',dict(content='字',mode='append')),('node_write',dict(target=b.notebook_id,key='content',value='字'*201))]:
            with self.assertRaises(RuntimeError) as failure:
                self.invoke(tool,p,b.recorder_id)
            self.assertIn('201',str(failure.exception))
            self.assertEqual(node._read_key('content').items[0]['content'],'字'*200)
        from datanet.components.nodes.text_file_node import codec
        params=codec.encode(node,self.backend.directory)
        restored=codec.decode((node.node_id,node.name,node.data_kind),params,self.backend.directory)
        self.assertEqual(restored.max_chars,200)
        self.assertEqual(restored.write('content','字'*201).status,'error')

    def test_round_messages_and_receipts_retain_archive_without_self_echo(self):
        group=self.group();self.backend.dispatch('group_begin',dict(group_id='discussion',task='唯一任务',caller='root'))
        first=self.backend.dispatch('start_round',dict(group_id='discussion'));plugin=self.app.plugins['network_presets/discussion_group'];info=self.backend.dispatch('group_info',dict(group_id='discussion'))
        self.assertIn('唯一任务',plugin.round_message('唯一任务',info,first,group['members'][0]))
        for member in group['members']:
            result=self.backend.dispatch('submit',dict(group_id='discussion',actor=member,content='发言:'+member))
            self.assertNotIn('content',result);self.assertEqual(result['round'],1)
        archived=self.backend.dispatch('finish_round',dict(group_id='discussion'))
        second=self.backend.dispatch('start_round',dict(group_id='discussion'))
        for member in group['members']:
            message=plugin.round_message('唯一任务',info,second,member)
            self.assertNotIn('唯一任务',message)
            for peer in group['members']:
                self.assertEqual(('发言:'+peer) in message,peer!=member)
        self.assertEqual(len(archived['submissions']),len(group['members']))
        resumed=self.backend.dispatch('start_round',dict(group_id='discussion'))
        self.assertEqual(second['previous_submitted'],resumed['previous_submitted'])

    def test_complete_discussion_still_returns_full_final_artifact(self):
        self.group();result=self.invoke('datanet_discuss',dict(group_id='discussion',task='交付完整成果'))
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['result']['items'][0]['content'],'全部测试完成')
        self.assertTrue(self.backend.groups['discussion']['completed'])

if __name__=='__main__':unittest.main(verbosity=2)
