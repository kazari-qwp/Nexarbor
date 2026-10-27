"""真实嵌入计算进程：验证主线程加载、管道请求与迁移后的 Dataer。"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(DATANET_DEFER_VECTORS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                  HF_HOME=str(ROOT/'build/model-cache'),PYTHONDONTWRITEBYTECODE='1')
from domain.core import DataNode,NodeInfo
from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode
from projects.knowledge_archive.nodes.vector import startup


def main():
    model=ROOT/'build/models/bge-small-zh-v1.5'
    if not model.is_dir():raise FileNotFoundError(model)
    config=dict(model_path=str(model),device='cpu',max_length=128,batch_size=2)
    with TemporaryDirectory(prefix='.vector-worker-',dir=ROOT/'build') as temporary:
        home=Path(temporary).resolve();assert home.is_relative_to(ROOT/'build')
        startup.initialize(home)
        try:
            assert startup.status()['torch_imported'] is False
            file=home/'account.md';file.write_text('修改账户密码需要在安全中心完成身份验证。',encoding='utf-8')
            node=LlamaIndexNode(NodeInfo('worker','计算节点'),home/'index',embedding_config=config)
            assert isinstance(node,DataNode)
            assert node.dataer.ingest([str(file)])['status']=='ok'
            result=node.dataer.search('如何更换密码',1)
            assert result.items and '安全中心' in result.items[0]['text']
            status=startup.status()
            assert status['state']=='ready' and status['torch_imported'] is False,status
            assert status['worker']['loaded_on_main_thread'] is True,status
            assert status['worker']['torch_imported'] is True,status
            evidence=dict(passed=True,real_embeddings=True,paid_api_calls=0,
                          scientific_imports_only_in_worker=True,worker=status['worker'])
        finally:startup.close()
    output=ROOT/'build/migration/vector-worker-verification.json'
    output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=='__main__':main()
