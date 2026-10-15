"""Four-part boundaries and executor behavior, with isolated import registries."""
import json, os, subprocess, sys, textwrap, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class FourPartTests(unittest.TestCase):
    def isolated(self, code, minimal=False):
        env = dict(os.environ, PYTHONPATH=str(ROOT/'python'), PYTHONDONTWRITEBYTECODE='1')
        for key in ('DATANET_COMPONENT_ROOT','DATANET_COMPONENT_PROFILE','DATANET_EXECUTORS'):
            env.pop(key, None)
        env['DATANET_PRODUCT_ROOT'] = str(ROOT)
        if minimal:
            env['DATANET_EXECUTORS'] = '["minimal"]'
        value = subprocess.run([sys.executable,'-c',textwrap.dedent(code)],cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
        self.assertEqual(value.returncode,0,value.stdout+value.stderr)

    def test_core_agent_and_text_roundtrip_without_extensions(self):
        self.isolated('''
            import tempfile,sys
            from pathlib import Path
            from datanet.core.component_registry import codecs
            from datanet.core.agent_node import AgentNode
            from datanet.core.text_node import TextFileNode
            from datanet.core.network import Network
            from datanet.core.serialization import save_network,load_network
            assert set(codecs())=={'node','text_file','agent'},set(codecs())
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);network=Network()
                agent=AgentNode('worker','Worker',file_path=root/'memory.md')
                network.add_node(agent);agent.write_memory('remember')
                network.add_node(TextFileNode('text','Text',None,root/'text.md'))
                save_network(network,root/'network.json')
                restored=load_network(root/'network.json')
                assert restored.nodes['worker'].read_memory()['content']=='remember'
                assert type(restored.nodes['worker']) is AgentNode
            assert not any('abilities' in key or 'features' in key or 'executors.minimal' in key for key in sys.modules)
        ''')

    def test_frozen_module_uses_declared_resource_directory(self):
        self.isolated("""
            import os
            from pathlib import Path
            root=Path.cwd()
            os.environ['DATANET_COMPONENT_ROOT']=str(root/'extensions/multi_agent')
            from datanet.core.component_registry import resource_directory
            module=Path('datanet/components/nodes/llamaindex_node/preprocessing/semantic_annotation.py')
            frozen=root/'build/frozen/_internal'/module
            resolved=resource_directory(frozen)/'prompts/paragraph_attribution.md'
            assert resolved.exists(),resolved
            assert resolved.is_relative_to(root/'extensions/storage/nodes/llamaindex')
        """)

    def test_only_capabilities_contain_extension_code(self):
        package=ROOT/'extensions/multi_agent'
        for file in package.rglob('*'):
            if file.suffix in ('.py','.js','.cjs','.mjs'):
                self.assertEqual(file.relative_to(package).parts[0],'capabilities',str(file))
        from datanet.component_catalog import discover, tool_bindings
        catalog=discover(package)
        bindings=tool_bindings(catalog,list(catalog))
        for file in (package/'toolboxes').glob('*/box.json'):
            box=json.loads(file.read_text(encoding='utf8'))
            self.assertLessEqual(set(box),{'id','description','tools'},str(file))
            self.assertTrue(all(isinstance(tool,str) for tool in box['tools']))
            self.assertTrue(all(bindings[tool]['source'] in ('harness','datanet') for tool in box['tools']))

    def test_optional_executor_tool_authority_history_and_restore(self):
        self.isolated('''
            import tempfile,json
            from pathlib import Path
            from datanet.core.execution import ExecutionRequest,ExecutorRegistry
            from datanet.core.agent_node import AgentNode
            from datanet.core.network import Network
            from datanet.core.serialization import save_network,load_network
            from datanet.executors.minimal.runtime import MockExecutor
            def response(content=None,calls=None):
                message={'role':'assistant','content':content}
                if calls:message['tool_calls']=calls
                return {'choices':[{'message':message}]}
            calls=[{'id':'one','type':'function','function':{'name':'add','arguments':'{"value":2}'}}]
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);network=Network();node=AgentNode('worker','Worker',file_path=root/'memory.md');network.add_node(node)
                seen=[]
                node.register_agent_tool('add',lambda value:seen.append(value) or value+1,description='Add one',parameters={'type':'object','properties':{'value':{'type':'integer'}},'required':['value']})
                executor=MockExecutor([response(calls=calls),response('done'),response('again')],directory=root/'sessions')
                registry=ExecutorRegistry(network);registry.register('mock',executor);registry.bind('worker','mock','session',['add'])
                value=registry.run('worker','calculate')
                assert value.status=='completed' and value.steps==2,(value.status,value.error)
                assert seen==[2]
                echo={'id':'echo','type':'function','function':{'name':'echo','arguments':'{\"name\":\"safe\"}'}}
                node.register_agent_tool('echo',lambda name:name,description='Echo',parameters={'type':'object','properties':{'name':{'type':'string'}},'required':['name']})
                echo_executor=MockExecutor([response(calls=[echo]),response('echoed')],directory=root/'echo')
                registry.register('echo',echo_executor);registry.bind('worker','echo','echo',['echo'])
                assert registry.run('worker','echo').status=='completed'
                assert 'safe' in echo_executor.agents['echo'].messages[-2]['content']
                registry.bind('worker','mock','session',['add'])
                executor.send('session','queued while idle')
                assert registry.run('worker','continue').status=='completed'
                messages=executor.agents['session'].messages
                assert any(m.get('content')=='queued while idle' for m in messages)
                assert sum(m['role']=='user' for m in messages)==3
                save_network(network,root/'network.json');restored=load_network(root/'network.json')
                assert restored.nodes['worker'].execution_binding['executor']=='mock'
                try:registry.bind('worker','mock','session',['hidden'])
                except ValueError:pass
                else:raise AssertionError('unregistered tool accepted')
        ''',minimal=True)

    def test_optional_executor_budgets_cancellation_and_message_delivery(self):
        self.isolated('''
            import tempfile,threading,time
            from datanet.core.execution import ExecutionRequest
            from datanet.executors.minimal.runtime import MinimalExecutor,ModelClient,MockExecutor
            started=threading.Event();release=threading.Event()
            def complete(request,timeout):
                started.set();assert release.wait(2)
                return {'choices':[{'message':{'role':'assistant','content':'late'}}]}
            with tempfile.TemporaryDirectory() as folder:
                executor=MinimalExecutor(ModelClient(complete),directory=folder);result=[]
                thread=threading.Thread(target=lambda:result.append(executor.run(ExecutionRequest('s','n','work'),{})))
                thread.start();assert started.wait(2)
                assert executor.run(ExecutionRequest('s','n','duplicate'),{}).status=='busy'
                assert executor.cancel('s');release.set();thread.join(2)
                assert result[0].status=='canceled',result[0]
                def slow(request,timeout):
                    time.sleep(.03)
                    return {'choices':[{'message':{'role':'assistant','content':'late'}}]}
                timed=MinimalExecutor(ModelClient(slow),directory=folder)
                assert timed.run(ExecutionRequest('timeout','n','work',timeout_seconds=.01),{}).status=='timeout'
        ''',minimal=True)

if __name__=='__main__':unittest.main()
