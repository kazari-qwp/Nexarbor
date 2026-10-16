"""Small shared domain helpers. No town constructor, global world store or dispatcher."""
from copy import deepcopy
from datanet.core.interface import Interface
from datanet.core.access_budget import active_agent,current_access
from datanet.core.node_modules import NodeModule


def instance(b,node,name):return b.modules.get(node,name)
def residents(b):return {m.node.node_id:m for m in b.modules.find('world.resident')}
def clocks(b):return b.modules.find('clock.text')
def clock(b):
    values=clocks(b)
    if len(values)!=1:raise ValueError('A scene requires one clock')
    return values[0]
def tick(b):return clock(b).state['tick']
def date(value):return dict(tick=value,day=value//5+1,slot=('早上','中午','下午','傍晚','午夜')[value%5])
def person(b,actor):return instance(b,actor,'world.resident')
def location(b,actor):return person(b,actor).state['place']
def house(b,actor):
    return next((h for h in b.modules.find('world.household') if actor in h.state['residents']),None)
def require_caller(b,target):
    acting=active_agent.get();frame=current_access.get()
    if not acting or not frame or frame['network'] is not b.network or frame['node_id']!=target:raise PermissionError('Use graph tools; the host supplies caller identity')
    actor=acting[1];person(b,actor)
    return actor

def presence(b,actor,destination):
    node=b.network.nodes[actor]
    old=location(b,actor)
    for source in (actor,):
        for direction in ('read','write'):
            edges=getattr(b.network.nodes[source],direction+'_interfaces')
            edges[:]=[e for e in edges if not e.metadata.attributes.get('world_presence')]
    person(b,actor).state['place']=destination
    # Remove only this resident's old address edges; preserve other people and roads.
    for direction in ('read','write'):
        oldedges=getattr(b.network.nodes[old],direction+'_interfaces')
        oldedges[:]=[e for e in oldedges if not (e.target_node_id==actor and e.metadata.attributes.get('world_presence'))]
        for source,target in ((actor,destination),(destination,actor)):
            edges=getattr(b.network.nodes[source],direction+'_interfaces')
            if not any(e.target_node_id==target and e.metadata.attributes.get('world_presence') for e in edges):
                edges.append(Interface(target,{'threshold':1,'attributes':{'world_presence':True}}))

def take(a,item,n):
    if type(n) is not int or n<1:raise ValueError('Quantity must be a positive integer')
    if item=='coins':
        if a['coins']<n:raise ValueError('Not enough coins')
        a['coins']-=n;return
    if item not in ('wood','ore'):raise ValueError('Only stack resources may be transferred')
    if a['inventory'].get(item,0)<n:raise ValueError('Not enough '+item)
    a['inventory'][item]-=n

def add(a,item,n):
    if item=='coins':a['coins']+=n
    else:a['inventory'][item]=a['inventory'].get(item,0)+n

class ActionModule(NodeModule):
    tools={}
    def install(self):
        for name,spec in self.tools.items():
            self.tool(name,lambda _name=name,**args:self.invoke(_name,args),**spec,read_only=name=='local_info')
    def invoke(self,name,args):
        actor=require_caller(self.backend,self.node.node_id)
        return self.backend.dispatch('scene_action',dict(actor=actor,target=self.node.node_id,module=self.module_name,name=name,arguments=args))
    def apply(self,actor,name,args):raise NotImplementedError
    def check(self,actor,name):
        a=person(self.backend,actor).state
        if self.config.get('address') and a['place']!=self.config['address']:raise PermissionError('Service is outside your current place')
        if name=='local_info':return
        turn=instance(self.backend,actor,'agent.signal').state
        if turn.get('status')!='running' or turn.get('signal_id')!=clock(self.backend).state.get('signal_id'):raise ValueError('No active activity for this resident')
        if a['role']=='child' and name not in ('move_here','talk','rest'):raise PermissionError('Children may move, talk and rest')
        if name!='talk' and a.get('action_tick')==tick(self.backend):raise ValueError('One primary action per time slot; the previous action already took effect')


def action(b,p):
    module=instance(b,p['target'],p['module']);module.check(p['actor'],p['name'])
    # One serial core transaction, rollback all domain values and graph changes on failure.
    saved={(n.node_id,k):deepcopy(spec['state']) for n in b.network.nodes.values() for k,spec in n.modules.items()}
    links={n.node_id:(list(n.read_interfaces),list(n.write_interfaces)) for n in b.network.nodes.values()}
    existing=set(b.network.nodes)
    try:
        value=module.apply(p['actor'],p['name'],p['arguments'])
        if p['name'] not in ('talk','local_info'):
            a=person(b,p['actor']).state;a['action_tick']=tick(b);a['last_result']=dict(ok=True,tool=p['name'],value=deepcopy(value),tick=tick(b))
        return value
    except BaseException:
        for node,key in list(b.modules.instances):
            if node not in existing:b.modules.unmount(node,key)
        for node in set(b.network.nodes)-existing:b.network.nodes.pop(node)
        for (node,key),value in saved.items():
            current=b.network.nodes[node].modules[key]['state'];current.clear();current.update(value)
        for node,(read,write) in links.items():b.network.nodes[node].read_interfaces=read;b.network.nodes[node].write_interfaces=write
        raise

def metadata(b,node):
    if 'world.resident' not in b.network.nodes[node].modules:return {}
    a=person(b,node).state
    pregnant=any(v['carrier']==node and not v.get('child') for m in b.modules.find('world.family') for v in m.state['pregnancies'].values())
    return dict(name=a['name'],initial_goal=a['goal'],background=a.get('background',''),role=a['role'],gender=a.get('gender','unspecified'),can_gestate=a.get('can_gestate',False),life_stage='child' if a['role']=='child' else 'adult',is_parent=bool(a['children']),pregnant=pregnant)

def place_metadata(b,node):
    n=b.network.nodes[node];address=node if 'world.address' in n.modules else next((v['config']['address'] for v in n.modules.values() if 'address' in v['config']),None)
    if not address:return {}
    result=dict(address=address)
    for h in b.modules.find('world.household'):
        if h.config['address']==address:result['residents']=[dict(node_id=x,name=person(b,x).state['name']) for x in h.state['residents']]
    for r in b.modules.find('world.repair'):
        if r.config['address']==address:result['materials']=deepcopy(r.state['materials'])
    return result

def install_metadata(b):
    from datanet.abilities.node_metadata.services import register_provider
    register_provider(b,'npc',lambda node:metadata(b,node))
    register_provider(b,'place',lambda node:place_metadata(b,node),public=True)

def register(s):
    s.graph_loaders.append(install_metadata)
    s.rpc('scene_action',action,mutation=True)
