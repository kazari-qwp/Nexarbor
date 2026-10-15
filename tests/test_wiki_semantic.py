"""Actual vectors over Wiki pages, including updates, deletion and cold restore."""
import os,unittest
import test_knowledge_base as base


@unittest.skipUnless(os.environ.get('DATANET_TEST_EMBEDDING_MODEL'),'supply local embedding model')
class WikiSemanticTests(unittest.TestCase):
    run_case=base.KnowledgeBaseTests.run_case

    def test_real_wiki_vectors_and_links_survive_updates_and_restart(self):
        self.run_case('''
import tempfile,os
from datanet.knowledge.store import KnowledgeStore
config=dict(model_path=os.environ['DATANET_TEST_EMBEDDING_MODEL'],device='cpu',max_length=512,batch_size=8)
with tempfile.TemporaryDirectory() as folder:
    s=KnowledgeStore(folder,embedding_config=config);wiki=s.create_collection('知识','wiki')
    empty=s.create_collection('空知识','wiki')
    target=s.store(wiki['id'],'口述：测试机青鹭在南楼三层，尚未复核。',key='field',metadata={'title':'现场记录','aliases':['现场']})
    entry=s.store(wiki['id'],'# 项目设备\\n现场位置见 [[field]]。',key='project')
    assert target['index']['status']=='ready'
    hit=s.search('青鹭机器放在哪里',semantic=True,limit=2)['items'][0]
    assert hit['id']==target['id'] and hit['entry']['storage']=='wiki'
    assert hit['matches'][0]['location_verified']
    assert s.fetch(**hit['entry']['read'])['content']==target['content']
    assert s.fetch(entry['id'],view='links')['links'][0]['read']['id']==target['id']
    changed=s.update(target['id'],'口述更正：青鹭已移至北楼二层。',expected_version=1)
    assert changed['index']['status']=='ready'
    cold=KnowledgeStore(folder,embedding_config=config)
    hits=cold.search('青鹭位置',collection=wiki['id'],semantic=True)
    found=next(x for x in hits['items'] if x['id']==target['id'])
    assert found['version']==2 and cold.fetch(**found['entry']['read'])['content']==changed['content']
    assert cold.fetch(target['id'],1)['content']==target['content']
    cold.delete(target['id'],expected_version=2);cold.index(wiki['id'])
    assert all(x['id']!=target['id'] for x in cold.search('青鹭位置',collection=wiki['id'],semantic=True)['items'])
    assert cold.fetch(entry['id'],view='links')['links'][0]['status']=='unresolved'
    assert cold.index(wiki['id'],rebuild=True)['status']=='ready'
''')


if __name__=='__main__':unittest.main()
