"""A collection is one bounded data node, independent of the number of records."""
from datanet.core.node import Node, NodeResult
from datanet.core.component_registry import NodeCodec, register_node


class CollectionNode(Node):
    def __init__(self, node_id, name, data_kind, directory, collection_id):
        super().__init__(node_id, name, data_kind)
        from pathlib import Path
        self.directory = Path(directory).resolve()
        self.collection_id = collection_id
        self._store = None

    @property
    def store(self):
        if self._store is None:
            from .store import KnowledgeStore
            self._store = KnowledgeStore(self.directory)
        return self._store

    def get_schema(self):
        return self.store.collection(self.collection_id)

    def _read_key(self, key):
        with self.store.connection() as db:
            row = db.execute('SELECT id FROM records WHERE collection_id=? AND (record_key=? OR id=?) AND deleted=0', (self.collection_id,key,key)).fetchone()
        return NodeResult(items=[self.store.fetch(row['id'])]) if row else NodeResult(status='not_found')

    def _read_filter(self, filters):
        return NodeResult(items=self.store.search(collection=self.collection_id, filters=filters)['items'])

    def _read_semantic(self, query, top_k):
        return NodeResult(items=self.store.search(query, collection=self.collection_id, semantic=True, limit=top_k)['items'])

    def write(self, key, value, *, mode='upsert'):
        from datanet.core.write_support import validate_write
        validate_write(key,mode)
        previous=self._read_key(key)
        if mode=='insert' and previous.items:return NodeResult(status='conflict')
        if mode=='update' and not previous.items:return NodeResult(status='not_found')
        return NodeResult(items=[self.store.store(self.collection_id,value,key=key)])


def register():
    from datanet.core.serialization import _path_string
    register_node(NodeCodec('knowledge_collection',CollectionNode,
        lambda n,b:dict(directory=_path_string(n.directory,b),collection_id=n.collection_id),
        lambda c,p,b:CollectionNode(*c,b/p['directory'],p['collection_id']),
        parameter_fields=['directory','collection_id'],description='知识集合：按记录ID、条件或语义读取资料。'))
