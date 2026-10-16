"""Host-independent four-surface input contract and persistence."""
import tempfile,unittest
from pathlib import Path
from datanet.core.agent_node import AgentNode
from datanet.core.agent_inputs import AgentInputs
from datanet.core.network import Network
from datanet.core.serialization import save_network,load_network

class InputTests(unittest.TestCase):
    def test_partial_updates_source_isolation_and_clear(self):
        value=AgentInputs();value.update('persona',dict(system_prompt='fixed',tail=['A']))
        value.update('clock',dict(tail=['now']));value.update('persona',dict(context=[dict(id='doc',text='facts')]))
        self.assertEqual(value.snapshot()['persona']['system_prompt'],'fixed')
        value.update('persona',dict(system_prompt='',tail=[]))
        self.assertEqual(value.tail(),['now']);self.assertEqual(value.snapshot()['persona']['context'][0]['text'],'facts')
        before=value.snapshot()
        with self.assertRaises(ValueError):value.update('persona',dict(system_prompt='must rollback',context=[dict(id='x',text=2)]))
        self.assertEqual(value.snapshot(),before)
    def test_all_four_surfaces_accept_actual_document_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.md';path.write_text('实际文档正文',encoding='utf-8');ref=dict(file=str(path))
            value=AgentInputs();value.update('files',dict(system_prompt=ref,context=[dict(id='guide',text=ref)],inputs=[dict(id='job',text=ref)],tail=[ref]))
            snap=value.snapshot()['files']
            self.assertEqual(snap['system_prompt'],'实际文档正文');self.assertEqual(snap['context'][0]['text'],'实际文档正文')
            self.assertEqual(snap['inputs'][0]['text'],'实际文档正文');self.assertEqual(snap['tail'],['实际文档正文'])
    def test_event_identity_and_checkpoint_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            n=Network();node=AgentNode('a','Agent',file_path=Path(folder)/'memory.md');n.add_node(node)
            node.update_inputs('producer',inputs=[dict(id='event',text='task')],system_prompt='persona')
            node.inputs.acknowledge('producer','event');node.update_inputs('producer',inputs=[dict(id='event',text='task')])
            self.assertEqual(node.inputs.pending(),[])
            with self.assertRaises(ValueError):node.update_inputs('producer',inputs=[dict(id='event',text='different task')])
            node.update_inputs('producer',inputs=[dict(id='event2',text='task')])
            file=Path(folder)/'network.json';save_network(n,file);restored=load_network(file).nodes['a']
            self.assertEqual(restored.inputs.snapshot(),node.inputs.snapshot());self.assertEqual(len(restored.inputs.pending()),1)
            self.assertEqual(restored.inputs.pending()[0][1]['id'],'event2')

    def test_optional_executor_consumes_four_surfaces_without_assembler(self):
        import sys,json
        root=Path(__file__).resolve().parents[1];sys.path.append(str(root/'executors/minimal/python'))
        import datanet
        from pkgutil import extend_path
        datanet.__path__=extend_path(datanet.__path__,datanet.__name__)
        from datanet.core.execution import ExecutorRegistry
        from datanet.executors.minimal.runtime import MinimalExecutor,ModelClient
        requests=[]
        def reply(request,timeout):
            requests.append(request);return {'choices':[{'message':{'role':'assistant','content':'ok'}}]}
        with tempfile.TemporaryDirectory() as folder:
            n=Network();node=AgentNode('a','Agent',file_path=Path(folder)/'memory.md');n.add_node(node)
            node.update_inputs('host',system_prompt='fixed persona',context=[dict(id='guide',text='context material')],inputs=[dict(id='job',text='event input')],tail=['current clock'])
            executor=MinimalExecutor(ModelClient(reply),directory=Path(folder)/'sessions');r=ExecutorRegistry(n);r.register('minimal',executor);r.bind('a','minimal','session')
            self.assertEqual(r.run('a','task').status,'completed');self.assertEqual(node.inputs.pending(),[])
            self.assertEqual(r.run('a','next task').status,'completed')
            for request in requests:
                wire=json.dumps(request,ensure_ascii=False)
                for text in ['fixed persona','context material','event input','current clock']:self.assertIn(text,wire)
                self.assertEqual(wire.count('context material'),1);self.assertEqual(wire.count('event input'),1);self.assertEqual(wire.count('current clock'),1)
            history=next((Path(folder)/'sessions').glob('*/messages.json')).read_text(encoding='utf-8');self.assertNotIn('current clock',history)

if __name__=='__main__':unittest.main()
