"""Authorization is derived from the tool, never from caller routing labels."""
import unittest
from datanet.core.node import Node
from datanet.core.network import Network
from datanet.core.tool_access import list_tools,invoke_tool,list_nodes
from datanet.core.access_budget import access_context
class ChannelAccessTests(unittest.TestCase):
 def setup_network(self):
  n=Network()
  for id in ('actor','store','other'):n.add_node(Node(id,id,None))
  store=n.nodes['store'];args=dict(description='test',parameters={'type':'object','properties':{},'additionalProperties':False})
  store.register_tool('read_value',lambda:'value',access_channels=['catalog'],**args)
  store.register_tool('change_value',lambda:'changed',access_channels=['maintenance'],**args)
  store.expose=['read_value','change_value']
  return n
 def test_unrelated_signal_channel_does_not_grant_tool_access(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=('world.tick','catalog'))
  self.assertEqual([t['name'] for t in list_tools(n,'actor','store',strength=2).items],['read_value'])
  self.assertEqual(invoke_tool(n,'actor','store','change_value',{},strength=2).status,'forbidden')
  with self.assertRaises(TypeError):invoke_tool(n,'actor','store','change_value',{},channels=['maintenance'])
 def test_custom_tool_channel_has_no_read_write_classification(self):
  n=self.setup_network();s=n.nodes['store'];s.register_tool('trade',lambda:'traded',description='trade',parameters={'type':'object'},access_channels=['market.trade']);s.expose.append('trade')
  n.nodes['actor'].connect('store',channels=['market.trade'])
  self.assertEqual([t['name'] for t in list_tools(n,'actor','store',strength=2).items],['trade'])
  self.assertEqual(invoke_tool(n,'actor','store','trade',{},strength=2).items,[{'result':'traded'}])
 def test_channel_named_private_has_no_special_rule_and_strength_is_bounded(self):
  n=self.setup_network();n.nodes['store'].register_tool('read_value',lambda:'value',description='test',parameters={'type':'object'},access_channels=['private'])
  n.nodes['actor'].connect('store',channels=['private']);n.nodes['other'].connect('actor',channels=['private'])
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=1).status,'ok')
  self.assertEqual(invoke_tool(n,'other','store','read_value',{},strength=3).status,'ok')
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=0).status,'forbidden')
 def test_nested_operation_cannot_upgrade_its_channel(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=['catalog','maintenance']);n.nodes['store'].connect('other',channels=['maintenance'])
  other=n.nodes['other'];other.register_tool('change',lambda:True,description='change',parameters={'type':'object'},access_channels=['maintenance']);other.expose=['change']
  with access_context(n,'store',2,['actor','store'],channels=['catalog']):
   self.assertEqual(invoke_tool(n,'store','other','change',{},strength=2).status,'forbidden')
   self.assertEqual(list_tools(n,'store','other',strength=2).items,[])
 def test_empty_channel_is_no_remote_grant_and_connect_merges_equal_grants(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=[])
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=2).status,'forbidden')
  n.nodes['actor'].connect('store',channels=['catalog']);n.nodes['actor'].connect('store',channels=['maintenance'])
  self.assertEqual(len(n.nodes['actor'].interfaces),1)
  self.assertEqual({t['name'] for t in list_tools(n,'actor','store',strength=2).items},{'read_value','change_value'})

 def test_channels_are_explicit_and_registration_failure_is_atomic(self):
  n=self.setup_network();node=n.nodes['store'];before=set(node.tools)
  with self.assertRaises(TypeError):node.register_tool('implicit',lambda:None,description='test',parameters={})
  with self.assertRaises(TypeError):node.register_tool('old',lambda:None,description='test',parameters={},read_only=True,access_channels=[])
  with self.assertRaises(ValueError):node.register_tool('invalid',lambda:None,description='test',parameters={'type':'object'},access_channels=[' '])
  self.assertEqual(set(node.tools),before)
  self.assertNotIn('read_only',node.tool_definitions['read_value'])
  self.assertFalse(hasattr(n,'read'));self.assertFalse(hasattr(n,'write'))

 def test_combined_channels_can_intentionally_cross_domains(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=['public']);n.nodes['store'].connect('other',channels=['private'])
  self.assertNotIn('other',[x.node_id for x,_ in n.walk('actor',channels=['public'],strength=3)])
  self.assertIn('other',[x.node_id for x,_ in n.walk('actor',channels=['public','private'],strength=3)])
  self.assertEqual([x['node_id'] for x in list_nodes(n,'actor',strength=3).items],['actor'])

 def test_explicit_text_tool_channels_and_exposure_survive_roundtrip(self):
  import tempfile
  from pathlib import Path
  from datanet.core.text_node import TextFileNode
  from datanet.core.serialization import save_network,load_network
  with tempfile.TemporaryDirectory() as folder:
   n=self.setup_network();text=TextFileNode('text','Text',None,Path(folder)/'data.md',tool_channels={'read':['documents'],'write':['documents'],'get_schema':['schema']})
   text.write('content','hello');text.expose=['read'];n.add_node(text);n.nodes['actor'].connect('text',channels=['documents','schema'])
   path=Path(folder)/'network.json';save_network(n,path);n=load_network(path)
   from datanet.core.component_registry import attach_local_tools
   attach_local_tools(n.nodes['text'])
   self.assertEqual(invoke_tool(n,'actor','text','read',{'request':{'method':'key','key':'content'}},strength=2).items,[{'content':'hello'}])
   self.assertEqual(invoke_tool(n,'actor','text','write',{'key':'content','value':'changed'},strength=2).status,'forbidden')
   self.assertEqual(n.nodes['text'].tool_channels['get_schema'],['schema'])
   n.nodes['text'].expose.append('get_schema')
   self.assertEqual(invoke_tool(n,'actor','text','get_schema',{},strength=2).status,'ok')
   self.assertEqual(n.nodes['text'].tool_definitions['write']['access_channels'],['documents'])

 def test_agent_owned_tools_cannot_be_exposed(self):
  import tempfile
  from pathlib import Path
  from datanet.core.agent_node import AgentNode
  with tempfile.TemporaryDirectory() as folder:
   n=self.setup_network();agent=AgentNode('agent','Agent',file_path=Path(folder)/'memory.md');n.add_node(agent)
   agent.register_agent_tool('secret',lambda:True,description='private',parameters={'type':'object'})
   agent.expose=['secret'];n.nodes['actor'].connect('agent',channels=['catalog'])
   self.assertEqual(invoke_tool(n,'actor','agent','secret',{},strength=2).status,'forbidden')
   self.assertEqual(list_tools(n,'actor','agent',strength=2).items,[])
if __name__=='__main__':unittest.main()
