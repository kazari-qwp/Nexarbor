"""Official Paul Graham retrieval example with local BGE-M3; no generation."""
import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.request import urlopen
from datanet.components.nodes.llamaindex_node.paths import PROJECT_ROOT

def main():
    os.environ.setdefault('NLTK_DATA', str(PROJECT_ROOT / '.models' / 'nltk-data'))
    os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(PROJECT_ROOT / '.models' / 'tiktoken-cache'))
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from . import LlamaIndexNode
    folder = PROJECT_ROOT / '.models' / 'research' / 'llamaindex_starter'
    folder.mkdir(parents=True, exist_ok=True)
    text = folder / 'paul_graham_essay.txt'
    url = 'https://raw.githubusercontent.com/run-llama/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt'
    if not text.exists():
        with urlopen(url, timeout=60) as response:
            text.write_bytes(response.read())
    embedding = HuggingFaceEmbedding(model_name=str(PROJECT_ROOT / '.models' / 'bge-m3'), device='cpu', max_length=1024, embed_batch_size=2)
    node = LlamaIndexNode('starter_rag', 'LlamaIndex官方示例', folder / 'index', embed_model=embedding, embedding_config={'model_path': str(PROJECT_ROOT / '.models' / 'bge-m3'), 'device': 'cpu', 'max_length': 1024, 'batch_size': 2})
    if not node.has_index():
        imported = node.invoke_tool('build_index', input_files=[str(text)])
    else:
        node.invoke_tool('load_index')
        imported = {'status': 'loaded', 'documents': 1, 'chunks': len(node.index.index_struct.nodes_dict)}
    node.index = None
    tests = []
    for question in ['What did the author work on before college?', '作者上大学之前主要做什么？']:
        retrieved = node.invoke_tool('search', query=question, top_k=3)
        if not retrieved.items or 'Before college the two main things' not in retrieved.items[0]['text']:
            raise AssertionError('Expected source paragraph was not ranked first')
        tests.append({'question': question, 'retrieval': asdict(retrieved)})
        print(question, retrieved.items[0]['text'][:250], flush=True)
    report = {'source_url': url, 'import': imported, 'tests': tests}
    (folder / 'retrieval_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(imported), flush=True)
if __name__ == '__main__':
    main()
