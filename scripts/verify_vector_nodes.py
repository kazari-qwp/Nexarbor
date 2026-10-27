"""真实本地 BGE + LlamaIndex；验证新 DataNode 的检索、修订和独立目录副本。"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(ROOT/'build/model-cache'),
                  TORCH_HOME=str(ROOT/'build/torch-cache'),PYTHONDONTWRITEBYTECODE='1')


def main():
    import torch
    torch.set_num_threads(2)
    from app.network_saver import NetworkSaver
    from domain.core import DataNode,Network,NodeInfo
    from projects.knowledge_archive.nodes.collection import CollectionNode
    from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode
    model=ROOT/'build/models/bge-small-zh-v1.5'
    if not model.is_dir():raise FileNotFoundError('需要本地模型：'+str(model))
    config=dict(model_path=str(model),device='cpu',max_length=512,batch_size=8)
    def command(node,operation,**args):
        return node.dataer.write('$command',dict(operation=operation,arguments=args)).items[0]
    def semantic(node,query):
        return node.dataer.read(dict(method='semantic',query=query,top_k=2)).items
    start=time.perf_counter()
    with TemporaryDirectory(prefix='.real-vector-',dir=ROOT/'build') as temporary:
        home=Path(temporary).resolve();assert home.is_relative_to(ROOT/'build')
        node=CollectionNode(NodeInfo('knowledge','文档'),home/'source',storage='rag',embedding=config)
        assert isinstance(node,DataNode)
        first=command(node,'put',key='account',value='账号安全指南：如需修改密码，请打开个人设置的安全中心，验证身份后设置新的密码。')
        second=command(node,'put',key='orders',value='订单管理指南：查看历史订单和退货进度，在订单中心申请退款。')
        assert first['index']['status']=='ready',first
        found=semantic(node,'更换登录口令去哪里办理')
        assert found[0]['id']==first['id'],found
        assert found[0]['matches'][0]['location_verified'],found
        print('PASS real embedding: Chinese semantic query and verified passage',flush=True)
        saver=NetworkSaver();saver.node_types.update(knowledge_collection=CollectionNode,llamaindex=LlamaIndexNode)
        file=home/'network.json';saver.save(Network([node]),file)
        backup=home/'source-backup'
        assert node.saver.path.resolve().is_relative_to(home) and backup.resolve().is_relative_to(home)
        node.saver.path.rename(backup)
        copied=saver.load(file).get('knowledge')
        assert semantic(copied,'如何重置账户密码')[0]['id']==first['id']
        changed=command(copied,'put',key='account',value='账号安全指南：修改密码的入口现已迁移至帮助中心的账号恢复页面。',expected_version=1)
        assert changed['index']['status']=='ready',changed
        assert semantic(copied,'账户密码修改入口')[0]['version']==2
        original=CollectionNode(NodeInfo('source','原始资料'),backup,storage='rag',embedding=config)
        assert original.dataer.read(dict(method='key',key='account')).items[0]['version']==1
        print('PASS copied index: source directory moved; independent update and query',flush=True)
        source=home/'direct.md';source.write_text('修改账户密码应进入安全中心，完成身份验证后设置新口令。',encoding='utf-8')
        raw=LlamaIndexNode(NodeInfo('raw','原始向量'),home/'raw-index',embedding_config=config,
                           embed_model=copied.dataer.store.embed_model)
        assert isinstance(raw,DataNode)
        result=raw.dataer.ingest([str(source)])
        assert result['status']=='ok' and result['chunks']>0,result
        assert raw.dataer.search('在哪里更换密码',1).items
        command(copied,'remove',key='account',expected_version=2);command(copied,'index')
        assert all(hit['id']!=first['id'] for hit in semantic(copied,'密码'))
        print('PASS raw LlamaIndex DataNode and deletion/index refresh',flush=True)
        evidence=dict(passed=True,real_embeddings=True,model=str(model),paid_api_calls=0,
                      source_moved_copy_works=True,copy_update_isolated=True,raw_node_is_data_node=True,
                      deletion_filtered=True,elapsed_seconds=round(time.perf_counter()-start,3))
    output=ROOT/'build/migration/vector-node-verification.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
