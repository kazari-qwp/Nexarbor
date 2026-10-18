"""只把场景数据装配为当前协议配置；成品运行不依赖本脚本。"""
from copy import deepcopy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'configs/npc_town_v3'
old=json.loads((ROOT/'configs/npc_town/network.json').read_text(encoding='utf-8'))
original={n['node_id']:n for n in old['network']['nodes']}
LOCAL=['movement','tools','records','info','service','chat','social','agreements']
MODEL=['tools','movement','service','chat','social','agreements','self']
CHANNELS=['movement','records','info','tools']
nodes={};files={}
def save(file,data):
    file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def node(id,name,kind='node'):
    value=dict(type=kind,node_id=id,name=name,description='',management_parent_id=None if id=='root' else 'root',divergence=-1,data_kind={'agent':'agent','text_file':'text','pulse':'pulse'}.get(kind),parameters={},connections={'interfaces':[]},agent=None,modules={},offered_tools=[],toolboxes=[],expose=[],execution=None,context_cursor=None,inputs=None)
    if kind in ('agent','text_file'):
        file=('memory/' if kind=='agent' else 'world/')+id.replace('/','-')+'.md';value['parameters']['file_path']=file;files[file]=''
    nodes[id]=value;return value
def mount(n,name,config=None,strength=0,channels=()):
    n['modules'][name]={'config':config or {},'state':{},'access':{'strength':strength,'channels':list(channels)}}
def edge(a,b,channels,relation='',reciprocal=False):
    meta=dict(channels=list(channels),threshold=1,multiplier=1,attributes={'relation':relation} if relation else {})
    nodes[a]['connections']['interfaces'].append(dict(target_node_id=b,metadata=meta))
    if reciprocal:edge(b,a,channels,relation)
def records(n,initial,references=()):
    numeric={k:0 for k,v in initial.items() if type(v) in (int,float)}
    mount(n,'records.store',dict(initial=initial,minimum=numeric,references=[dict(key=k,node_id=v) for k,v in references]),0,['records'])
def events(place,trigger):
    result=[]
    for e in original[place]['modules']['chance.events']['config']['events']:
        if trigger not in e['triggers']:continue
        result.append(dict(id=e['id'],text=e['message'],probability=e['probability'],limit=e.get('max_hits'),rewards=e.get('effects',{}).get('items',{}),triggers=e['triggers']))
    return result

node('root','小镇观察者')
pulse=node('world/pulse','世界脉冲','pulse');pulse['parameters']=dict(channels=['tick'],strength=4,content='新时刻开始',signal_options=dict(timeout_seconds=540,node_timeout_seconds=420,max_hops=8,max_deliveries=128))
clock=node('world/time','时间','text_file');mount(clock,'clock.counter',dict(signal_channels=['tick'],labels=['早上','中午','下午','傍晚','午夜'],write_text=True),0,['tick'])
saver=node('world/save','五时刻存档');mount(saver,'clock.counter',dict(signal_channels=['tick'],checkpoint_every=5),0,['tick','runtime.checkpoint']);saver['offered_tools']=[dict(ref='runtime:checkpoint',channels=['runtime.checkpoint'])]
edge('world/pulse','world/time',['tick']);edge('world/save','world/pulse',['tick'])

for id,o in original.items():
    if not id.startswith('place/'):continue
    p=node(id,o['name']);p['description']=o.get('description','') or o['name']+'，使用本地服务，沿相邻道路移动。'
    visitors=[i for i,n in original.items() if i.startswith('npc/') and n['modules']['entity.profile']['config']['profile']['place']==id]
    mount(p,'place.info',dict(description=p['description'],visitors=visitors),0,['movement','info'])
    hooks=[dict(target='requester',module='records.store',operation='apply',arguments={'deltas':{'ap':-3}})]
    arrivals=[dict(id=e['id'],text=e['message'],probability=e['probability'],limit=e.get('max_hits'),rewards=e.get('effects',{}).get('items',{}),triggers=e['triggers']) for e in o['modules']['chance.events']['config']['events']]
    if arrivals:
        mount(p,'events.chance',dict(events=arrivals),2,['events','records','movement'])
        hooks.append(dict(target='destination',module='events.chance',operation='sample',arguments={'trigger':'arrive'}))
    mount(p,'movement.here',dict(location_channels=LOCAL,before_hooks=hooks),2,[*LOCAL,'events'])
    edge(id,'world/time',['info'])

