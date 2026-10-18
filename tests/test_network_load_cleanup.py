"""Loading composable node records prunes dangling interfaces, not bad data."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.node_records import capture_records, merge_records
from datanet.core.serialization import _build, load_network, network_document, save_network


class NetworkLoadCleanupTests(unittest.TestCase):
    def document(self, base):
        network=Network()
        for node in ('source','target','other'):network.add_node(Node(node,node,None))
        network.nodes['source'].connect('target',channels=['red'])
        network.nodes['source'].connect('source',channels=['self'])
        network.nodes['source'].connect('other',channels=['blue'])
        return network_document(network,base)

    def test_file_load_drops_missing_targets_and_keeps_valid_order_and_metadata(self):
        with TemporaryDirectory() as folder:
            base=Path(folder);document=self.document(base)
            links=document['nodes'][0]['connections']['interfaces']
            valid=deepcopy(links)
            for index in (0,2,5):
                links.insert(index,dict(target_node_id='deleted-'+str(index),metadata={'channels':['gone']}))
            path=base/'network.json';path.write_text(json.dumps(document),encoding='utf-8')
            restored=load_network(path)
            self.assertEqual(network_document(restored,base)['nodes'][0]['connections']['interfaces'],valid)
            self.assertEqual([node.node_id for node,_,_ in restored.walk_states('source',channels=['red'],strength=1)],['source','target'])
            save_network(restored,path)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['nodes'][0]['connections']['interfaces'],json.loads(json.dumps(valid)))

    def test_missing_target_does_not_hide_a_malformed_interface(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            for link in (
                {'target_node_id':'deleted','metadata':{'threshold':-1}},
                {'target_node_id':'deleted','metadata':{},'unexpected':True},
                {'target_node_id':'','metadata':{}},
                {'target_node_id':123,'metadata':{}},
            ):
                with self.subTest(link=link):
                    document=self.document(base)
                    document['nodes'][0]['connections']['interfaces'].append(link)
                    with self.assertRaises(ValueError):_build(document,base)

    def test_composed_old_source_record_can_outlive_its_target(self):
        with TemporaryDirectory() as folder:
            base=Path(folder);original={'network':self.document(base)}
            old_source=capture_records(original,['source'])
            current=deepcopy(original)
            current['network']['nodes']=[n for n in current['network']['nodes'] if n['node_id']!='target']
            restored=_build(merge_records(current,old_source)['network'],base)
            self.assertEqual(set(restored.nodes),{'source','other'})
            self.assertEqual([link.target_node_id for link in restored.nodes['source'].interfaces],['source','other'])
            self.assertEqual(len(old_source['source']['node']['connections']['interfaces']),3)


if __name__=='__main__':unittest.main()
