"""真实 Backend + ctx + 原生准备适配器；无模型、无付费调用。"""
import asyncio, json, os, sys, unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from datanet.core.backend import Backend
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.text_node import TextFileNode
from adapters.harness.studio.executor import NativeExecutor

KINDS=['system_prompt','context','inputs','tail']
class AssemblerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=TemporaryDirectory(dir=ROOT/'build');cls.home=Path(cls.temp.name);cls.b=Backend(cls.home)
  cls.executor=NativeExecutor(cls.b,None)
 @classmethod
 def tearDownClass(cls):cls.b.close();cls.temp.cleanup()
 def setUp(self):
  self.b.modules.clear();self.b.network.nodes.clear();self.b.agents.clear()
  actor=AgentNode('a','角色',file_path=self.home/'agent.md');self.b.network.add_node(actor)
  actor.execution_binding={'executor':'harness','strength':3,'channels':['context.assemble','self'],'prepare':[{'node':'assembly','module':'context.assembler','operation':'assemble','arguments':{},'channels':['context.assemble']}]}
  self.actor=actor;self.b.network.add_node(Node('assembly','组装节点',None));actor.connect('assembly',channels=['context.assemble'])
  self.config={'sources':[],'channels':['context.assemble'],**{k+'_channels':[k] for k in KINDS}};self.mount()
 def mount(self):
  if ('assembly','context.assembler') in self.b.modules.instances:self.b.modules.unmount('assembly','context.assembler')
  return self.b.modules.mount('assembly','context.assembler',self.config,{},access={'strength':6,'channels':KINDS+['context.assemble','records'],'extension':{'operations':['read_text'],'targets':[]}})
 def source(self,id,text,kind,**cfg):
  file=self.home/(id+'.md');file.write_text(text,encoding='utf-8');node=TextFileNode(id,id,'text',file);self.b.network.add_node(node)
  self.b.modules.mount(id,'context.text',cfg,{},access={'strength':0,'channels':KINDS});self.b.network.nodes['assembly'].connect(id,channels=[kind]);return node
 def preview(self):return self.b.runtime.run(self.b.modules.call('assembly','context.assembler','preview',{}))['data']
 def prepare(self):return self.executor.prepare({'actor':'a'})
 def test_four_channels_dedup_and_no_mixed_channel_walk(self):
  sysnode=self.source('system','人格','system_prompt');self.source('doc','规则','context');self.source('event','开始','inputs',event_id='start');self.source('time','第1天','tail')
  self.b.network.add_node(Node('route','分路',None));self.b.network.nodes['assembly'].connect('route',channels=['context']);self.b.network.nodes['route'].connect('doc',channels=['context']);self.b.network.nodes['doc'].connect('route',channels=['context'])
  secret=self.source('secret','不能读','tail');self.b.network.nodes['assembly'].interfaces[:]=[e for e in self.b.network.nodes['assembly'].interfaces if e.target_node_id!='secret'];sysnode.connect('secret',channels=['tail']);self.actor.connect('secret',channels=['chat'])
  before=self.actor.inputs.snapshot();p=self.preview();self.assertEqual(p['errors'],[]);self.assertEqual(p['patch'],{'system_prompt':'人格','context':[{'id':'node:doc','text':'规则'}],'inputs':[{'id':'node:event/start','text':'开始','delivery':'followup'}],'tail':['第1天']});self.assertEqual(before,self.actor.inputs.snapshot())
  prepared=self.prepare();self.assertEqual(prepared['system_prompt'],'人格');self.assertEqual(len(prepared['inputs']),1);self.assertNotIn('不能读',json.dumps(prepared,ensure_ascii=False));self.executor.ack({'actor':'a','events':[{'source':prepared['inputs'][0]['source'],'id':'node:event/start'}]});self.assertEqual(self.prepare()['inputs'],[])
 def test_direct_text_file_and_file_root_failures(self):
  file=self.home/'guide.txt';file.write_text('文件正文',encoding='utf-8');self.config['sources']=[{'id':'direct','kind':'system_prompt','type':'text','text':'直接人格'},{'id':'file','kind':'context','type':'file','path':'guide.txt'},{'id':'bad','kind':'tail','type':'file','path':'../outside.md'},{'id':'missing','kind':'tail','type':'file','path':'missing.md'}];self.mount()
  p=self.preview();self.assertEqual(p['patch']['system_prompt'],'直接人格');self.assertEqual(p['patch']['context'][0]['text'],'文件正文');self.assertEqual(len(p['errors']),2);self.assertTrue(Path(next(s for s in p['sources'] if s['id'].endswith(':source:file'))['resolved_path']).samefile(file))
  file.write_text('更新后的正文',encoding='utf-8');self.assertEqual(self.preview()['patch']['context'][0]['text'],'更新后的正文')
 def test_explicit_external_root_and_size_limit(self):
  with TemporaryDirectory(dir=ROOT/'build') as external:
   p=Path(external)/'outside.txt';p.write_text('明确授权',encoding='utf-8');self.config['sources']=[{'id':'external','kind':'context','type':'file','path':str(p)}];self.mount();self.assertEqual(len(self.preview()['errors']),1)
   self.config['document_roots']=[external];self.mount();self.assertEqual(self.preview()['patch']['context'][0]['text'],'明确授权');p.write_bytes(b'x'*(1024*1024+1));self.assertIn('1 MiB',self.preview()['errors'][0]['error'])
 def test_file_extension_is_not_ambient_authority(self):
  self.config['sources']=[{'id':'file','kind':'tail','type':'file','path':'guide.txt'}];self.mount();self.b.modules.unmount('assembly','context.assembler');self.b.modules.mount('assembly','context.assembler',self.config,{},access={'strength':4,'channels':KINDS+['context.assemble']});p=self.preview();self.assertEqual(len(p['errors']),1);self.assertEqual(p['patch']['tail'],[])
 def test_condition_fact_binding_and_dynamic_clear(self):
  self.b.modules.mount('a','records.store',{'initial':{'role':'miner'}},{},access={'strength':0,'channels':['records']});self.b.network.nodes['assembly'].connect('a',channels=['records'])
  self.config['bindings']=[{'node':'a','module':'records.store','operation':'read','channels':['records'],'pointer':'/values'}];self.mount();self.source('knowledge','矿工知识','context',when={'role':'miner'})
  self.assertEqual(len(self.prepare()['context']),1);self.b.runtime.run(self.b.modules.call('a','records.store','apply',{'set':{'role':'resident'}}));self.assertEqual(self.prepare()['context'],[])
 def test_direct_source_ids_event_identity_and_repeated_preview(self):
  self.config['sources']=[{'id':'e','kind':'inputs','type':'text','text':'一次输入','event_id':'e1'}];self.mount();self.preview();self.preview();self.assertEqual(self.actor.inputs.snapshot(),{});first=self.prepare();self.assertEqual(len(first['inputs']),1);self.assertEqual(len(self.prepare()['inputs']),1)
  self.config['sources'][0]['text']='更改同一个事件';self.mount()
  with self.assertRaisesRegex(ValueError,'event ID'):self.prepare()
 def test_no_unnecessary_node_locks_and_source_revocation(self):
  self.source('time','当前快照','tail');self.assertEqual(self.prepare()['tail'],['当前快照']);self.actor.execution_binding['prepare']=[];self.assertEqual(self.prepare()['tail'],[])
  self.assertNotIn('lock_nodes',(ROOT/'extensions/composable/capabilities/context_assembler/module.py').read_text(encoding='utf-8'))
 def test_broken_entrypoint_does_not_fall_back_to_global_call(self):
  self.actor.interfaces.clear()
  with self.assertRaises(PermissionError):self.prepare()
 def test_wrong_input_without_event_id_is_reported(self):
  self.source('e','不应入队','inputs');p=self.preview();self.assertEqual(p['patch']['inputs'],[]);self.assertIn('稳定',p['errors'][0]['error'])
 def test_draft_frontend_preview_does_not_apply_config(self):
  self.config['sources']=[{'id':'sys','kind':'system_prompt','type':'text','text':'运行配置'}];self.mount();draft={'sources':[{'id':'draft','kind':'system_prompt','type':'text','text':'草稿预览'}]}
  result=self.b.studio.frontend_preview({'node':'assembly','module':'context.assembler','config':draft});self.assertEqual(result['patch']['system_prompt'],'草稿预览');self.assertEqual(self.prepare()['system_prompt'],'运行配置')
 def test_chaining_merges_stable_sources_and_stops_cycles(self):
  self.source('time','共享时钟','tail');self.config['sources']=[{'id':'self','kind':'system_prompt','type':'text','text':'A人格'}];self.mount()
  self.b.network.add_node(Node('b','B组装',None));other={'channels':['context.assemble'],**{k+'_channels':[k] for k in KINDS},'sources':[{'id':'self','kind':'system_prompt','type':'text','text':'B人格'}]}
  self.b.modules.mount('b','context.assembler',other,{},access={'strength':5,'channels':KINDS+['context.assemble']});self.b.network.nodes['assembly'].connect('b',channels=['context.assemble']);self.b.network.nodes['b'].connect('assembly',channels=['context.assemble']);self.b.network.nodes['b'].connect('time',channels=['tail']);result=self.preview();self.assertEqual(result['errors'],[]);self.assertEqual(result['patch']['tail'],['共享时钟']);self.assertIn('A人格',result['patch']['system_prompt']);self.assertIn('B人格',result['patch']['system_prompt'])
 def test_agent_prepares_subnode_context_through_local_entrypoint(self):
  from datanet.core.subnode import Subnode
  self.b.modules.unmount('assembly','context.assembler');self.b.network.nodes['assembly']=Subnode('assembly','上下文亚节点',parent_id='a');self.actor.interfaces.clear();self.actor.execution_binding['channels']=[];self.actor.execution_binding['prepare'][0].pop('channels',None);self.config['sources']=[{'id':'persona','kind':'system_prompt','type':'text','text':'本地人格'}];self.mount();self.assertEqual(self.prepare()['system_prompt'],'本地人格');self.assertNotIn('context.assemble',self.actor.execution_binding['channels'])
if __name__=='__main__':unittest.main()