roads=[('home1','civil'),('home1','hospital'),('home1','tavern'),('home2','tavern'),('home2','shop'),('home2','woods'),('tavern','shop'),('tavern','civil'),('shop','smith'),('smith','mine'),('shop','hospital'),('woods','mine')]
for a,b in roads:edge('place/'+a,'place/'+b,CHANNELS,'road',True)

knowledge=[]
catalog=ROOT/'extensions/npc_world/nodes/resident_knowledge'
for entry in json.loads((catalog/'profiles.json').read_text(encoding='utf-8')):
    mapping={'gender':'gender','role':'role','life_stage':'age_group','can_gestate':'can_gestate','pregnant':'pregnant','is_parent':'is_parent'}
    when={mapping[k.rsplit('/',1)[-1]]:v for k,v in entry['when'].items()}
    current={
        'profession/miner':'你是矿工。完好镐子是pickaxe；在矿坑每单位挖矿消耗6行动点，获得3矿石。坏镐可在铁匠铺花2金币及店内1铁料修理，矿石可去商店每份售3金币。以工具返回为准。',
        'profession/woodcutter':'你是伐木工。持axe在树林每单位砍树消耗6行动点，获得3木材。木材可到商店每份售2金币。',
        'profession/smith':'你是铁匠。当地修理服务有独立库存，来访者花2金币和店内1铁料修理坏镐。你可将随身铁料补入店内库存，不必替来访者确认。',
        'profession/wanderer':'你暂时没有登记住处，不能使用居民楼休息服务。可以交谈、寻找收入、请求同地居民主动赠送金币或工具。',
        'life/family':'两位成年人同一时刻在民政局各自调用marriage协议同意。登记后在共同住处各自同意family_plan；必须至少一人有can_gestate资格。10时刻后具备资格的待产者到医院，查看协议并fulfill。不能代替对方同意。',
        'life/gestation':'你具备孕育资格；当前是否怀孕以自己的记录为准。',
        'life/pregnant':'家庭协议登记后等待10时刻，到医院查看协议并兑现。重试同一协议保持同一个孩子名字，官方模板按同一个请求键创建一次。',
        'life/parent':'孩子拥有独立记忆与身份，下一时刻自己活动。你只能通过当地交流与其交谈。'
    }
    knowledge.append(dict(id=entry['id'],when=when,text=current.get(entry['id'],(catalog/entry['file']).read_text(encoding='utf-8'))))
common=old['files']['world/common.md']+'\n记录中的coins是金币；gold是黄金物品，不要混淆。remember/recall属于你自己。需要聊天先看自己的便条箱；到其他地点后工具与现场会自动刷新。每次最多主动执行三件有意义的事，然后保存重要记忆并结束。业务返回失败意味着未完成，不可编造成功。遇到并发锁冲突可以稍后重试一次，不要无限重试。\n'
map_text=old['files']['world/map.md']
role_map={'sen':'woodcutter','shi':'miner','li':'miner','tie':'smith','lu':'wanderer','lin':'resident','yue':'resident'}
def agent(id,name,profile,persona,opening,location,refs,adult=True):
    n=node(id,name,'agent');records(n,profile,refs)
    mount(n,'place.info',dict(location=location),0,['movement','info'])
    mount(n,'agents.context',dict(persona=persona,common=common,map=map_text,opening=opening,clock='world/time',knowledge=knowledge),2,['self','records','movement','info'])
    mount(n,'messages.box',dict(read_policy='self',send_cost=1,max_messages=200),2,['chat','records'])
    if adult:mount(n,'records.transfer',dict(cost=1,same_location=True),2,['self','social','movement','records'])
    mount(n,'tools.collector',{},2,MODEL)
    mount(n,'agents.activity',dict(enabled=True,budget=10,signal_channels=['tick'],prompt='新时刻开始。安排你自己的行动，先看未读便条，按目标做不超过三件事，记录重要经历，然后自然结束。'),0,['tick','records','self','runtime.agent'])
    n['offered_tools']=[dict(ref='runtime:agent_run',channels=['runtime.agent'])]
    n['execution']=dict(executor='harness',strength=2,channels=MODEL,max_steps=18,timeout_seconds=360,prepare=[dict(module='agents.context',operation='prepare',arguments={})])
    edge(id,location,LOCAL,'location',True);edge(id,'world/time',['info']);edge(id,'world/save',['tick']);edge('world/time',id,['tick'])
    return n
