"""Authorization is derived from the tool, never from caller routing labels."""
import unittest
from datanet.core.node import Node
from datanet.core.network import Network
from datanet.core.tool_access import list_tools,invoke_tool
from datanet.core.access_budget import access_context
class ChannelAccessTests(unittest.TestCase):
 def setup_network(self):
  n=Network()
  for id in ('actor','store','other'):n.add_node(Node(id,id,None))
  store=n.nodes['store'];args=dict(description='test',parameters={'type':'object','properties':{},'additionalProperties':False})
  store.register_tool('read_value',lambda:'value',read_only=True,**args)
  store.register_tool('change_value',lambda:'changed',**args)
  store.expose=['read_value','change_value']
  return n
 def test_mixed_tick_and_read_cannot_authorize_write(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=('world.tick','access.read'))
  self.assertEqual([t['name'] for t in list_tools(n,'actor','store',strength=2).items],['read_value'])
  self.assertEqual(invoke_tool(n,'actor','store','change_value',{},strength=2).status,'forbidden')
  with self.assertRaises(TypeError):invoke_tool(n,'actor','store','change_value',{},channels=['world.tick','access.write'])
 def test_custom_tool_channel_is_not_tied_to_read_only_flag(self):
  n=self.setup_network();s=n.nodes['store'];s.register_tool('trade',lambda:'traded',description='trade',parameters={'type':'object'},access_channels=['market.trade']);s.expose.append('trade')
  n.nodes['actor'].connect('store',channels=['market.trade'])
  self.assertEqual([t['name'] for t in list_tools(n,'actor','store',strength=2).items],['trade'])
  self.assertEqual(invoke_tool(n,'actor','store','trade',{},strength=2).items,[{'result':'traded'}])
 def test_private_access_is_owner_only_and_strength_is_bounded(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=['access.read'],visibility='private');n.nodes['other'].connect('actor',channels=['access.read'])
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=1).status,'ok')
  self.assertEqual(invoke_tool(n,'other','store','read_value',{},strength=3).status,'forbidden')
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=0).status,'forbidden')
 def test_nested_operation_cannot_upgrade_its_channel(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=['access.read','access.write']);n.nodes['store'].connect('other',channels=['access.write'])
  other=n.nodes['other'];other.register_tool('change',lambda:True,description='change',parameters={'type':'object'});other.expose=['change']
  with access_context(n,'store',2,['actor','store'],channels=['access.read']):
   self.assertEqual(invoke_tool(n,'store','other','change',{},strength=2).status,'forbidden')
   self.assertEqual(list_tools(n,'store','other',strength=2).items,[])
 def test_empty_channel_is_no_remote_grant_and_connect_merges_equal_grants(self):
  n=self.setup_network();n.nodes['actor'].connect('store',channels=[])
  self.assertEqual(invoke_tool(n,'actor','store','read_value',{},strength=2).status,'forbidden')
  n.nodes['actor'].connect('store',channels=['access.read']);n.nodes['actor'].connect('store',channels=['access.write'])
  self.assertEqual(len(n.nodes['actor'].interfaces),1)
  self.assertEqual({t['name'] for t in list_tools(n,'actor','store',strength=2).items},{'read_value','change_value'})
if __name__=='__main__':unittest.main()
