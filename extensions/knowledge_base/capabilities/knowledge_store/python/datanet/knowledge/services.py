"""Knowledge application services; topology and data policies stay out of core."""
from datanet.core.node import Node
from datanet.core.interface import Interface
from .store import KnowledgeStore
from .node import CollectionNode


def initialize(backend):
    backend.knowledge = KnowledgeStore(backend.directory / 'knowledge')


def restored(backend):
    for node in backend.network.nodes.values():
        if isinstance(node,CollectionNode):node._store=backend.knowledge


def ensure_network(backend):
    store=backend.knowledge
    new_collections=[]
    for id,name in [('knowledge','知识库'),('knowledge/data','知识数据区'),('knowledge/sources','原始资料区')]:
        if id not in backend.network.nodes:
            node=Node(id,name,None);node.management_parent_id='root';backend.network.add_node(node)
    for source,target in [('root','knowledge'),('knowledge','knowledge/data'),('knowledge','knowledge/sources')]:
        node=backend.network.nodes[source]
        if not any(e.target_node_id==target for e in node.read_interfaces):node.read_interfaces.append(Interface(target))
        if not any(e.target_node_id==target for e in node.write_interfaces):node.write_interfaces.append(Interface(target))
    for collection in store.catalog(limit=1000):
        if collection['node_id'] not in backend.network.nodes:
            node=CollectionNode(collection['node_id'],collection['name'],collection['storage'],store.directory,collection['id'])
            node.management_parent_id='root';node._store=store
            backend.network.add_node(node)
            new_collections.append(collection)
        else:backend.network.nodes[collection['node_id']]._store=store
        parent=backend.network.nodes['knowledge/data']
        if not any(e.target_node_id==collection['node_id'] for e in parent.read_interfaces):parent.read_interfaces.append(Interface(collection['node_id']))
        if not any(e.target_node_id==collection['node_id'] for e in parent.write_interfaces):parent.write_interfaces.append(Interface(collection['node_id']))
    connect_workers(backend, new_collections)
    return store


STORAGE_TYPES = ('csv', 'sqlite', 'rag', 'wiki')


def access(backend, actor):
    if actor == 'root':
        task_id = backend.agents.get(actor, {}).get('document_task')
        task = backend.extension_state.get('task_documents', {}).get(task_id, {})
        return dict(read=list(STORAGE_TYPES), write=[] if task.get('mode') == 'read' else list(STORAGE_TYPES))
    binding = backend.agents.get(actor, {})
    grant = binding.get('knowledge_access')
    if not grant:
        raise PermissionError('Actor is outside this knowledge network')
    return grant


def connect_workers(backend, collections=None):
    for actor, binding in backend.agents.items():
        grant = binding.get('knowledge_access')
        if not grant or actor not in backend.network.nodes:
            continue
        node = backend.network.nodes[actor]
        for collection in backend.knowledge.catalog(limit=1000) if collections is None else collections:
            for direction in ('read', 'write'):
                if collection['storage'] in grant[direction]:
                    edges = getattr(node, direction + '_interfaces')
                    if not any(e.target_node_id == collection['node_id'] for e in edges):
                        edges.append(Interface(collection['node_id'], visibility='private'))


def reachable(backend, actor, node_id, mutation=False):
    strength = backend.agents.get(actor, {}).get('maxStrength', 2)
    return any(n.node_id == node_id for n, _ in backend.network.walk(actor,
               direction='write' if mutation else 'read', strength=strength))


def authorize(backend, p, mutation=False, collection=None, storage=None):
    actor = p.get('actor', 'root')
    grant = access(backend, actor)
    if storage is not None and storage not in grant['write' if mutation else 'read']:
        raise PermissionError('Storage type is outside this Agent scope')
    if collection is not None:
        target = backend.knowledge.collection(collection)
        if target['storage'] not in grant['write' if mutation else 'read'] or not reachable(backend, actor, target['node_id'], mutation):
            raise PermissionError('Collection is outside graph access')
    return grant


def operation(name, mutation=False):
    def invoke(backend,p):
        store=backend.knowledge
        if name=='create_collection' and 'knowledge' not in backend.network.nodes:ensure_network(backend)
        grant = authorize(backend, p, mutation, collection=p.get('collection', p.get('target') if name == 'collection' else None), storage=p.get('storage'))
        actor = p.get('actor', 'root')
        if name in ('fetch', 'update', 'delete'):
            # Resolve metadata before fetching content, including historical/deleted records.
            with store.connection() as db:
                row = db.execute('SELECT collection_id FROM records WHERE id=?', (p['id'],)).fetchone()
            if row is None:raise KeyError('Record not found')
            authorize(backend, p, mutation, collection=row['collection_id'])
        if name in ('intake', 'route', 'commit_intake') and actor != 'root':
            task_id = backend.agents[actor].get('document_task')
            task = backend.extension_state.get('task_documents', {}).get(task_id, {})
            if p['id'] not in task.get('references', []):
                raise PermissionError('Intake is outside this task')
        if name == 'stage' and actor != 'root':
            raise PermissionError('Only the entry may admit original materials')
        for source in p.get('sources', []):
            record = store.fetch(source)
            authorize(backend, p, collection=record['collection_id'])
        args={k:v for k,v in p.items() if k!='actor'}
        if name in ('catalog', 'search'):
            allowed = [c for c in store.catalog(limit=1000) if c['storage'] in grant['read'] and reachable(backend, actor, c['node_id'])]
            if name == 'catalog':
                query=args.get('query',''); offset=args.get('offset',0); limit=args.get('limit',50)
                store._page(limit,offset)
                return [c for c in allowed if query in c['name'] or query in c['description']][offset:offset+limit]
            if not args.get('collection'):
                return store.search(**args, allowed_collections=[c['id'] for c in allowed])
        result=getattr(store,name)(**args)
        if name=='create_collection':
            ensure_network(backend)
            authorize(backend, p, mutation, collection=result['id'])
        return result
    return invoke


def register(services):
    services.initializers.append(initialize)
    services.graph_loaders.append(restored)
    services.rpc('knowledge_init',lambda b,p:dict(directory=str(ensure_network(b).directory)),mutation=True)
    for name in ['catalog','collection','fetch','search','query','export','intake','route']:
        services.rpc('knowledge_'+name,operation(name))
    for name in ['create_collection','store','update','delete','stage','commit_intake','index']:
        services.rpc('knowledge_'+name,operation(name,True),mutation=True)