for id,o in original.items():
    if not id.startswith('npc/'):continue
    e=o['modules']['entity.profile']['config'];p=e['profile'];c=o['modules']['resident.context']['config'];short=id.split('/')[1]
    values=dict(name=p['name'],gender=p['gender'],profession=p['occupation'],role=role_map[short],age=p['age'],age_group='adult',adult=True,can_gestate=p['gender']=='female',pregnant=False,is_parent=False,coins=e['coins'],ap=10,**e['items'])
    references=[('home',p.get('home')),('partner',p.get('partner')),('spouse',None)]
    agent(id,p['name'],values,old['files'][c['persona_file']],c['opening_line'],p['place'],references)

# 同一通用服务按配置呈现采集、交易、修理、休息；库存只在提供服务的地点保存一份。
for id,o in original.items():
    if 'local.action_rules' not in o.get('modules',{}):continue
    old_config=o['modules']['local.action_rules']['config'];address=old_config['address'];p=nodes[address]
    initial=original[address]['modules']['entity.profile']['config'];records(p,dict(coins=initial['coins'],**initial['items']))
    actions=[]
    for key,r in old_config['rules'].items():
        actor=r.get('actor',{});local=r.get('place',{})
        deltas={**actor.get('items',{}),**({'coins':actor['coins']} if 'coins'in actor else {})}
        local_deltas={**local.get('items',{}),**({'coins':local['coins']} if 'coins'in local else {})}
        a=dict(id=key,title=r['description'].split('：')[0],description=r['description'],cost=r.get('cost',1),per_unit_cost=r.get('cost_per_unit',False),actor_deltas=deltas,local_deltas=local_deltas,actor_set=actor.get('fields',{}),require_items=r.get('requires_items',{}))
        requirement=r.get('requires_profile',{})
        if key!='rest':a['require_values']={'adult':True}
        if requirement.get('home'):a['required_home']=requirement['home']
        actions.append(a)
    hooks=[dict(target='local',module='events.chance',operation='sample',arguments={'trigger':key},actions=[key]) for key in old_config['rules'] if events(address,key)]
    mount(p,'service.actions',dict(address=address,actions=actions,events=[],after_hooks=hooks),2,['service','records','movement','events'])

marriage=dict(id='marriage',title='双方同意登记结婚',cost=1,require_values={'adult':True},pair_field='spouse',forbid_existing_pair=True,set_values={'married':True})
mount(nodes['place/civil'],'agreements.pair',dict(clock='world/time',address='place/civil',rules=[marriage]),2,['agreements','records','movement','info'])
for home in ['home1','home2']:
    id='place/'+home
    plan=dict(id='family_plan',title='夫妻共同家庭计划',cost=1,require_values={'adult':True,'pregnant':False},eligible_field='can_gestate',equal_fields=['home'],pair_field='spouse',require_pair=True,set_values={'is_parent':True},delay_ticks=10,template='family-'+home,fulfill_cost=1,fulfill_require_values={'can_gestate':True},participant_effects=[dict(when={'can_gestate':True},on_start={'pregnant':True},on_finish={'pregnant':False})])
    mount(nodes[id],'agreements.pair',dict(clock='world/time',address=id,delivery_address='place/hospital',rules=[plan]),3,['agreements','records','movement','info','runtime.template'])
    edge(id,'place/hospital',['runtime.template'])
    for npc,o in original.items():
        if npc.startswith('npc/') and o['modules']['entity.profile']['config']['profile'].get('home')==id:
            edge(id,npc,['records','info'],'household')
