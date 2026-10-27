"""原知识目录与新 DataNode 的版本、查询、复制和恢复验证。"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from app.network_saver import NetworkSaver
from domain.core import DataNode,Network,NodeInfo
from projects.knowledge_archive.nodes.collection import CollectionNode
from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode

class CollectionNodeTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]
        self.temp=TemporaryDirectory(prefix='.collection-test-',dir=root)
        self.home=Path(self.temp.name).resolve()
        assert self.home.is_relative_to(root)
        self.addCleanup(self.temp.cleanup)
    def node(self,kind='wiki'):
        return CollectionNode(NodeInfo(kind,kind),self.home/kind,storage=kind,schema={'text':'string','count':'integer'} if kind in ('csv','sqlite') else None)
    def saver(self):
        result=NetworkSaver();result.node_types.update(knowledge_collection=CollectionNode,llamaindex=LlamaIndexNode)
        return result
    def command(self,node,op,**args):return node.dataer.write('$command',{'operation':op,'arguments':args})
    def read(self,node,key='guide'):return node.dataer.read({'method':'key','key':key})

    def test_four_collection_backends_use_new_data_nodes(self):
        for kind in ('csv','sqlite','rag','wiki'):
            with self.subTest(kind=kind):
                node=self.node(kind);self.assertIsInstance(node,DataNode)
                value={'text':'原始资料','count':7} if kind in ('csv','sqlite') else '# 资料\n原始正文'
                self.assertEqual(self.command(node,'put',key='guide',value=value).status,'ok')
                record=self.read(node).items[0]
                self.assertEqual(record['content'],value);self.assertEqual(record['node_id'],kind)
                self.assertNotIn('original_path',record)
                self.assertEqual(node.dataer.get_schema()['storage'],kind)

    def test_versions_delete_restore_outline_and_keyword_search(self):
        node=self.node();self.command(node,'put',key='guide',value='# 标题\n## 章节\n原始正文')
        self.command(node,'put',key='guide',value='# 标题\n## 新章节\n修改正文',expected_version=1)
        self.assertEqual(len(self.command(node,'history',key='guide').items),2)
        self.assertTrue(self.command(node,'search',query='修改').items[0]['items'])
        self.assertTrue(self.command(node,'fetch',key='guide',view='outline').items[0]['outline'])
        self.command(node,'remove',key='guide',expected_version=2)
        self.assertTrue(self.read(node).items[0]['deleted'])
        self.command(node,'restore',key='guide',version=1,expected_version=2)
        self.assertIn('原始正文',self.read(node).items[0]['content'])
        self.assertEqual(self.read(node).items[0]['version'],3)

    def test_structured_filters_and_conflicts_preserve_existing_version(self):
        for kind in ('csv','sqlite'):
            node=self.node(kind)
            self.command(node,'put',key='one',value={'text':'one','count':7})
            self.command(node,'put',key='two',value={'text':'two','count':8})
            result=node.dataer.read({'method':'filter','filters':{'count':7}})
            self.assertEqual([v['key'] for v in result.items],['one'])
            with self.assertRaisesRegex(ValueError,'Version conflict'):
                self.command(node,'put',key='one',value={'text':'bad','count':9},expected_version=9)
            self.assertEqual(self.read(node,'one').items[0]['version'],1)

    def test_directory_copy_keeps_history_and_changes_are_independent(self):
        node=self.node();self.command(node,'put',key='guide',value='原始正文')
        saver=self.saver();file=self.home/'network.json';saver.save(Network([node]),file)
        copied=saver.load(file).get('wiki')
        self.assertIsInstance(copied,DataNode);self.assertNotEqual(copied.saver.path,node.saver.path)
        self.assertFalse((copied.saver.path/'.write.lock').exists())
        self.command(copied,'put',key='guide',value='仅副本修改',expected_version=1)
        self.assertEqual(self.read(node).items[0]['content'],'原始正文')
        self.assertEqual(self.read(copied).items[0]['version'],2)
        self.assertEqual(len(self.command(copied,'history',key='guide').items),2)

    def test_reference_save_observes_the_current_directory(self):
        node=self.node();node.save_data=False;self.command(node,'put',key='guide',value='first')
        saver=self.saver();file=self.home/'network.json'
        with patch.object(node.saver,'save',side_effect=AssertionError('不能复制')):saver.save(Network([node]),file)
        self.command(node,'put',key='guide',value='second',expected_version=1)
        loaded=saver.load(file).get('wiki')
        self.assertEqual(loaded.saver.path,node.saver.path);self.assertEqual(self.read(loaded).items[0]['content'],'second')

    def test_failed_directory_save_preserves_previous_config_and_copies(self):
        node=self.node();self.command(node,'put',key='guide',value='before')
        saver=self.saver();file=self.home/'network.json';network=Network([node]);saver.save(network,file)
        before=file.read_bytes();copies=set((self.home/'network_data').iterdir())
        def broken(destination):
            (destination/'partial.txt').write_text('partial',encoding='utf-8');raise OSError('simulated failure')
        with patch.object(node.saver,'save',side_effect=broken),self.assertRaises(OSError):saver.save(network,file)
        self.assertEqual(file.read_bytes(),before);self.assertEqual(set((self.home/'network_data').iterdir()),copies)
        self.assertEqual(self.read(saver.load(file).get('wiki')).items[0]['content'],'before')

    def test_semantic_requires_a_model_and_does_not_use_keyword_fallback(self):
        node=self.node('rag');self.command(node,'put',key='guide',value='原始正文')
        with self.assertRaisesRegex(ValueError,'嵌入模型'):node.dataer.read({'method':'semantic','query':'资料'})

    def test_raw_vector_node_preserves_its_empty_directory_and_config(self):
        config={'model_path':str(self.home/'model'),'device':'cpu','max_length':128,'batch_size':2}
        node=LlamaIndexNode(NodeInfo('vector','vector'),self.home/'index',embedding_config=config)
        self.assertIsInstance(node,DataNode);self.assertFalse(node.dataer.has_index())
        saver=self.saver();file=self.home/'network.json';saver.save(Network([node]),file)
        loaded=saver.load(file).get('vector')
        self.assertIsInstance(loaded,LlamaIndexNode);self.assertFalse(loaded.dataer.has_index())
        self.assertNotEqual(loaded.saver.path,node.saver.path);self.assertEqual(loaded.parameters,node.parameters)

if __name__=='__main__':unittest.main()
