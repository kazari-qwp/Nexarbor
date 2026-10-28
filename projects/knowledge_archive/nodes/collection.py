"""原知识集合通过 Dataer 访问；目录、修订、索引均由新 DataNode 持有。"""
from pathlib import Path
from copy import deepcopy
from filelock import FileLock
from domain.core import DataNode, NodeInfo
from domain.data_result import DataResult
from domain.record_dataer import RecordDataer
from .files import DirectoryData, DirectorySaver

class CollectionDataer(RecordDataer):

    def __init__(self, node_id, name, directory, storage='wiki', schema=None, embedding=None, collection_id=None):
        self.node_id = node_id
        self.name = name
        if storage not in ('csv', 'sqlite', 'rag', 'wiki'):
            raise ValueError('未知集合存储类型')
        self.directory = Path(directory).resolve()
        self.storage = storage
        self.schema_fields = dict(schema or {})
        self.embedding = embedding
        self.collection_id = collection_id
        self._store = None

    def resources_restored(self):
        self._store = None

    @property
    def store(self):
        if self._store is None:
            if self.collection_id:
                from ..modules.knowledge_catalog.store import KnowledgeStore
                store=KnowledgeStore(self.directory,embedding_config=self.embedding,owner_node=self.node_id)
            else:
                from ..storage.knowledge import KnowledgeStore
                store=KnowledgeStore(self.directory,embedding_config=self.embedding)
            collections = store.catalog(limit=1000)
            if len(collections) > 1:
                raise ValueError('本地知识节点只能拥有一个集合')
            current = collections[0] if collections else store.create_collection(self.name,self.storage,schema=self.schema_fields,**({'collection_id':self.collection_id} if self.collection_id else {}))
            if current['storage'] != self.storage:
                raise ValueError('集合存储类型不能覆盖已有数据')
            self.collection_id = current['id']
            self._store = store
        return self._store

    def public(self, value):
        if isinstance(value, list):
            return [self.public(item) for item in value]
        if isinstance(value, dict):
            return {key: deepcopy(item) if key in ('content', 'metadata', 'schema') else self.node_id if key == 'node_id' else self.public(item) for key, item in value.items() if key not in ('original_path', 'archived_path')}
        return value

    def get_schema(self):
        return self.public(self.store.collection(self.collection_id))

    def _record(self, key):
        store = self.store
        with store.connection() as db:
            row = db.execute('SELECT id,version,deleted FROM records WHERE collection_id=? AND (record_key=? OR id=?)', (self.collection_id, key, key)).fetchone()
        return dict(store.fetch(row['id'], version=row['version'] if row['deleted'] else None), deleted=bool(row['deleted'])) if row else None

    def _read_key(self, key):
        value = self._record(key)
        return DataResult(items=[self.public(value)]) if value else DataResult(status='not_found')

    def _read_filter(self, filters):
        return DataResult(items=self.public(self.store.search(collection=self.collection_id, filters=filters)['items']))

    def _read_semantic(self, query, top_k):
        if not self.embedding:
            raise ValueError('语义检索需要配置本地嵌入模型')
        return DataResult(items=self.public(self.store.search(query, collection=self.collection_id, semantic=True, limit=top_k)['items']))

    def write(self, key, value, *, mode='upsert'):
        if key == '$command':
            result = self.command(value)
            result.items = self.public(result.items)
            return result
        from domain.data_write import validate_write
        validate_write(key, mode)
        previous = self._record(key)
        if mode == 'insert' and previous:
            return DataResult(status='conflict')
        if mode == 'update' and (not previous):
            return DataResult(status='not_found')
        return DataResult(items=[self.public(self.store.store(self.collection_id, value, key=key))])

    def command(self, p):
        operation = p['operation']
        args = p.get('arguments', {})
        store = self.store
        if operation == 'index':
            return DataResult(items=[store.index(self.collection_id)])
        if operation == 'search':
            return DataResult(items=[store.search(collection=self.collection_id, **args)])
        if operation == 'put':
            return DataResult(items=[store.store(self.collection_id, args['value'], key=args['key'], metadata=args.get('metadata'), expected_version=args.get('expected_version'))])
        record = self._record(args['key'])
        if record is None:
            return DataResult(status='not_found')
        if operation == 'fetch':
            return DataResult(items=[store.fetch(record['id'], **{k: v for k, v in args.items() if k != 'key'})])
        if operation == 'history':
            with store.connection() as db:
                rows = db.execute('SELECT version,hash,metadata,sources_json FROM versions WHERE record_id=? ORDER BY version', (record['id'],)).fetchall()
            return DataResult(items=[dict(row) for row in rows])
        if operation == 'remove':
            return DataResult(items=[store.delete(record['id'], expected_version=args.get('expected_version'))])
        if operation == 'restore':
            previous = store.fetch(record['id'], version=args['version'])
            return DataResult(items=[store.store(self.collection_id, previous['content'], key=record['key'], metadata=previous.get('metadata'), expected_version=args.get('expected_version'))])
        raise ValueError('未知本地集合操作')


class CollectionSaver(DirectorySaver):
    kind = "knowledge_collection"


class CollectionNode(DataNode):
    node_type = 'knowledge_collection'
    def __init__(self, info: NodeInfo, path: str | Path, storage="wiki", schema=None, embedding=None, collection_id=None, *, save_data: bool = True):
        data = DirectoryData(Path(path))
        dataer = CollectionDataer(info.node_id, info.name, data.path, storage, schema, embedding, collection_id)
        super().__init__(info, dataer=dataer, saver=CollectionSaver(data, FileLock(str(data.path / ".write.lock"), timeout=30)), save_data=save_data)

    @property
    def parameters(self) -> dict:
        return {"storage": self.dataer.storage, "schema": dict(self.dataer.schema_fields),
                "embedding": deepcopy(self.dataer.embedding), "collection_id": self.dataer.collection_id}