mount(nodes['place/hospital'],'agreements.pair',dict(clock='world/time',sources=['place/home1','place/home2'],rules=[]),2,['agreements','info'])
nodes['place/hospital']['offered_tools']=[dict(ref='templates:instantiate',channels=['runtime.template'])]
for home in ['home1','home2']:edge('place/hospital','place/'+home,['agreements'])

# 出生模板也是声明配置。新角色有自己的状态、记忆文件和原生会话，不继承父母上下文。
base_ids=set(nodes);base_files=set(files)
child=agent('child','新成员',dict(name='新成员',gender='unspecified',profession='孩子',role='child',age=0,age_group='child',adult=False,can_gestate=False,pregnant=False,is_parent=False,coins=0,ap=10),old['files'].get('personas/child.md','你是能说话的小孩，想认识家人和小镇。'),'你刚刚出生，能说话，想认识家人和这个小镇。','place/hospital',[('home','place/home1'),('parent1','npc/lin'),('parent2','npc/yue'),('spouse',None)],False)
child_files={f:files[f] for f in set(files)-base_files}
# agent()只为生成模板临时添加锚点；从初始网络移除这些出边。
for id in base_ids:nodes[id]['connections']['interfaces']=[e for e in nodes[id]['connections']['interfaces'] if e['target_node_id']!='child']
nodes.pop('child');files={k:v for k,v in files.items() if k in base_files}
templates=[]
for home in ['home1','home2']:
    c=deepcopy(child)
    bindings=[dict(path='/network/nodes/0/name',input='name'),dict(path='/network/nodes/0/modules/records.store/config/initial/name',input='name')]
    for i,key in enumerate(['home','parent1','parent2']):bindings.append(dict(path=f'/network/nodes/0/modules/records.store/config/references/{i}/node_id',input={'home':'home','parent1':'/parents/0','parent2':'/parents/1'}[key]))
    templates.append(dict(id='family-'+home,callers=['place/'+home],document=dict(network=dict(version=8,nodes=[c],signals={},delegations=[]),files=child_files),arguments_schema=dict(type='object',properties=dict(name=dict(type='string',minLength=1,maxLength=50),parents=dict(type='array',items=dict(type='string'),minItems=2,maxItems=2),home=dict(type='string',enum=['place/'+home])),required=['name','parents','home'],additionalProperties=False),bindings=bindings,attachments=[dict(source='world/time',target='child',metadata=dict(channels=['tick'],threshold=1,multiplier=1,attributes={})),dict(source='place/hospital',target='child',metadata=dict(channels=LOCAL,threshold=1,multiplier=1,attributes={'relation':'location'}))]))

save(OUT/'network.json',dict(network=dict(version=8,nodes=list(nodes.values()),signals={},delegations=[]),files=files))
save(OUT/'templates.json',templates)
save(OUT/'profile.json',dict(name='NPC小镇 · 当前局部组件协议',network='network.json',templates='templates.json',components=['capabilities/runtime_ports','capabilities/template_instantiation'],runtime_directory='../../build/npc-town-v3'))
save(OUT/'scenario.json',dict(places=[dict(id=id,name=n['name']) for id,n in nodes.items() if id.startswith('place/')],roles=[dict(id=id,name=n['name'],initial=n['modules']['records.store']['config']) for id,n in nodes.items() if id.startswith('npc/')],roads=roads,common=common,map=map_text,provenance='仅从旧配置提取场景数据，不加载旧模块或协议'))
print('配置已生成：',len(nodes),'个节点，',len(templates),'个固定声明模板')
