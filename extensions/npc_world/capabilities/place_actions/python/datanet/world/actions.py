"""Local public tools, delayed effects and deterministic, atomic phase settlement."""
from copy import deepcopy
from pathlib import Path
import json
from datanet.core.access_budget import active_agent,current_access
from datanet.world.nodes import WorldNode,Resident
from datanet.world.state import state,require,address,business,clock,presence,create_resident
from datanet.rounds import barrier

TOOLS=json.loads((Path(__file__).resolve().parents[3]/'tools.json').read_text(encoding='utf-8'))
ADULT={'marry','plan_family','repair','trade','mine','chop','birth','drink','give'}

def caller(b,target):
    principal=active_agent.get();frame=current_access.get()
    if not principal or not frame or frame['network'] is not b.network or frame['node_id']!=target:
        raise PermissionError('Use the graph tool channel; caller identity is supplied by the host')
    actor=principal[1];require(b,actor)
    return actor

def active(w,actor):
    r=w['barrier']
    if not r.get('active') or actor not in r['participants']:raise ValueError('No active world round')
    if actor in r['submitted']:raise ValueError('This round is already submitted')
    import time
    if time.time()>=r['deadline']:raise TimeoutError('Round deadline exceeded')

def install(b,node,*_):
    if not isinstance(node,(WorldNode,Resident)):return
    def attach(name,read_only=False):
        spec=TOOLS[name]
        node.register_tool(name,lambda _name=name,**args:invoke(b,node,_name,args),**spec,read_only=read_only)
        if name not in node.expose:node.expose.append(name)
    if isinstance(node,Resident):
        attach('talk');attach('give');return
    if node.kind=='address':attach('move_here');return
    w=state(b)
    if not w:return
    services=next(x['services'] for x in w['config']['places'] if x['id']==node.place)
    for name in services:attach(name)
    attach('local_info',True)

def invoke(b,node,name,args):
    actor=caller(b,node.node_id);w,a=require(b,actor)
    if isinstance(node,Resident):
        other=w['actors'][node.node_id]
        if a['place']!=other['place']:raise PermissionError('Not in the same place')
    elif name!='move_here' and node.place!=a['place']:raise PermissionError('Service is outside your current place')
    if name=='local_info':
        info=dict(place=node.place,services=next(x['services'] for x in w['config']['places'] if x['id']==node.place))
        if node.place=='shop':info['items']=deepcopy(w['shop'])
        if node.place=='smithy':info.update(price=2,stock=deepcopy(w['smith_stock']),smith_present=any(x['role']=='smith' and x['place']=='smithy' for x in w['actors'].values()))
        return info
    active(w,actor)
    if a['role']=='child' and name in ADULT:raise PermissionError('Children may move, talk and rest')
    if name=='talk':
        own=[e for e in w['events'] if e.get('tick')==w['tick'] and e.get('actor')==actor and e.get('type')=='talk']
        if len(own)>=3:raise ValueError('At most three conversations per time slot')
        event=dict(id=f"{w['tick']}:{actor}:{len(own)}",type='talk',tick=w['tick'],actor=actor,to=node.node_id,content=args['content'])
        other['inbox'].append(event.copy());other['inbox']=other['inbox'][-100:]
        w['events'].append(event);w['events']=w['events'][-1000:]
        return dict(delivered=True,recipient=node.node_id,notice='对方会在本轮按需读取或下一时刻看到，交谈不自动唤醒新轮次。')
    intent=dict(type=name,**args)
    if name=='move_here':
        roads=w['config']['roads']
        if node.place!=a['place'] and not any(set(r)=={node.place,a['place']} for r in roads):raise PermissionError('Destination is not adjacent')
        intent['destination']=node.place
    elif isinstance(node,Resident):intent['recipient']=node.node_id
    else:intent['place']=node.place
    if name in ('marry','plan_family'):
        if args['partner']==actor or args['partner'] not in w['actors']:raise ValueError('Choose another resident ID')
        if w['actors'][args['partner']]['place']!=a['place']:raise ValueError('Partner must be present')
    w['intents'][actor]=intent
    return dict(queued=deepcopy(intent),notice='这是行动计划；可在提交前更换，提交后统一结算。',**({'expected_due':clock(w['tick']+10)} if name=='plan_family' else {}))

