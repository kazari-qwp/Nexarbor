"""Persistent explicit context-source recipes. No Agent-visible mutation tools."""
from copy import deepcopy
from pathlib import Path
from datanet.core.json_values import freeze
from datanet.core.agent_inputs import identifier

KINDS={'system_prompt','context','inputs','tail'}

def state(b):return b.extension_state.setdefault('context_assembly',dict(nodes={},bindings={},matches={}))
def host(p):
    if p.get('actor')!='root':raise PermissionError('Only the host configures context assembly')
def configure(b,p):
    host(p);node=p['node_id']
    if node not in b.network.nodes:raise ValueError('Assembly node does not exist')
    sources=deepcopy(p['sources']);freeze(sources)
    if not isinstance(sources,list):raise ValueError('Context sources must be a list')
    seen=set();roots=[str(Path(x).resolve()) for x in p.get('document_roots',[])]
    for spec in sources:
        if not isinstance(spec,dict) or set(spec)-{'id','kind','source','when','order','name','reference_only','event_id','delivery'}:raise ValueError('Invalid context source')
        key=identifier(spec['id'])
        if key.startswith('state:'):raise ValueError('state: is reserved for applicability snapshots')
        if key in seen:raise ValueError('Duplicate context source ID')
        seen.add(key)
        if spec['kind'] not in KINDS:raise ValueError('Invalid context delivery kind')
        if not isinstance(spec.get('when',{}),dict) or type(spec.get('order',0)) is not int:raise ValueError('Invalid context conditions/order')
        src=spec['source'];kind=src.get('type')
        allowed={'text':{'type','text'},'node':{'type','target','key'},'file':{'type','path'},'resource':{'type','component','file'}}
        required={'text':{'type','text'},'node':{'type','target'},'file':{'type','path'},'resource':{'type','component','file'}}
        if kind not in allowed or set(src)-allowed[kind] or not required[kind]<=set(src):raise ValueError('Invalid context source descriptor')
        if kind=='text' and not isinstance(src['text'],str):raise ValueError('Source text must be a string')
        if kind=='file':
            path=Path(src['path'])
            if not path.is_absolute():raise ValueError('Document paths must be absolute')
            path=path.resolve()
            if not any(path.is_relative_to(Path(root)) for root in roots):raise PermissionError('Document is outside the host-granted roots')
            src['path']=str(path)
        if spec['kind']=='inputs':identifier(spec['event_id'])
        if spec.get('reference_only') and (spec['kind']!='context' or kind!='node'):raise ValueError('Reference-only requires a context node source')
    state(b)['nodes'][node]=dict(sources=sources,document_roots=roots)
    return dict(node_id=node)
def bind(b,p):
    host(p)
    from datanet.core.agent_node import AgentNode
    if not isinstance(b.network.nodes[p['target']],AgentNode):raise TypeError('Context recipient requires an Agent node')
    if p['node_id'] not in state(b)['nodes']:raise ValueError('Assembly node is not configured')
    nodes=state(b)['bindings'].setdefault(p['target'],[])
    if p['node_id'] not in nodes:nodes.append(p['node_id'])
    return dict(bound=True)
def get(b,p):return deepcopy(state(b)['matches'].get(p['target'],{}).get(p['node_id']))
def put(b,p):
    host(p);freeze(p['value']);state(b)['matches'].setdefault(p['target'],{})[p['node_id']]=deepcopy(p['value']);return dict(saved=True)
def register(s):
    for name,fn,mut in [('configure',configure,True),('bind',bind,True),('get',get,False),('put',put,True)]:s.rpc('context_assembly_'+name,fn,mutation=mut)
