"""LlamaIndex handles loading, splitting, storage and passage retrieval."""
from pathlib import Path
import json
from threading import RLock
from copy import deepcopy
from hashlib import sha256
from datanet.core.storage_paths import storage_path
from .storage import VersionStorage
from .local_fs import local_filesystem
from datanet.core.node import Node, NodeResult

class LlamaIndexNode(Node):

    def __init__(self, node_id, name, storage_path, *, embed_model=None, embedding_config=None, description=''):
        super().__init__(node_id, name, 'document', description=description)
        self.storage_path = Path(storage_path).resolve()
        if embed_model is None and embedding_config is None:
            raise ValueError('需要嵌入模型或embedding_config')
        self.embedding_config = deepcopy(embedding_config)
        if self.embedding_config is not None:
            config = self.embedding_config
            if not isinstance(config, dict) or set(config) != {'model_path', 'device', 'max_length', 'batch_size'}:
                raise ValueError('embedding_config需要model_path、device、max_length、batch_size')
            if not isinstance(config['model_path'], str) or not config['model_path']:
                raise ValueError('model_path必须是非空字符串')
            if not isinstance(config['device'], str) or not config['device']:
                raise ValueError('device必须是非空字符串')
            if any((type(config[k]) is not int or config[k] < 1 for k in ('max_length', 'batch_size'))):
                raise ValueError('max_length和batch_size必须为正整数')
            config['model_path'] = str(Path(config['model_path']).resolve())
        self._embed_model = embed_model
        self._storage = VersionStorage(self.storage_path)
        self._lock = RLock()
        self._version = None
        self.index = None
        self.chunk_size, self.chunk_overlap = (512, 64)
        query_parameters = {'type': 'object', 'properties': {'query': {'type': 'string'}, 'top_k': {'type': 'integer', 'minimum': 1}}, 'required': ['query'], 'additionalProperties': False}
        self.register_tool('search', self.search, description='语义检索本节点文档，返回原文、相关性和来源，不生成答案', parameters=query_parameters, read_only=True)
        self.register_tool('build_index', self.ingest, description='从指定本地文件全量重建并保存索引；替换当前索引，不是增量追加', parameters={'type': 'object', 'properties': {'input_files': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1}, 'chunk_size': {'type': 'integer', 'minimum': 1}, 'chunk_overlap': {'type': 'integer', 'minimum': 0}}, 'required': ['input_files'], 'additionalProperties': False}, read_only=False)
        self.register_tool('load_index', self.load, description='重新加载本节点已保存的索引，不修改磁盘内容', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}, read_only=True)
        self.register_tool('update_documents', self.update_documents, description='增量导入本地文件：新文档追加，同路径文档未变则跳过，变化则替换；保留其他文档', parameters={'type': 'object', 'properties': {'input_files': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1}}, 'required': ['input_files'], 'additionalProperties': False}, read_only=False)

    @staticmethod
    def _documents(input_files):
        if not isinstance(input_files, list) or not input_files:
            raise ValueError('input_files 必须是非空文件路径列表')
        if any((not isinstance(p, (str, Path)) or not str(p).strip() for p in input_files)):
            raise TypeError('input_files 的每一项必须是文件路径')
        paths = list(dict.fromkeys((str(Path(p).resolve()) for p in input_files)))
        from llama_index.core import SimpleDirectoryReader
        documents = SimpleDirectoryReader(input_files=paths, fs=local_filesystem(), filename_as_id=True, raise_on_error=True, file_metadata=lambda p: {'file_path': str(Path(p).resolve()), 'file_name': Path(p).name, 'source_sha256': sha256(storage_path(p).read_bytes()).hexdigest()}).load_data()
        for document in documents:
            document.excluded_embed_metadata_keys=list(dict.fromkeys([*document.excluded_embed_metadata_keys,'file_path','file_name','source_sha256']))
        if not documents:
            raise ValueError('未读取到文档')
        return documents

    @property
    def embed_model(self):
        if self._embed_model is None:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            config = self.embedding_config
            self._embed_model = HuggingFaceEmbedding(model_name=config['model_path'], local_files_only=True, device=config['device'], max_length=config['max_length'], embed_batch_size=config['batch_size'])
        return self._embed_model

    def _load_folder(self, folder):
        from llama_index.core import StorageContext, load_index_from_storage
        from llama_index.core.node_parser import SentenceSplitter
        settings = json.loads((folder / 'node_config.json').read_text(encoding='utf-8'))
        index = load_index_from_storage(StorageContext.from_defaults(persist_dir=str(folder),fs=local_filesystem()), embed_model=self.embed_model, transformations=[SentenceSplitter(**settings)])
        return (index, settings)

    def _publish(self, candidate, chunk_size, chunk_overlap):
        version, (restored, settings) = self._storage.commit(candidate, {'chunk_size': chunk_size, 'chunk_overlap': chunk_overlap}, self._load_folder)
        self.index = restored
        self._version = version
        self.chunk_size, self.chunk_overlap = (settings['chunk_size'], settings['chunk_overlap'])

    def has_index(self):
        return (self.storage_path / 'current.json').exists()

    def ingest(self, input_files, *, chunk_size=512, chunk_overlap=64):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._storage.lock:
            return self._ingest(input_files, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def _ingest(self, input_files, *, chunk_size=512, chunk_overlap=64):
        if not isinstance(input_files, list) or not input_files:
            raise ValueError('input_files 必须是非空文件路径列表')
        if any((not isinstance(p, (str, Path)) or not str(p).strip() for p in input_files)):
            raise TypeError('input_files 的每一项必须是文件路径')
        if type(chunk_size) is not int or type(chunk_overlap) is not int:
            raise TypeError('chunk_size 和 chunk_overlap 必须为整数')
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError('需要 0 <= chunk_overlap < chunk_size')
        from llama_index.core import VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter
        documents = self._documents(input_files)
        index = VectorStoreIndex.from_documents(documents, embed_model=self.embed_model, transformations=[SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)])
        self._publish(index, chunk_size, chunk_overlap)
        return {'status': 'ok', 'documents': len(documents), 'chunks': len(index.index_struct.nodes_dict)}

    def load(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._storage.lock:
            self._refresh()
        return {'status': 'ok', 'chunks': len(self.index.index_struct.nodes_dict), 'storage_path': str(self.storage_path)}

    def _refresh(self, force=True):
        version = self._storage.version()
        if version is None:
            raise FileNotFoundError('尚未建立版本化索引，请调用build_index或update_documents')
        if force or self.index is None or version != self._version:
            candidate, settings = self._load_folder(self._storage.folder(version))
            self.index = candidate
            self.chunk_size, self.chunk_overlap = (settings['chunk_size'], settings['chunk_overlap'])
            self._version = version

    def update_documents(self, input_files):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._storage.lock:
            return self._update_documents(input_files)

    def delete_documents(self, input_files):
        paths={str(Path(path).resolve()) for path in input_files}
        self.storage_path.parent.mkdir(parents=True,exist_ok=True)
        with self._lock,self._storage.lock:
            if not self.has_index():return {'status':'ok','deleted':0}
            self._ensure_index()
            candidate,_=self._load_folder(self._storage.folder(self._version))
            ids=[id for id,info in candidate.ref_doc_info.items() if info.metadata.get('file_path') in paths]
            for id in ids:candidate.delete_ref_doc(id,delete_from_docstore=True)
            if ids:self._publish(candidate,self.chunk_size,self.chunk_overlap)
            return {'status':'ok','deleted':len(ids)}

    def _update_documents(self, input_files):
        documents = self._documents(input_files)
        if not self.has_index():
            return {**self._ingest(input_files), 'added': len(documents), 'updated': 0, 'skipped': 0}
        self._ensure_index()
        counts = {'added': 0, 'updated': 0, 'skipped': 0}
        for document in documents:
            old_hash = self.index.docstore.get_document_hash(document.id_)
            action = 'added' if old_hash is None else 'skipped' if old_hash == document.hash else 'updated'
            counts[action] += 1
        if counts['added'] or counts['updated']:
            candidate, _ = self._load_folder(self._storage.folder(self._version))
            candidate.refresh_ref_docs(documents)
            self._publish(candidate, self.chunk_size, self.chunk_overlap)
        return {'status': 'ok', **counts, 'chunks': len(self.index.index_struct.nodes_dict)}

    def _ensure_index(self):
        self._refresh(force=False)

    def _result(self, hits):
        return NodeResult(status='ok' if hits else 'not_found', items=[{'chunk_id': h.node.node_id, 'text': h.node.get_content(), 'metadata': h.node.metadata, 'score': h.score, 'start_char': h.node.start_char_idx, 'end_char': h.node.end_char_idx} for h in hits], sources=[{'node_id': self.node_id, 'storage': str(self.storage_path), 'chunk_id': h.node.node_id, **h.node.metadata} for h in hits])

    def _read_semantic(self, query, top_k):
        return self.search(query, top_k)

    def search(self, query, top_k=5):
        self._validate_query(query, top_k)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._storage.lock:
            self._ensure_index()
            return self._result(self.index.as_retriever(similarity_top_k=top_k).retrieve(query))

    @staticmethod
    def _validate_query(query, top_k):
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query 必须是非空字符串')
        if type(top_k) is not int or top_k < 1:
            raise ValueError('top_k 必须为正整数')

    def get_schema(self):
        return {'kind': 'llamaindex', 'read_methods': ['semantic'], 'storage_path': str(self.storage_path)}
