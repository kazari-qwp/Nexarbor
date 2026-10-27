"""原短命令经新核心装配，真实工具发现、依赖和隔离网络测试。"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import asyncio
import time
from tempfile import TemporaryDirectory
import unittest
from app.runtime.backend import Backend
from app.studio.service import Studio
from app.studio.network_work import validate_network
from app.studio.network_testing import NetworkHarness
from domain.core import Network
ROOT=Path(__file__).resolve().parents[1]
class NetworkWork(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=TemporaryDirectory(prefix='studio-network-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        component=self.root/'counter';component.mkdir()
        files=json.loads((ROOT/'resources/studio/templates/blank.json').read_text(encoding='utf-8'))
        spec=json.loads(files['module.json']);spec['agent_tools']=[dict(id='increment',name='计数',description='增加计数',operation='increment')];files['module.json']=json.dumps(spec)
        for file,text in files.items():(component/file).write_text(text,encoding='utf-8')
        self.backend=Backend(self.root/'runtime',network=Network());self.addCleanup(self.backend.close)
        (self.root/'nexarbor.json').write_text(json.dumps({'format':'nexarbor-project/v2','resources':{'modules':{'example.counter':{'folder':'counter'},'tool_discovery':{'builtin':True}}}}),encoding='utf-8')
        self.studio=Studio(self.backend,{'example.counter':component,'tool_discovery':ROOT/'modules/tool_discovery'},project_directory=self.root);self.addCleanup(self.studio.close)

    def edit(self,commands,document=None,expect_failure=False):
        file=self.root/'input.json';out=self.root/'output.json';file.write_text(json.dumps(dict(document=document or {'network':{'nodes':[]},'files':{}},commands=commands,library=self.studio.library,expect_failure=expect_failure)),encoding='utf-8')
        subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'tests/studio_edit_network_fixture.mjs'),str(file),str(out)],check=True,capture_output=True)
        return json.loads(out.read_text(encoding='utf-8'))

    async def test_commands_compile_real_tables_and_native_agent_tools(self):
        result=self.edit([{'op':'node.create','id':'agent','kind':'agent'},{'op':'node.create','id':'counter','kind':'node'},{'op':'module.mount','node':'counter','module':'example.counter'},{'op':'module.mount','node':'agent','module':'tool_discovery','config':{},'access':{'strength':2,'channels':['tools']}},{'op':'edge.add','source':'agent','target':'counter','channels':['tools']}])
        document=validate_network(result['document'],self.backend,self.studio.library)
        self.assertEqual(result['receipt']['counts']['nodes'],2);self.assertTrue(document['network']['nodes'][1]['tables']['modules'][0]['tools']['members'])
        document['network']['nodes'][0]['execution']={'executor':'harness','strength':2,'channels':['tools']}
        fixture=self.root/'fixture';fixture.mkdir();(fixture/'initial.json').write_text(json.dumps({'version':1,'agents':{},**document}),encoding='utf-8')
        (fixture/'setup.json').write_text(json.dumps({'modules':{key:str(self.studio.root/item['folder']) for key,item in self.studio.library.items()}}),encoding='utf-8')
        h=NetworkHarness(fixture);self.addAsyncCleanup(h.close)
        discovered=await h.call('agent','agent','tool_discovery','discover')
        from domain.core import Tools
        self.assertIsInstance(discovered['data'],Tools);self.assertEqual(len(list(discovered['data'])),1)
        view=await h.prepare_agent('agent');name=next(tool['name'] for tool in view['tools'] if '计数' in tool['description'])
        self.assertEqual(await h.agent_tool('agent',name,{'amount':6}),6)
        await h.restart();await h.prepare_agent('agent');self.assertEqual(await h.agent_tool('agent',name,{'amount':2}),8)

    async def test_existing_serialized_tables_are_copied_without_rechecking_manifest_dependencies(self):
        draft=self.edit([{'op':'node.create','id':'counter'},{'op':'module.mount','node':'counter','module':'example.counter'}])['document']
        document=validate_network(draft,self.backend,self.studio.library)
        library=deepcopy(self.studio.library);library['example.counter']['manifest']['requires']=['not-installed']
        changed=self.edit([{'op':'module.mount','node':'counter','module':'example.counter','state':{'count':12}}],document=document)['document']
        self.assertEqual(changed['network']['nodes'][0]['tables']['modules'][0]['tools'],document['network']['nodes'][0]['tables']['modules'][0]['tools'])
        copied=validate_network(document,self.backend,library)
        self.assertEqual(copied['network']['nodes'][0]['tables'],document['network']['nodes'][0]['tables'])

    async def test_failed_edit_batch_is_atomic_and_duplicate_edges_are_idempotent(self):
        result=self.edit([{'op':'node.create','id':'a'},{'op':'node.create','id':'b'},{'op':'edge.add','source':'a','target':'b','channels':['route']},{'op':'edge.add','source':'a','target':'b','channels':['route']}])
        self.assertEqual(result['receipt']['counts']['edges'],1)
        failure=self.edit([{'op':'node.create','id':'created'},{'op':'edge.add','source':'created','target':'missing','channels':['route']}],expect_failure=True)
        self.assertTrue(failure['rejected']);self.assertIn('整批未保存',failure['message'])

    async def test_repeat_units_keep_tool_identity_typed_references_and_independent_data(self):
        from app.studio.preset_repetition import expand_snapshot
        component=Path(self.studio.library['example.counter']['folder']);spec=json.loads((component/'module.json').read_text(encoding='utf-8'))
        spec['node_types']=['node','agent'];spec['config_schema']={'type':'object','properties':{'partner':{'type':'string','format':'node-id'},'tool':{'type':'object'}}}
        (component/'module.json').write_text(json.dumps(spec),encoding='utf-8');self.studio=Studio(self.backend,{'example.counter':component},project_directory=self.root);self.addCleanup(self.studio.close)
        draft=self.edit([{'op':'node.create','id':'shared'},{'op':'node.create','id':'unit','kind':'agent'},{'op':'text.write','path':'data/unit.md','text':'独立记忆'},{'op':'module.mount','node':'unit','module':'example.counter','config':{'partner':'unit','tool':{'path':'业务值'}},'state':{'count':5}},{'op':'edge.add','source':'shared','target':'unit','channels':['tick']}])['document']
        compiled=validate_network(draft,self.backend,self.studio.library)
        expanded=expand_snapshot({**compiled['network'],'files':compiled['files'],'repeat_unit':['unit'],'repeat_unit_count':3},definitions={key:item['manifest'] for key,item in self.studio.library.items()})
        self.assertEqual(len(expanded['nodes']),4);self.assertEqual(len(expanded['nodes'][0]['links']),3);self.assertEqual(len(expanded['files']),3)
        for node in expanded['nodes'][1:]:
            module=node['tables']['modules'][0];self.assertEqual(module['config']['partner'],node['node_id']);self.assertEqual(module['config']['tool'],{'path':'业务值'})
        fixture=self.root/'repeated';fixture.mkdir();(fixture/'initial.json').write_text(json.dumps({'version':1,'agents':{},'network':{'nodes':expanded['nodes']},'files':expanded['files']}),encoding='utf-8')
        (fixture/'setup.json').write_text(json.dumps({'modules':{'example.counter':str(component)}}),encoding='utf-8')
        h=NetworkHarness(fixture);self.addAsyncCleanup(h.close)
        names=[]
        for node in expanded['nodes'][1:]:
            current=h.network.get(node['node_id']);tool=next(tool for tool in current.tools if '计数' in tool.description);names.append(tool.name)
            self.assertEqual(tool.invoke(amount=1),6)
        self.assertEqual(len(set(names)),3)
        h.write('unit~unit-2','仅第二份');self.assertEqual(h.read('unit'),'独立记忆');self.assertEqual(h.read('unit~unit-3'),'独立记忆')

    async def test_network_author_worker_validates_and_publishes_real_candidate(self):
        draft=self.edit([{'op':'node.create','id':'counter'},{'op':'module.mount','node':'counter','module':'example.counter'}])['document']
        work=self.studio.create({'kind':'network'});id=work['id']
        self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'network.json','content':json.dumps(draft)}})
        test="""import unittest
