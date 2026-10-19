import unittest
from types import SimpleNamespace
from pathlib import Path
from datanet.core.preset_repetition import expand_snapshot,validate_repetition
from datanet.core.serialization import network_document,_build
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.text_node import TextFileNode
from datanet.core.subnode import Subnode

class PresetRepetition(unittest.TestCase):
 def fixture(self):
  base=Path.cwd();network=Network()
  network.add_node(TextFileNode('member','成员','text',file_path=base/'member.md'))
  network.add_node(Subnode('context','上下文',parent_id='member'))
  network.add_node(Node('board','共享任务板',None))
  network.nodes['member'].connect('board',channels=['work']);network.nodes['member'].connect('context',channels=['local']);network.nodes['board'].connect('member',channels=['tick'])
  snap={'nodes':network_document(network,base)['nodes'],'files':{'member.md':'私有数据'},'positions':{'member':{'x':0,'y':0},'board':{'x':200,'y':0}},'repeat_unit_count':3,'repeat_unit':['member']}
  snap['nodes'][0]['execution']={'executor':'other','prepare':[{'node':'context','module':'demo','operation':'read'}],'tool_sources':['context']}
  snap['nodes'][1]['modules']={'demo':{'config':{'target':'member'},'state':{},'access':{'channels':[],'strength':0}}}
  return snap
 def test_count_repeats_members_and_owned_subnodes_but_not_shared_board(self):
  source=self.fixture();schema=SimpleNamespace(config_schema={'type':'object','properties':{'target':{'format':'node-id'}}},state_schema={})
  result=expand_snapshot(source,4,{'demo':schema});self.assertEqual(len(result['nodes']),9);self.assertEqual(len([n for n in result['nodes'] if n['name']=='共享任务板']),1);self.assertEqual(len(source['nodes']),3)
  by={n['node_id']:n for n in result['nodes']};self.assertEqual(len(by),9);self.assertEqual(len(by['board']['connections']['interfaces']),4)
  files=[]
  for id,node in by.items():
   if node['type']!='text_file':continue
   files.append(node['parameters']['file_path']);self.assertEqual(result['files'][files[-1]],'私有数据')
   sub=by[node['execution']['tool_sources'][0]];self.assertEqual(sub['parameters']['parent_id'],id);self.assertEqual(sub['modules']['demo']['config']['target'],id);self.assertEqual(node['execution']['prepare'][0]['node'],sub['node_id']);self.assertIn('board',[e['target_node_id'] for e in node['connections']['interfaces']])
  self.assertEqual(len(set(files)),4);self.assertNotIn('repeat_unit_count',result)
 def test_null_or_absent_is_unchanged_and_bad_counts_rejected(self):
  snapshot=self.fixture();snapshot['repeat_unit_count']=None;self.assertEqual(expand_snapshot(snapshot),snapshot)
  for count in [0,-1,101,True,1.5,'4']:
   snapshot['repeat_unit_count']=count
   with self.assertRaisesRegex(ValueError,'整数'):expand_snapshot(snapshot)
  snapshot['repeat_unit_count']=2;snapshot['repeat_unit']=['missing']
  with self.assertRaisesRegex(ValueError,'不存在'):expand_snapshot(snapshot)
 def test_one_unit_and_generated_ids_never_collide(self):
  snapshot=self.fixture();self.assertEqual(len(expand_snapshot(snapshot,1)['nodes']),3)
  node=dict(snapshot['nodes'][2],node_id='member~unit-2');snapshot['nodes'].append(node)
  result=expand_snapshot(snapshot,2);ids=[n['node_id'] for n in result['nodes']];self.assertEqual(len(set(ids)),len(ids))
 def test_v8_metadata_roundtrips_without_affecting_ordinary_networks(self):
  network=Network();network.add_node(Node('member','成员',None));plain=network_document(network,Path.cwd());self.assertNotIn('repeat_unit_count',plain)
  declared={**plain,'repeat_unit_count':5,'repeat_unit':['member']};restored=_build(declared,Path.cwd());self.assertEqual(network_document(restored,Path.cwd()),declared)
