"""World state and graph are committed together by the existing checkpoint service."""
from copy import deepcopy
from datanet.core.interface import Interface
from datanet.core.text_node import TextFileNode
from datanet.world.nodes import WorldNode,Resident
from datanet.rounds import barrier

SLOTS=('早上','中午','下午','傍晚','午夜')
def address(place):return 'world/place/'+place
def business(place):return 'world/service/'+place
def clock(tick):return dict(tick=tick,day=tick//5+1,slot=SLOTS[tick%5])

def state(b):return b.extension_state.get('npc_world')

def require(b,actor):
    w=state(b)
    if not w or actor not in w['actors']:raise PermissionError('Not a world resident')
    return w,w['actors'][actor]

def edge(b,source,target,directions=('read','write')):
    for direction in directions:
        links=getattr(b.network.nodes[source],direction+'_interfaces')
        if not any(x.target_node_id==target for x in links):links.append(Interface(target,threshold=1))

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

def create_resident(b,actor,a):
    if actor not in b.network.nodes:
        n=Resident(actor,a['name'],file_path=b.directory/'world'/'memories'/(actor.rsplit('/',1)[-1]+'.md'),
                   creation_options=dict(identity=actor,world='small_town'),description=a['name'])
        n.write_memory('# '+a['name']+'的私人记忆\n'+a.get('background','')+'\n')
        b.network.add_node(n)
    if hasattr(b,'world_tools'):b.world_tools(b,b.network.nodes[actor])

def initialize(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the world operator initializes the map')
    if state(b):return dict(existing=True,clock=clock(state(b)['tick']))
    config=deepcopy(p['config'])
    w=dict(tick=0,config=config,actors={},barrier={},intents={},results={},events=[],pregnancies={},families=[],
           shop=deepcopy(config['shop']),smith_stock=deepcopy(config['smith_stock']),last_settled=None)
    for place in config['places']:
        b.network.add_node(WorldNode(address(place['id']),place['name'],place=place['id'],kind='address',description=place['name']+'入口'))
        b.network.add_node(WorldNode(business(place['id']),place['name']+'服务',place=place['id'],kind='business',description='本场所业务'))
        edge(b,address(place['id']),business(place['id']))
    for left,right in config['roads']:edge(b,address(left),address(right));edge(b,address(right),address(left))
    path=b.directory/'world'/'common.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(p['common'],encoding='utf-8')
    common=TextFileNode('world/common','世界常识','text',path,description='小镇公开规则，只读。');common.expose=['read'];b.network.add_node(common)
    for spec in config['npcs']:
        actor='world/npc/'+spec['id']
        a={**deepcopy(spec),'coins':spec.get('coins',8),'stamina':5,'inventory':deepcopy(spec.get('inventory',{})),'spouse':None,'children':[],'born_tick':-1,'inbox':[]}
        w['actors'][actor]=a;create_resident(b,actor,a)
    b.extension_state['npc_world']=w;presence(b,w)
    if hasattr(b,'world_tools'):
        for node in b.network.nodes.values():b.world_tools(b,node)
    return dict(existing=False,clock=clock(0),actors=list(w['actors']))

def look(b,p):
    w,a=require(b,p['actor']);place=a['place']
    neighbors=[y if x==place else x for x,y in w['config']['roads'] if place in (x,y)]
    names={x['id']:x['name'] for x in w['config']['places']}
    due=[dict(id=k,due=clock(v['due_tick']),ready=w['tick']>=v['due_tick']) for k,v in w['pregnancies'].items() if v['carrier']==p['actor'] and not v.get('child')]
    return dict(clock=clock(w['tick']),self={k:deepcopy(a[k]) for k in ('name','role','coins','stamina','inventory','spouse','children')},
                location=dict(id=address(place),name=names[place],service=business(place)),
                neighbors=[dict(id=address(x),name=names[x]) for x in neighbors],
                people=[dict(id=k,name=v['name']) for k,v in w['actors'].items() if k!=p['actor'] and v['place']==place],
                common='world/common',pregnancies=due,last_result=deepcopy(w['results'].get(p['actor'])),
                pending_action=deepcopy(w['intents'].get(p['actor'])),submitted=p['actor'] in w['barrier'].get('submitted',{}))

def messages(b,p):
    w,a=require(b,p['actor']);items=[m for m in a['inbox'] if not m.get('read')]
    for m in items:m['read']=True
    return dict(items=deepcopy(items))

def begin(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the world operator advances time')
    w=state(b)
    if not w:raise ValueError('World not initialized')
    if not w['barrier'].get('active'):w['intents']={}
    return barrier.begin(w['barrier'],str(w['tick']),list(w['actors']),p.get('timeout_seconds',180))

def submit(b,p):
    w,a=require(b,p['actor']);payload=dict(action=deepcopy(w['intents'].get(p['actor'],dict(type='wait'))),summary=p.get('summary','')[:300])
    return barrier.submit(w['barrier'],p['actor'],payload)

def abandon(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the operator may mark unavailable')
    w=state(b);barrier.abandon(w['barrier'],p['target'],p.get('reason','unavailable'))
    return dict(pending=barrier.pending(w['barrier']))

def observe(b,p):
    if p.get('actor')!='root':raise PermissionError('Operator view is private')
    return deepcopy(state(b))

def register(s):
    for name,fn,mutation in [('init',initialize,True),('look',look,False),('messages',messages,True),('begin',begin,True),('submit',submit,True),('abandon',abandon,True),('observe',observe,False)]:
        s.rpc('world_'+name,fn,mutation=mutation)
