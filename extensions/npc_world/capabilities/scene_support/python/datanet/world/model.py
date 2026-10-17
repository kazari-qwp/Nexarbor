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
    if old!=destination:
        # Only witnesses sharing the departure place learn this direction. Future
        # unseen moves do not update their observation or expose live whereabouts.
        for other,m in residents(b).items():
            if other==actor:continue
            if m.state['place']==old:
                m.state.setdefault('departures',{})[actor]=dict(origin=old,destination=destination,name=b.network.nodes[destination].name,tick=tick(b))
            elif m.state['place']==destination:
                m.state.get('departures',{}).pop(actor,None)
    node.interfaces[:]=[e for e in node.interfaces if not e.metadata.attributes.get('world_presence')]
    person(b,actor).state['place']=destination
    oldedges=b.network.nodes[old].interfaces
    oldedges[:]=[e for e in oldedges if not(e.target_node_id==actor and e.metadata.attributes.get('world_presence'))]
    for source,target in ((actor,destination),(destination,actor)):
        b.network.nodes[source].connect(target,channels=('access.read','access.write'),threshold=1,attributes={'world_presence':True})


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



def action(b,p):
    module=instance(b,p['target'],p['module']);module.check(p['actor'],p['name'])
    # One serial core transaction, rollback all domain values and graph changes on failure.
    saved={(n.node_id,k):deepcopy(spec['state']) for n in b.network.nodes.values() for k,spec in n.modules.items()}
    links={n.node_id:list(n.interfaces) for n in b.network.nodes.values()}
    existing=set(b.network.nodes)
    budget=instance(b,p['actor'],'action.budget')
    try:
        budget.check(action=p['name'],period=tick(b))
        value=module.apply(p['actor'],p['name'],p['arguments'])
        events=b.modules.instances.get((p['target'],'probability.events'))
        if events and events.active and (not events.owner or events.owner in b.components.enabled) and p['name']!='local_info' and 'waiting_for' not in value:
            a=person(b,p['actor']).state
            serial=a.setdefault('successful_actions',0)+1
            action_id=str(tick(b))+':'+p['actor']+':'+str(serial)
            def effects(items):
                for effect in items:
                    if set(effect)!={'item','quantity'} or not isinstance(effect['item'],str) or type(effect['quantity']) is not int or effect['quantity']<1:raise ValueError('Reward requires item and positive integer quantity')
                    add(a,effect['item'],effect['quantity'])
                return items
            observations=events.draw(action_id,p['name'],effects)
            a['successful_actions']=serial
            if observations:value={**value,'events':observations}
        receipt=budget.status(period=tick(b)) if p['name']=='local_info' else budget.charge(action=p['name'],period=tick(b))
        value={**value,'action_budget':dict(cost=0,**receipt) if p['name']=='local_info' else receipt}
        if p['name']!='local_info':
            person(b,p['actor']).state['last_result']=dict(ok=True,tool=p['name'],value=deepcopy(value),tick=tick(b))
        return value
    except BaseException:
        for node,key in list(b.modules.instances):
            if node not in existing:b.modules.unmount(node,key)
        for node in set(b.network.nodes)-existing:b.network.nodes.pop(node)
        for (node,key),value in saved.items():
            current=b.network.nodes[node].modules[key]['state'];current.clear();current.update(value)
        for node,edges in links.items():b.network.nodes[node].interfaces=edges
        raise

def metadata(b,node):
    if 'world.resident' not in b.network.nodes[node].modules:return {}
    a=person(b,node).state
    pregnant=any(v['carrier']==node and not v.get('child') for m in b.modules.find('world.family') for v in m.state['pregnancies'].values())
    return dict(name=a['name'],background=a.get('background',''),role=a['role'],gender=a.get('gender','unspecified'),can_gestate=a.get('can_gestate',False),life_stage='child' if a['role']=='child' else 'adult',is_parent=bool(a['children']),pregnant=pregnant)

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
