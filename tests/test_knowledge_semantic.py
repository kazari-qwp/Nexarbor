"""Real local embeddings and persisted LlamaIndex; supply a model folder to enable."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get('DATANET_TEST_EMBEDDING_MODEL'),'local model is supplied separately')
class SemanticKnowledgeTests(unittest.TestCase):
    def test_real_chinese_retrieval_update_delete_and_restore(self):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),DATANET_COMPONENT_ROOT=str(ROOT/'extensions/knowledge_base'),
                 DATANET_COMPONENT_PROFILE='{}',DATANET_COMPONENT_SELECTION='["capabilities/knowledge_store"]',
                 HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        script="""
import tempfile,os,json,time,statistics,shutil
from pathlib import Path
import torch
torch.set_num_threads(2)
from datanet.knowledge.store import KnowledgeStore
from datanet.core.storage_paths import storage_path
config=dict(model_path=os.environ['DATANET_TEST_EMBEDDING_MODEL'],device='cpu',max_length=512,batch_size=8)
with tempfile.TemporaryDirectory() as folder:
    directory=storage_path(Path(folder)/('long-'+'a'*100)/('nested-'+'b'*100)) if os.name=='nt' else Path(folder)
    if os.name=='nt':assert len(str(directory))>260
    start=time.perf_counter();s=KnowledgeStore(directory,embedding_config=config);c=s.create_collection('文档','rag')
    a=s.store(c['id'],'账号安全指南：如需修改密码，请打开个人设置的安全中心，验证身份后设置新的密码。',key='account')
    b=s.store(c['id'],'订单管理指南：查看历史订单和退货进度，在订单中心申请退款。',key='orders')
    assert a['index']['status']=='ready',a['index']
    hits=s.search('更换登录口令去哪里办理',collection=c['id'],semantic=True,limit=2)
    assert hits['items'][0]['id']==a['id'],hits
    match=hits['items'][0]['matches'][0]
    assert match['location_verified'],match
    section=s.fetch(**match['section_fetch'])
    assert '密码' in section['content'] and section['version']==1
    assert s.index(c['id'],rebuild=True)['status']=='ready'
    cold=time.perf_counter()-start
    times=[]
    for _ in range(5):
        start=time.perf_counter();s.search('如何重置账户密码',collection=c['id'],semantic=True);times.append(time.perf_counter()-start)
    changed=s.update(a['id'],'账号安全指南：修改密码的入口现已迁移至帮助中心的账号恢复页面。',expected_version=1)
    assert changed['index']['status']=='ready',changed['index']
    restored=KnowledgeStore(directory,embedding_config=config)
    hits=restored.search('账户密码修改入口',collection=c['id'],semantic=True)
    assert hits['items'][0]['id']==a['id']
    assert restored.fetch(a['id'])['version']==2
    restored.delete(a['id'],expected_version=2);restored.index(c['id'])
    assert all(h['id']!=a['id'] for h in restored.search('密码',collection=c['id'],semantic=True)['items'])
    metrics=dict(cold_ingest_seconds=round(cold,3),warm_query_p50_ms=round(statistics.median(times)*1000,2),warm_query_max_ms=round(max(times)*1000,2),queries=len(times),real_embeddings=True)
    Path('build/knowledge-semantic-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False))
    if os.name=='nt':
        cleanup=storage_path(folder)
        assert cleanup.parent==storage_path(tempfile.gettempdir())
        shutil.rmtree(cleanup)
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())


    def test_component_startup_then_real_embedding_in_rpc_worker(self):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),DATANET_COMPONENT_ROOT=str(ROOT/'extensions/knowledge_base'),
                 DATANET_COMPONENT_PROFILE='{}',DATANET_COMPONENT_SELECTION='["capabilities/knowledge_store"]',
                 HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        script="""
import tempfile,os,sys
from concurrent.futures import ThreadPoolExecutor
from datanet.core.backend import Backend
with tempfile.TemporaryDirectory() as directory:
    backend=Backend(directory)
    assert 'scipy.special' in sys.modules and 'llama_index.embeddings.huggingface' in sys.modules
    backend.knowledge.embedding_config=dict(model_path=os.environ['DATANET_TEST_EMBEDDING_MODEL'],device='cpu',max_length=512,batch_size=8)
    with ThreadPoolExecutor(max_workers=1) as workers:
        collection=workers.submit(backend.knowledge.create_collection,'工作线程资料','rag').result(timeout=15)
        stored=workers.submit(backend.knowledge.store,collection['id'],'修改密码应进入账户安全中心。',key='account').result(timeout=45)
        assert stored['index']['status']=='ready',stored['index']
        found=workers.submit(backend.knowledge.search,'哪里重置账户口令',collection=collection['id'],semantic=True).result(timeout=15)
        assert found['items'][0]['id']==stored['id']
    backend.close()
print('PASS optional component startup followed by real embedding/index/search in RPC worker')
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf8',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())

if __name__=='__main__':unittest.main()

