"""显式安装的固定模板能力，不调用模型。"""
import os,sys,subprocess,tempfile,textwrap,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class Templates(unittest.TestCase):
    def test_registered_template_is_idempotent_bounded_and_has_fresh_memory(self):
        source=r'''
import asyncio,json
from copy import deepcopy
from pathlib import Path
from datanet.core.backend import Backend
from datanet.core.serialization import network_document
from datanet.core.node import Node
directory=Path(__import__('sys').argv[1]);b=Backend(directory)
try:
    b.network.add_node(Node('clinic','医院',None));b.network.nodes['root'].offered_tools=[{'ref':'templates:instantiate','channels':['spawn']}]
    node=deepcopy(network_document(b.network,b.directory)['nodes'][0]);node.update(node_id='child',name='儿童',management_parent_id='root',modules={'place.info':{'config':{'location':'clinic'},'state':{},'access':{'strength':0,'channels':['movement']}}},connections={'interfaces':[{'target_node_id':'clinic','metadata':{'channels':['movement'],'threshold':1,'multiplier':1,'attributes':{}}}]},offered_tools=[])
    node['parameters']['file_path']='memory.md'
    template={'id':'resident','callers':['root'],'document':{'network':{'version':8,'nodes':[node],'signals':{},'delegations':[]},'files':{'memory.md':'全新的私人记忆'}},'arguments_schema':{'type':'object','properties':{'name':{'type':'string','minLength':1}},'required':['name'],'additionalProperties':False},'bindings':[{'path':'/network/nodes/0/name','input':'name'}],'attachments':[{'source':'clinic','target':'child','metadata':{'channels':['movement'],'threshold':1,'multiplier':1,'attributes':{}}}]}
    template['arguments_schema']['properties']['parents']={'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2};template['arguments_schema']['required'].append('parents')
    template['bindings'].append({'path':'/network/nodes/0/modules/place.info/config/location','input':'/parents/0'})
    b.configure_templates({'templates':[template]})
    async def invoke(key='birth-1',name='小芽',actor='root'):
        return await b.external_tools.invoke(actor,'root','templates:instantiate',{'template':'resident','key':key,'arguments':{'name':name,'parents':['clinic','root']}},strength=2,channels=['spawn'])
    first=asyncio.run(invoke());second=asyncio.run(invoke());assert second['duplicate'] and first['node_ids']==second['node_ids']
    child=b.network.nodes[first['node_ids']['child']];assert child.name=='小芽' and child.context_cursor is None
    assert child.file_path.read_text(encoding='utf-8')=='全新的私人记忆'
    assert child.file_path.is_relative_to(b.directory/'created/templates')
    assert any(e.target_node_id==child.node_id for e in b.network.nodes['clinic'].interfaces)
    assert any(e.target_node_id=='clinic' for e in child.interfaces)
    assert b.modules.get(child.node_id,'place.info').config['location']=='clinic'
    try:asyncio.run(invoke(name='不同参数'))
    except ValueError:pass
    else:raise AssertionError('同key改变参数未拒绝')
    b.network.nodes['clinic'].connect('root',channels=['spawn'])
    try:asyncio.run(invoke(actor='clinic'))
    except PermissionError:pass
    else:raise AssertionError('未经登记的节点能够实例化模板')
    count=len(b.network.nodes);before=list(b.network.nodes['clinic'].interfaces);writer=b.write_documents
    def fail(files):raise RuntimeError('模拟落盘阶段故障')
    b.write_documents=fail
    try:asyncio.run(invoke(key='rollback'))
    except RuntimeError:pass
    else:raise AssertionError('故障未发生')
    finally:b.write_documents=writer
    assert len(b.network.nodes)==count and b.network.nodes['clinic'].interfaces==before
    bad=deepcopy(template);bad['id']='bad';bad['document']['network']['nodes'][0]['modules']['place.info']['config']['description']=45
    b.configure_templates({'templates':[template,bad]})
    try:asyncio.run(b.external_tools.invoke('root','root','templates:instantiate',{'template':'bad','key':'broken','arguments':{'name':'失败','parents':['clinic','root']}},strength=0,channels=['spawn']))
    except Exception:pass
    else:raise AssertionError('错误配置未拒绝')
    assert len(b.network.nodes)==count
    bad=deepcopy(template);bad['bindings']=[{'path':'/network/nodes/0/modules/place.info/access/strength','input':'name'}]
    try:b.configure_templates({'templates':[bad]})
    except ValueError:pass
    else:raise AssertionError('输入参数可以改权限')
    b.dispatch('save',{})
finally:b.close()
b=Backend(directory)
try:
    b.configure_templates({'templates':[template]});saved=b.extension_state['template_receipts']['root:birth-1']['result'];assert saved['node_ids']==first['node_ids']
    assert b.network.nodes[first['node_ids']['child']].file_path.read_text(encoding='utf-8')=='全新的私人记忆'
finally:b.close()
print('PASS 模板幂等、独立记忆、固定锚点、权限不可改、失败无半成品、冷恢复')
'''
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION='["capabilities/component_studio","capabilities/place_info","capabilities/template_instantiation"]',DATANET_COMPONENT_PROFILE='{}')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as temporary:
            result=subprocess.run([sys.executable,'-c',textwrap.dedent(source),temporary],env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=40)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
