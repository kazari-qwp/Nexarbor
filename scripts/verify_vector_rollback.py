"""真实 BGE/LlamaIndex 的节点事务回滚与索引缓存恢复。"""

import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HOME=str(ROOT / 'build/model-cache'),
                  TORCH_HOME=str(ROOT / 'build/torch-cache'), PYTHONDONTWRITEBYTECODE='1')


def main():
    import torch
    torch.set_num_threads(2)
    from app.transactions import NodeLocks, NodeSnapshots
    from domain.core import Network, NodeInfo
    from projects.knowledge_archive.nodes.collection import CollectionNode
    from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode
    model = ROOT / 'build/models/bge-small-zh-v1.5'
    config = dict(model_path=str(model), device='cpu', max_length=128, batch_size=4)
    started = time.perf_counter()
    with TemporaryDirectory(prefix='.vector-rollback-', dir=ROOT / 'build') as temporary:
        directory = Path(temporary)
        node = CollectionNode(NodeInfo('rag', 'RAG'), directory / 'knowledge', storage='rag', embedding=config)
        def put(text, version=None):
            arguments = dict(key='guide', value=text)
            if version is not None:arguments['expected_version'] = version
            return node.dataer.write('$command', dict(operation='put', arguments=arguments)).items[0]
        put('修改账号口令需要前往安全中心，完成身份验证。')
        assert node.dataer.read(dict(method='semantic', query='哪里更换密码', top_k=1)).items
        previous_store = node.dataer.store
        network = Network([node])
        locks = NodeLocks(network, NodeSnapshots(network, directory))
        async def rollback_collection():
            try:
                async with locks.transaction(['rag']):
                    updated = put('临时指引：前往云朵广场使用飞象凭证。', 1)
                    assert updated['index']['status'] == 'ready', updated
                    raise ValueError('rollback')
            except ValueError:
                pass
        asyncio.run(rollback_collection())
        assert node.dataer._store is None
        restored = node.dataer.read(dict(method='key', key='guide')).items[0]
        assert restored['version'] == 1 and '安全中心' in restored['content'], restored
        hits = node.dataer.read(dict(method='semantic', query='更换密码的地点', top_k=1)).items
        wire = json.dumps(hits, ensure_ascii=False)
        assert hits and '安全中心' in wire and '飞象' not in wire, hits
        assert node.dataer.store is not previous_store
        print('PASS real RAG rollback: revision, vector files, cache and query restored', flush=True)
        original = directory / 'original.md'
        original.write_text('蓝鲸口令的设置地点是安全中心。', encoding='utf-8')
        transient = directory / 'transient.md'
        transient.write_text('飞象凭证的领取地点是云朵广场。', encoding='utf-8')
        raw = LlamaIndexNode(NodeInfo('raw', 'Raw'), directory / 'raw', embedding_config=config,
                            embed_model=node.dataer.store.embed_model)
        assert raw.dataer.ingest([str(original)])['status'] == 'ok'
        network = Network([raw])
        locks = NodeLocks(network, NodeSnapshots(network, directory))
        async def rollback_raw():
            try:
                async with locks.transaction(['raw']):
                    assert raw.dataer.ingest([str(transient)])['status'] == 'ok'
                    assert any('飞象' in row['text'] for row in raw.dataer.search('飞象凭证', 2).items)
                    raise ValueError('rollback')
            except ValueError:
                pass
        asyncio.run(rollback_raw())
        assert raw.dataer.index is None and raw.dataer._version is None
        found = raw.dataer.search('口令凭证在哪里', 3).items
        assert found and any('蓝鲸' in row['text'] for row in found), found
        assert all('飞象' not in row['text'] for row in found), found
        print('PASS raw LlamaIndex rollback: transient document removed from restored index', flush=True)
        evidence = dict(passed=True, real_embeddings=True, paid_api_calls=0, rag_revision_restored=True,
                        rag_cache_invalidated=True, raw_cache_invalidated=True, transient_vector_removed=True,
                        elapsed_seconds=round(time.perf_counter() - started, 3))
    output = ROOT / 'build/migration/vector-rollback-verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == '__main__':
    main()
