"""Root is an optional node ID, not a persistence or editor invariant."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import importlib.util
from datanet.core.backend import Backend
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.serialization import network_document

ROOT=Path(__file__).resolve().parents[1]
class RootlessNetworks(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/rootless-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=TemporaryDirectory(dir=base);self.home=Path(self.temp.name);self.b=None
    def tearDown(self):
        if self.b is not None:self.b.close()
        self.temp.cleanup()
    def create(self,nodes=()):
        graph=Network()
        for node in nodes:graph.add_node(node)
        return {'network':network_document(graph,self.home),'files':{}}
    def reopen(self):
        self.b.close();self.b=None;self.b=Backend(self.home)
    def test_empty_network_can_load_save_and_cold_restore(self):
        self.b=Backend(self.home,initial_document=self.create())
        self.assertIsNone(self.b.root);self.assertEqual(self.b.snapshot()['network']['nodes'],[])
        self.assertIsNone(self.b.dispatch('root_network_info',{})['root_node_id'])
        self.assertEqual(self.b.dispatch('recovery_info',{})['node_count'],0)
        self.b.dispatch('save',{});self.reopen();self.assertEqual(len(self.b.network.nodes),0)
        self.assertTrue(self.b.studio.graph_validate({'document':self.create()})['valid'])
    def test_plain_network_and_plain_node_named_root_are_both_legal(self):
        self.b=Backend(self.home,initial_document=self.create([Node('place','地方',None)]))
        self.assertIsNone(self.b.root);self.assertEqual(set(self.b.network.nodes),{'place'})
        doc=self.create([Node('root','普通编号',None)])
        self.b.studio.apply({'document':doc,'base_commit':self.b.store.head});self.b.dispatch('save',{});self.reopen()
        self.assertIs(type(self.b.root),Node)
        self.assertEqual(self.b.dispatch('root_network_info',{})['root_node_id'],'root')
    def test_explicit_package_entry_does_not_require_canonical_root_id(self):
        self.b=Backend(self.home,initial_document=self.create())
        path=ROOT/'extensions/foundation/capabilities/tools_network_management/python/datanet/services/tools/network_management/services.py'
        spec=importlib.util.spec_from_file_location('entry_service',path);service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
        graph=Network();graph.add_node(Node('entrance','入口',None))
        package=SimpleNamespace(entry_points={'start':'entrance'},instantiate=lambda **kwargs:(graph,SimpleNamespace(node_ids=['entrance'],entry_points={'start':'entrance'})))
        with patch.object(service,'load_network_package',return_value=package):
            result=service.load_root_network(self.b,{'package':str(ROOT/'build/entry-package.json'),'entry_point':'start'})
        self.assertEqual(result['node_ids'],['entrance']);self.assertIsNone(self.b.root)
        self.assertIs(graph.node_locks,self.b.node_locks)
        self.assertEqual(service.load_root_network(self.b,{'package':'unused'})['root_node_id'],None)

    def test_delete_bound_root_keeps_other_agent_data_and_clears_only_parent_binding(self):
        self.b=Backend(self.home);agent=AgentNode('member','成员',file_path=self.b.directory/'member.md');agent.management_parent_id='root'
        self.b.network.add_node(agent);agent.write_memory('成员的独立记忆')
        self.b.agents={'root':{'session_id':'root-history','manager_id':None},'member':{'session_id':'member-history','manager_id':'root','creator_node_id':'root'}}
        self.b.dispatch('save',{})
        live=self.b.studio.state()['live'];doc=deepcopy(live['document']);doc['network']['nodes']=[n for n in doc['network']['nodes'] if n['node_id']!='root']
        doc['network']['nodes'][0]['management_parent_id']=None
        result=self.b.studio.apply({'document':doc,'base_commit':live['commit']});self.assertTrue(result['valid'])
        self.assertIsNone(self.b.root);self.assertNotIn('root',self.b.agents);self.assertEqual(self.b.agents['member']['session_id'],'member-history')
        self.assertIsNone(self.b.agents['member']['manager_id']);self.assertIsNone(self.b.agents['member']['creator_node_id'])
        self.b.dispatch('save',{});self.reopen();self.assertEqual(self.b.network.nodes['member'].read_memory()['content'],'成员的独立记忆')
        self.assertEqual(set(self.b.network.nodes),{'member'})

if __name__=='__main__':unittest.main()