from app.studio.network_testing import NetworkHarness
class Candidate(unittest.IsolatedAsyncioTestCase):
    async def test_real_operation(self):
        h=NetworkHarness()
        try:
            result=await h.call('counter','counter','example.counter','increment',{'amount':9})
            self.assertEqual(result['data'],9)
            await h.restart()
            self.assertEqual((await h.call('counter','counter','example.counter','increment',{'amount':1}))['data'],10)
        finally:await h.close()
"""
        self.studio.maker_tool({'id':id,'tool':'write_file','arguments':{'path':'tests/test_candidate.py','content':test}})
        job=self.studio.validate({'id':id,'timeout':60});deadline=time.monotonic()+60
        while job['status']=='running' and time.monotonic()<deadline:
            await asyncio.sleep(.05);job=self.studio.job({'job':job['id']})
        self.assertEqual(job['status'],'passed',job['log']);self.assertIn('测试数量：1',job['log'])
        release=self.studio.publish({'id':id});self.assertEqual(release['kind'],'network');self.assertEqual(len(release['document']['network']['nodes']),1)

    async def test_context_assembly_keeps_configured_channels_and_strength(self):
        library={key:Path(release['folder']) for key,release in self.studio.library.items()};library['context.assembler']=ROOT/'modules/context_assembler'
        self.studio=Studio(self.backend,library);self.addCleanup(self.studio.close)
        channel='context.assembler.context'
        result=self.edit([{'op':'node.create','id':'agent','kind':'agent'},{'op':'node.create','id':'relay'},{'op':'node.create','id':'document','kind':'markdown'},{'op':'text.write','path':'data/document.md','text':'跨两层的真实资料'},{'op':'module.mount','node':'agent','module':'context.assembler','config':{},'access':{'strength':4,'channels':[channel]}},{'op':'edge.add','source':'agent','target':'relay','channels':[channel]},{'op':'edge.add','source':'relay','target':'document','channels':[channel]}])
        document=validate_network(result['document'],self.backend,self.studio.library)
        module=document['network']['nodes'][0]['tables']['modules'][0]
        self.assertEqual(module['strength'],4);self.assertEqual(module['channels'],[channel])
        fixture=self.root/'context';fixture.mkdir();(fixture/'initial.json').write_text(json.dumps({'version':1,'agents':{},**document}),encoding='utf-8')
        (fixture/'setup.json').write_text(json.dumps({'modules':{key:str(item['folder']) for key,item in self.studio.library.items()}}),encoding='utf-8')
        h=NetworkHarness(fixture);self.addAsyncCleanup(h.close)
        packet=await h.network.get('agent').modules.get('context.assembler').assemble()
        self.assertEqual(packet['patch']['context'][0]['text'],'跨两层的真实资料')

    async def test_frontend_copy_library_and_actual_restored_tool_calls(self):
        from app.runtime import ports
        from app.projects.host_tools import host_tool_name
        component=Path(self.studio.library['example.counter']['folder']);spec=json.loads((component/'module.json').read_text(encoding='utf-8'))
        spec['node_types']=['node','agent'];spec['config_schema']={'type':'object','properties':{'partner':{'type':'string','format':'node-id'}}}
        (component/'module.json').write_text(json.dumps(spec),encoding='utf-8');self.studio=Studio(self.backend,{'example.counter':component},project_directory=self.root);self.addCleanup(self.studio.close)
        draft=self.edit([{'op':'node.create','id':'hub'},{'op':'node.create','id':'unit','kind':'agent'},{'op':'text.write','path':'data/unit.md','text':'独立文件'},{'op':'module.mount','node':'unit','module':'example.counter','config':{'partner':'unit'},'state':{'count':5}},{'op':'edge.add','source':'hub','target':'unit','channels':['route']}])['document']
        draft['network']['properties']={'unit':{'management_parent_id':'hub','offered_ports':[{'ref':'runtime:checkpoint','channels':['runtime.checkpoint']}]}}
        definitions={'runtime:checkpoint':ports.DEFINITIONS[1]}
        document=validate_network(draft,self.backend,self.studio.library,port_definitions=definitions)
        document['network']['nodes'][1]['execution']={'executor':'harness','strength':2,'channels':[]}
        catalog={key:item['manifest'] for key,item in self.studio.library.items()}
        source=self.root/'copy-input.json';out=self.root/'copy-output.json';source.write_text(json.dumps({'document':document,'catalog':catalog}),encoding='utf-8')
        result=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(ROOT/'tests/studio_copy_library_fixture.mjs'),str(source),str(out)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);value=json.loads(out.read_text(encoding='utf-8'));id=value['id']
        fixture=self.root/'copy-runtime';fixture.mkdir();(fixture/'initial.json').write_text(json.dumps({'version':1,'agents':{},'node_properties':value['document']['network']['properties'],**value['document']}),encoding='utf-8')
        (fixture/'setup.json').write_text(json.dumps({'modules':{'example.counter':str(component)},'port_definitions':definitions}),encoding='utf-8')
        h=NetworkHarness(fixture);self.addAsyncCleanup(h.close)
        for actor,expected in [('unit',6),(id,124)]:
            view=await h.prepare_agent(actor);name=next(tool['name'] for tool in view['tools'] if '计数' in tool['description'])
            self.assertEqual(await h.agent_tool(actor,name,{'amount':1}),expected)
        self.assertGreater(await h.agent_tool(id,host_tool_name(id,'runtime:checkpoint'),{'full':True}),0)
        h.write(id,'仅修改复制文件');self.assertEqual(h.read('unit'),'独立文件')