def take(a,item,n):
    if item=='coins':
        if a['coins']<n:raise ValueError('Not enough coins')
        a['coins']-=n;return
    if item in ('axe','pickaxe'):raise ValueError('Tools are unique; cannot transfer as stack items')
    if a['inventory'].get(item,0)<n:raise ValueError('Not enough '+item)
    a['inventory'][item]-=n

def add(a,item,n):
    if item=='coins':a['coins']+=n
    else:a['inventory'][item]=a['inventory'].get(item,0)+n

def apply(w,actor,intent,actions,handled):
    a=w['actors'][actor];kind=intent['type']
    if kind=='wait':return '等待。'
    if a['role']=='child' and kind in ADULT:raise ValueError('Adult activity unavailable to a child')
    if kind=='move_here':return '移动将在本轮业务结算后完成。'
    if 'place' in intent and intent['place']!=a['place']:raise ValueError('Location changed')
    if kind in ('marry','plan_family'):
        partner=intent['partner'];other=w['actors'][partner];op=actions.get(partner,{})
        if other['place']!=a['place'] or op.get('type')!=kind or op.get('partner')!=actor:raise ValueError('双方需在同一场所提交相同申请。')
        if other['role']=='child':raise ValueError('Children cannot register a family')
        if kind=='marry':
            if a['spouse'] or other['spouse']:raise ValueError('Already married')
            a['spouse']=partner;other['spouse']=actor;w['families'].append(sorted([actor,partner]));message='双方已登记结婚。'
        else:
            if a['spouse']!=partner or other['spouse']!=actor:raise ValueError('Only spouses may register a pregnancy')
            if a['children'] or other['children']:raise ValueError('This demo allows one child per family')
            if any(set(v['parents'])=={actor,partner} for v in w['pregnancies'].values()):raise ValueError('Family plan already registered')
            carrier=actor if a.get('can_gestate') else partner if other.get('can_gestate') else None
            if not carrier:raise ValueError('No eligible gestational parent')
            pid='family-'+str(len(w['pregnancies'])+1)
            w['pregnancies'][pid]=dict(parents=sorted([actor,partner]),carrier=carrier,due_tick=w['tick']+10,child=None)
            message='生育计划已登记，预产：'+str(clock(w['tick']+10))
        handled.add(partner);w['results'][partner]=dict(ok=True,message=message,tick=w['tick'])
        return message
    if kind=='rest':a['stamina']=min(5,a['stamina']+3);return '休息后体力恢复。'
    if kind=='drink':take(a,'coins',1);a['stamina']=min(5,a['stamina']+1);return '饮料花费1金币，恢复1体力。'
    if kind in ('mine','chop'):
        tool,resource=('pickaxe','ore') if kind=='mine' else ('axe','wood')
        if a['stamina']<1 or a['inventory'].get(tool,0)<1:raise ValueError('需要体力和耐久大于0的工具。')
        a['stamina']-=1;a['inventory'][tool]-=1;add(a,resource,2);return '获得2份'+resource+'。'
    if kind=='repair':
        item=intent['item']
        if item not in a['inventory']:raise ValueError('You do not own this tool')
        if not any(x['role']=='smith' and x['place']=='smithy' for x in w['actors'].values()):raise ValueError('铁匠不在店内。')
        if min(w['smith_stock'].values())<1:raise ValueError('修理材料不足。')
        take(a,'coins',2);a['inventory'][item]=5
        for k in w['smith_stock']:w['smith_stock'][k]-=1
        smith=next(x for x in w['actors'].values() if x['role']=='smith');smith['coins']+=2
        return '工具已修复至5耐久。'
    if kind=='trade':
        item,n=intent['item'],intent['quantity'];stock=w['shop'][item];price=stock['price']
        if item in ('axe','pickaxe'):
            if intent['side']!='buy' or n!=1 or item in a['inventory']:raise ValueError('工具只能单件购买一次，坏工具可修理。')
        if intent['side']=='buy':
            if stock['stock']<n:raise ValueError('商店库存不足。')
            take(a,'coins',price*n);stock['stock']-=n
            if item in ('axe','pickaxe'):a['inventory'][item]=5
            else:add(a,item,n)
        else:take(a,item,n);add(a,'coins',max(1,price-1)*n);stock['stock']+=n
        return '交易已结算。'
    if kind=='give':
        other=w['actors'][intent['recipient']]
        if other['place']!=a['place']:raise ValueError('Recipient is not present')
        take(a,intent['item'],intent['quantity']);add(other,intent['item'],intent['quantity']);return '赠送已交付。'
    if kind=='birth':
        pair=next(((k,v) for k,v in w['pregnancies'].items() if v['carrier']==actor and not v.get('child')),None)
        if not pair:raise ValueError('No pending pregnancy')
        pid,pregnancy=pair
        if w['tick']<pregnancy['due_tick']:raise ValueError('尚未到预产日。')
        child='world/npc/child-'+pid
        name='小芽'+str(len(w['pregnancies']))
        parents=pregnancy['parents'];background='你的父母是'+ '、'.join(w['actors'][x]['name'] for x in parents)+'。你刚在医院出生，已经能说话。'
        w['actors'][child]=dict(id=child.rsplit('/',1)[-1],name=name,place='hospital',role='child',goal='认识家人和小镇，在安全场所休息、交流。',background=background,parents=parents,coins=0,stamina=5,inventory={},spouse=None,children=[],born_tick=w['tick'],inbox=[])
        pregnancy['child']=child
        for parent in parents:w['actors'][parent]['children'].append(child)
        return '孩子已出生：'+child+'；下一时刻加入。'
    raise ValueError('Unsupported action')

