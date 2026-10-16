"""World state and graph are committed together by the existing checkpoint service."""
from copy import deepcopy
from datanet.core.interface import Interface
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
from datanet.core.pulse_node import PulseNode
from datanet.world.nodes import WorldNode,Resident
from datanet.world import profiles


SLOTS=('早上','中午','下午','傍晚','午夜')
def address(place):return 'world/place/'+place
def business(place):return 'world/service/'+place
def clock(tick):return dict(tick=tick,day=tick//5+1,slot=SLOTS[tick%5])

def state(b):return b.extension_state.get('npc_world')

def home_of(w,actor):return next((place for place,members in w['housing'].items() if actor in members),None)

def may_rest(w,actor,place):return actor in w['housing'].get(place,[])

def place_metadata(b,node_id):
    w=state(b);node=b.network.nodes.get(node_id)
    if not w or not isinstance(node,WorldNode):return {}
    value=dict(place_id=node.place)
    if node.place in w['housing']:
        value['residents']=[dict(node_id=actor,name=w['actors'][actor]['name']) for actor in w['housing'][node.place]]
    if node.place=='smithy':value['materials']=deepcopy(w['smith_stock'])
    return value

def require(b,actor):
    w=state(b)
    if not w or actor not in w['actors']:raise PermissionError('Not a world resident')
    return w,w['actors'][actor]

def edge(b,source,target,directions=('read','write')):
    for direction in directions:
        links=getattr(b.network.nodes[source],direction+'_interfaces')
        if not any(x.target_node_id==target for x in links):links.append(Interface(target,{'threshold':1}))

def presence(b,w):
    # Rebuild only the presence edges; road and business connections remain fixed.
    npcs=set(w['actors'])
    for node in b.network.nodes.values():
        if isinstance(node,WorldNode) and node.kind=='address':
            for d in ('read','write'):
                setattr(node,d+'_interfaces',[x for x in getattr(node,d+'_interfaces') if x.target_node_id not in npcs])
    for actor,a in w['actors'].items():
        n=b.network.nodes[actor]
        n.read_interfaces=[];n.write_interfaces=[]
        edge(b,actor,address(a['place']));edge(b,address(a['place']),actor)
        edge(b,actor,'world/common',('read',))
        n.read_interfaces.append(Interface(profiles.context_id(actor),{'threshold':1,'visibility':'private'}))
        n.write_interfaces.append(Interface('world/pulse',{'threshold':1,'channels':['world.tick']}))
    profiles.sync(b,w)

def create_resident(b,actor,a):
    if actor not in b.network.nodes:
        n=Resident(actor,a['name'],file_path=b.directory/'world'/'memories'/(actor.rsplit('/',1)[-1]+'.md'),
                   creation_options=dict(identity=actor,world='small_town'),description=a['name'])
        n.write_memory('# '+a['name']+'的私人记忆\n'+a.get('background','')+'\n')
        b.network.add_node(n)
    if profiles.context_id(actor) not in b.network.nodes:
        from datanet.core.node import Node
        b.network.add_node(Node(profiles.context_id(actor),a['name']+'的上下文装配',None))
    if hasattr(b,'world_tools'):b.world_tools(b,b.network.nodes[actor])

def initialize(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the world operator initializes the map')
    if state(b):
        b.network.nodes['world/common'].write('content',p['common'])
        return dict(existing=True,clock=clock(state(b)['tick']))
    config=deepcopy(p['config'])
    w=dict(tick=0,config=config,actors={},round={},intents={},results={},events=[],pregnancies={},families=[],
           shop=deepcopy(config['shop']),smith_stock=deepcopy(config['smith_stock']),last_settled=None)
    w['housing']={place:['world/npc/'+person for person in members] for place,members in config['households'].items()}
    residents=[person for members in w['housing'].values() for person in members]
    valid={'world/npc/'+person['id'] for person in config['npcs']}
    if len(residents)!=len(set(residents)) or not set(residents)<=valid:raise ValueError('Invalid or duplicate household residents')
    if any(place not in {'home1','home2'} for place in w['housing']):raise ValueError('Households require residential places')
    for place in config['places']:
        b.network.add_node(WorldNode(address(place['id']),place['name'],place=place['id'],kind='address',description=place['name']+'入口'))
        b.network.add_node(WorldNode(business(place['id']),place['name']+'服务',place=place['id'],kind='business',description='本场所业务'))
        edge(b,address(place['id']),business(place['id']))
    for left,right in config['roads']:edge(b,address(left),address(right));edge(b,address(right),address(left))
    path=b.directory/'world'/'common.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(p['common'],encoding='utf-8')
    common=TextFileNode('world/common','世界常识','text',path,description='小镇公开规则，只读。');common.expose=['read'];b.network.add_node(common)
    for spec in config['npcs']:
        actor='world/npc/'+spec['id']
        a={**deepcopy(spec),'gender':spec.get('gender','unspecified'),'coins':spec.get('coins',8),'stamina':5,'inventory':deepcopy(spec.get('inventory',{})),'spouse':None,'children':[],'born_tick':-1,'inbox':[]}
        w['actors'][actor]=a;create_resident(b,actor,a)
    b.network.add_node(PulseNode('world/pulse','世界脉冲',channels=['world.tick'],strength=3,signal_options={'failure_policy':'continue','max_hops':3,'node_timeout_seconds':120}))
    time_node=TextFileNode('world/time','时间','text',b.directory/'world'/'time.md')
    time_node.expose=[];time_node.write('content','第1天-早');b.network.add_node(time_node)
    b.network.nodes['world/pulse'].write_interfaces.append(Interface('world/time',{'threshold':1,'channels':['world.tick']}))
    b.extension_state['npc_world']=w;presence(b,w)
    subscriptions(b,list(w['actors']))
    if hasattr(b,'world_tools'):
        for node in b.network.nodes.values():b.world_tools(b,node)
    return dict(existing=False,clock=clock(0),actors=list(w['actors']))

def look(b,p):
    w,a=require(b,p['actor']);place=a['place']
    neighbors=[y if x==place else x for x,y in w['config']['roads'] if place in (x,y)]
    names={x['id']:x['name'] for x in w['config']['places']}
    due=[dict(id=k,due=clock(v['due_tick']),ready=w['tick']>=v['due_tick']) for k,v in w['pregnancies'].items() if v['carrier']==p['actor'] and not v.get('child')]
    return dict(clock=clock(w['tick']),self={k:deepcopy(a[k]) for k in ('name','gender','role','coins','stamina','inventory','spouse','children')},
                location=dict(id=address(place),name=names[place],service=business(place)),
                neighbors=[dict(id=address(x),name=names[x]) for x in neighbors],
                people=[dict(id=k,name=v['name']) for k,v in w['actors'].items() if k!=p['actor'] and v['place']==place],
                common='world/common',knowledge=profiles.references(b,w,p['actor']),pregnancies=due,last_result=deepcopy(w['results'].get(p['actor'])),
                pending_action=deepcopy(w['intents'].get(p['actor'])),finished=p['actor'] in w['round'].get('outcomes',{}))

def messages(b,p):
    w,a=require(b,p['actor']);items=[m for m in a['inbox'] if not m.get('read')]
    for m in items:m['read']=True
    return dict(items=deepcopy(items))

def subscriptions(b,targets):
    b.network.nodes['world/time'].write_interfaces=[Interface(target,{'threshold':1,'channels':['world.tick']}) for target in targets]

def prepare(b,p):
    if p.get('actor')!='root':raise PermissionError('Only operator may route the world pulse')
    w=state(b)
    if w['round'].get('active'):raise RuntimeError('Previous pulse requires settlement or reconciliation')
    targets=p.get('targets',list(w['actors']))
    if not targets or len(targets)!=len(set(targets)) or any(t not in w['actors'] for t in targets):raise ValueError('Invalid pulse participants')
    profiles.sync(b,w);subscriptions(b,targets)
    return dict(participants=targets)

def open_pulse(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the clock handler may open the world pulse')
    w=state(b)
    if w['round'].get('active'):
        if w['round']['signal_id']==p['signal_id']:return dict(existing=True)
        raise RuntimeError('Another world pulse is active')
    targets=[e.target_node_id for e in b.network.nodes['world/time'].write_interfaces if e.carries(['world.tick'],strength=2)]
    w['round']=dict(active=True,signal_id=p['signal_id'],tick=w['tick'],participants=targets,outcomes={})
    w['intents']={}
    slots=('早','午','下午','傍晚','午夜');text=f"第{w['tick']//5+1}天-{slots[w['tick']%5]}"
    b.network.nodes['world/time'].write('content',text)
    return dict(clock=clock(w['tick']),text=text,participants=targets)

def complete(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the execution handler may record completion')
    w=state(b);r=w['round'];target=p['target']
    if not r.get('active') or r['signal_id']!=p['signal_id'] or target not in r['participants']:raise ValueError('Resident is outside this pulse')
    if target in r['outcomes']:return deepcopy(r['outcomes'][target])
    status=p['status']
    if status not in ('completed','unavailable'):raise ValueError('Invalid resident outcome')
    payload=dict(action=deepcopy(w['intents'].get(target,dict(type='wait'))) if status=='completed' else dict(type='wait'))
    outcome=dict(status=status,payload=payload,reason=p.get('reason','')[:500])
    r['outcomes'][target]=outcome
    return deepcopy(outcome)

def configure_knowledge(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the operator may configure identity knowledge')
    return profiles.configure(b,state(b),p['profiles'])


def refresh_knowledge(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the host may refresh identity knowledge')
    profiles.sync(b,state(b));return dict(refreshed=True)


def observe(b,p):
    if p.get('actor')!='root':raise PermissionError('Operator view is private')
    return deepcopy(state(b))

def install_metadata(b):
    if 'capabilities/node_metadata' in b.components.enabled:
        from datanet.abilities.node_metadata.services import register_provider
        register_provider(b,'npc',lambda actor:profiles.base_attributes(state(b),actor) if state(b) and actor in state(b)['actors'] else {})
        register_provider(b,'place',lambda node_id:place_metadata(b,node_id),public=True)


def register(s):
    s.graph_loaders.append(install_metadata)
    for name,fn,mutation in [('init',initialize,True),('configure_knowledge',configure_knowledge,True),('refresh_knowledge',refresh_knowledge,True),('look',look,False),('messages',messages,True),('prepare_pulse',prepare,True),('open_pulse',open_pulse,True),('complete_pulse_actor',complete,True),('observe',observe,False)]:
        s.rpc('world_'+name,fn,mutation=mutation)
