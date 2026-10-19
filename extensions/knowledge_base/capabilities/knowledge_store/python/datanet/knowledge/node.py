"""本地知识集合：元数据、正文、版本和索引均属于一个节点。"""
from pathlib import Path
from copy import deepcopy
from datanet.core.node import Node,NodeResult
from datanet.core.component_registry import NodeCodec,register_node

class CollectionNode(Node):
    signal_type = 'knowledge_collection'
    def __init__(self,node_id,name,data_kind,directory,storage='wiki',schema=None,embedding=None,collection_id=None):
        super().__init__(node_id,name,data_kind)
        if storage not in ('csv','sqlite','rag','wiki'):raise ValueError('未知集合存储类型')
        self.directory=Path(directory).resolve();self.storage=storage;self.schema_fields=dict(schema or {});self.embedding=embedding;self.collection_id=collection_id;self._store=None
    def install_local_tools(self):pass
    def resources_restored(self):self._store=None
    @property
    def store(self):
        if self._store is None:
            from .store import KnowledgeStore
            store=KnowledgeStore(self.directory,embedding_config=self.embedding)
            collections=store.catalog(limit=1000)
            if len(collections)>1:raise ValueError('本地知识节点只能拥有一个集合')
            current=collections[0] if collections else store.create_collection(self.name,self.storage,schema=self.schema_fields)
            if current['storage']!=self.storage:raise ValueError('集合存储类型不能覆盖已有数据')
            self.collection_id=current['id'];self._store=store
        return self._store
    def public(self,value):
        if isinstance(value,list):return [self.public(item) for item in value]
        if isinstance(value,dict):return {key:deepcopy(item) if key in ('content','metadata','schema') else self.node_id if key=='node_id' else self.public(item) for key,item in value.items() if key not in ('original_path','archived_path')}
        return value
    def get_schema(self):return self.public(self.store.collection(self.collection_id))
    def _record(self,key):
        store=self.store
        with store.connection() as db:row=db.execute('SELECT id,version,deleted FROM records WHERE collection_id=? AND (record_key=? OR id=?)',(self.collection_id,key,key)).fetchone()
        return dict(store.fetch(row['id'],version=row['version'] if row['deleted'] else None),deleted=bool(row['deleted'])) if row else None
    def _read_key(self,key):
        value=self._record(key)
        return NodeResult(items=[self.public(value)]) if value else NodeResult(status='not_found')
    def _read_filter(self,filters):return NodeResult(items=self.public(self.store.search(collection=self.collection_id,filters=filters)['items']))
    def _read_semantic(self,query,top_k):
        if not self.embedding:raise ValueError('语义检索需要配置本地嵌入模型')
        return NodeResult(items=self.public(self.store.search(query,collection=self.collection_id,semantic=True,limit=top_k)['items']))
    def write(self,key,value,*,mode='upsert'):
        if key=='$command':
            result=self.command(value);result.items=self.public(result.items);return result
        from datanet.core.write_support import validate_write
        validate_write(key,mode)
        previous=self._record(key)
        if mode=='insert' and previous:return NodeResult(status='conflict')
        if mode=='update' and not previous:return NodeResult(status='not_found')
        return NodeResult(items=[self.public(self.store.store(self.collection_id,value,key=key))])
    def command(self,p):
        operation=p['operation'];args=p.get('arguments',{});store=self.store
        if operation=='index':return NodeResult(items=[store.index(self.collection_id)])
        if operation=='search':return NodeResult(items=[store.search(collection=self.collection_id,**args)])
        if operation=='put':return NodeResult(items=[store.store(self.collection_id,args['value'],key=args['key'],metadata=args.get('metadata'),expected_version=args.get('expected_version'))])
        record=self._record(args['key'])
        if record is None:return NodeResult(status='not_found')
        if operation=='fetch':return NodeResult(items=[store.fetch(record['id'],**{k:v for k,v in args.items() if k!='key'})])
        if operation=='history':
            with store.connection() as db:rows=db.execute('SELECT version,hash,metadata,sources_json FROM versions WHERE record_id=? ORDER BY version',(record['id'],)).fetchall()
            return NodeResult(items=[dict(row) for row in rows])
        if operation=='remove':return NodeResult(items=[store.delete(record['id'],expected_version=args.get('expected_version'))])
        if operation=='restore':
            previous=store.fetch(record['id'],version=args['version'])
            return NodeResult(items=[store.store(self.collection_id,previous['content'],key=record['key'],metadata=previous.get('metadata'),expected_version=args.get('expected_version'))])
        raise ValueError('未知本地集合操作')

def register():
    from datanet.core.serialization import _path_string,_fields
    def encode(n,b):return dict(directory=_path_string(n.directory,b),storage=n.storage,schema=n.schema_fields,embedding=n.embedding,collection_id=n.collection_id)
    def decode(c,p,b):
        _fields(p,('directory','storage','schema','embedding','collection_id'),'本地知识集合参数')
        return CollectionNode(*c,b/p['directory'],p['storage'],p['schema'],p['embedding'],p['collection_id'])
    register_node(NodeCodec('knowledge_collection',CollectionNode,encode,decode,parameter_fields=['directory','storage','schema_fields','embedding','collection_id'],resource_directories=('directory',),description='独立的知识集合：CSV、SQLite、RAG 或 Wiki；正文、修订及索引随节点复制。'))