def settle(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the operator settles rounds')
    original=state(b)
    if not original['barrier'].get('active'):
        if original['last_settled'] is not None:return deepcopy(original['last_settled'])
        raise ValueError('No round to settle')
    # Expiration is itself a durable change; effects remain isolated until commit.
    barrier.expire(original['barrier'])
    if barrier.pending(original['barrier']):raise ValueError('Participants are still pending')
    w=deepcopy(original);entries=barrier.finish(w['barrier'])
    actions={actor:(v['payload']['action'] if v['status']=='submitted' else dict(type='wait')) for actor,v in entries.items()}
    handled=set();members=list(entries);offset=w['tick']%len(members);members=members[offset:]+members[:offset]
    for actor in members:
        if actor in handled:continue
        trial=deepcopy(w);trial_handled=set(handled)
        try:
            message=apply(trial,actor,actions[actor],actions,trial_handled)
            trial['results'][actor]=dict(ok=True,message=message,tick=w['tick']);w,handled=trial,trial_handled
        except (ValueError,KeyError) as error:w['results'][actor]=dict(ok=False,message=str(error),tick=w['tick'])
    # Everyone performs business at the start-of-slot location, then moves together.
    for actor,intent in actions.items():
        if intent['type']=='move_here':w['actors'][actor]['place']=intent['destination'];w['results'][actor]['message']='已到达 '+intent['destination']
    newborns=[k for k in w['actors'] if k not in original['actors']]
    result=dict(settled_tick=w['tick'],next_clock=clock(w['tick']+1),results=deepcopy(w['results']),newborns=newborns,
                unavailable=[k for k,v in entries.items() if v['status']=='unavailable'])
    w['events'].append(dict(type='settlement',tick=w['tick'],newborns=newborns));w['events']=w['events'][-1000:]
    w['tick']+=1;w['last_settled']=deepcopy(result)
    # New files/nodes are built before publishing; deterministic IDs make retries safe.
    for actor in newborns:create_resident(b,actor,w['actors'][actor])
    b.extension_state['npc_world']=w;presence(b,w)
    for actor in newborns:install(b,b.network.nodes[actor])
    return result

def register(s):
    s.initializers.append(lambda b:setattr(b,'world_tools',install))
    s.node_restorers.append(install)
    s.rpc('world_settle',settle,mutation=True)
