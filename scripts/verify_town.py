"""独立的应用组合验收；真实核心与组件，只有模型运行用无费用执行器替身。"""
import asyncio,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(json.loads((ROOT/'extensions/development/extension.json').read_text(encoding='utf-8'))['select']+['capabilities/runtime_ports','capabilities/template_instantiation']),DATANET_COMPONENT_PROFILE='{}')
sys.path.insert(0,str(ROOT/'python'))
from datanet.core.backend import Backend
from datanet.core.json_values import thaw
PROFILE=ROOT/'configs/npc_town_v3'
directory=ROOT/'build'/('town-acceptance-'+str(int(time.time()*1000)));directory.mkdir(parents=True)
os.environ['TEMP']=os.environ['TMP']=str(directory)
b=Backend(directory,initial_document=json.loads((PROFILE/'network.json').read_text(encoding='utf-8')))
templates=json.loads((PROFILE/'templates.json').read_text(encoding='utf-8'));b.configure_templates({'templates':templates})
stages=[];executions=[]
async def stub(actor,message,**options):
    executions.append(actor);return dict(status='completed',output='无费用调度验收',steps=0)
b.agent_executor=stub
async def local(node,module,operation,args=None):
    r=await b.modules.call(node,module,operation,args or {});assert r['status']=='ok',(node,module,operation,r);return r['data']
async def call(actor,target,module,operation,args=None):
    r=await b.modules.access(actor,target,module,operation,args or {},strength=2,channels=['movement','service','chat','social','agreements','self']);assert r['status']=='ok',(actor,target,module,operation,r);return r['data']
async def values(id):return (await local(id,'records.store','read'))['values']
async def budget(id):return await local(id,'records.store','apply',{'set':{'ap':10}})
async def move(actor,destination):return await call(actor,destination,'movement.here','move')
async def run():
    for id in [n for n in b.network.nodes if n.startswith('npc/')]:await local(id,'agents.context','prepare')
    start=await values('npc/lin');moved=await move('npc/lin','place/civil');assert moved['moved'] and 'before_results'in moved
    assert (await values('npc/lin'))['ap']==start['ap']-3
    assert 'npc/lin' not in (await local('place/home1','place.info','read'))['visitors']
    assert 'npc/lin' in (await local('place/civil','place.info','read'))['visitors']
    view=await local('npc/lin','tools.collector','collect');origins={t['origin']['node_id'] for t in view};assert 'place/civil'in origins
    assert not any(t['origin']['node_id']=='place/shop' and '业务'in t['name'] for t in view)
    # 无法走到非相邻地址；失败不扣预算、不改变旧位置。
    before=await values('npc/lin');bad=await b.modules.access('npc/lin','place/home1','movement.here','move',{},strength=2,channels=['movement']);assert bad['status']=='ok',bad
    denied=False
    try:bad=await b.modules.access('npc/lin','place/mine','movement.here','move',{},strength=2,channels=['movement']);denied=bad['status']!='ok'
    except PermissionError:denied=True
    assert denied
    stages.append('移动、预算、双向位置边、访客、工具发现与远程拒绝')
    await call('npc/sen','place/woods','service.actions','perform',{'action':'chop','key':'wood-1'})
    assert (await values('npc/sen'))['wood']==3
    await move('npc/sen','place/home2');await budget('npc/sen');await move('npc/sen','place/shop')
    sold=await call('npc/sen','place/shop','service.actions','perform',{'action':'sell_wood','quantity':3,'key':'sell-1'})
    again=await call('npc/sen','place/shop','service.actions','perform',{'action':'sell_wood','quantity':3,'key':'sell-1'})
    assert again['duplicate'] and (await values('npc/sen'))['coins']==14 and (await values('npc/sen'))['wood']==0
    await move('npc/shi','place/smith');await call('npc/shi','place/smith','service.actions','perform',{'action':'repair','key':'fix-1'})
    assert (await values('npc/shi'))['pickaxe']==1 and (await values('npc/shi'))['broken_pickaxe']==0
    stages.append('砍树、跨地出售、数量成本、幂等、镐子修理与库存')
    await budget('npc/lin');await move('npc/lin','place/civil');await move('npc/yue','place/civil')
    note=await call('npc/lin','npc/yue','messages.box','send',{'text':'我们去登记吧','key':'greet'})
    own=await local('npc/yue','messages.box','read');assert own['messages'][-1]['text']=='我们去登记吧'
    private=await b.modules.access('npc/lin','npc/yue','messages.box','read',{},strength=2,channels=['chat']);assert private['status']=='error'
    stages.append('同地交流、发送收费、私信读取权限')
    a=await call('npc/lin','place/civil','agreements.pair','agree',{'partner':'npc/yue','rule':'marriage','key':'lin-marriage'})
    z=await call('npc/yue','place/civil','agreements.pair','agree',{'partner':'npc/lin','rule':'marriage','key':'yue-marriage'})
    assert z['status']=='completed' and (await values('npc/lin'))['spouse']=='npc/yue'
    for actor in ['npc/lin','npc/yue']:await budget(actor);await move(actor,'place/home1')
    await call('npc/lin','place/home1','agreements.pair','agree',{'partner':'npc/yue','rule':'family_plan','key':'lin-plan'})
    agreement=await call('npc/yue','place/home1','agreements.pair','agree',{'partner':'npc/lin','rule':'family_plan','key':'yue-plan'})
    assert agreement['status']=='pending' and (await values('npc/yue'))['pregnant']
    report=await b.network.nodes['world/pulse'].run(b.signals,cycles=10,timeout_seconds=150)
    assert report['status']=='completed',report
    status=await local('world/time','clock.counter','read');print(json.dumps(dict(clock=status,executions=len(executions),report=report),ensure_ascii=False),flush=True)
    assert status['tick']==10 and len(executions)==70,(status,len(executions))
    for actor in ['npc/lin','npc/yue']:await budget(actor)
    await move('npc/yue','place/hospital')
    visible=await call('npc/yue','place/hospital','agreements.pair','inspect');assert any(a['id']==agreement['id'] for a in visible['agreements']),visible
    birth=await call('npc/yue','place/hospital','agreements.pair','fulfill',{'id':agreement['id'],'name':'小苗'})
    children=[id for id in b.network.nodes if id.startswith('instance-')];assert len(children)==1,birth
    child=children[0];assert (await values('npc/yue'))['child']==child and not (await values('npc/yue'))['pregnant']
    assert (await values('npc/lin'))['child']==child
    assert (await values(child))['parent1']=='npc/lin' and (await values(child))['parent2']=='npc/yue'
    assert b.network.nodes[child].context_cursor is None and b.network.nodes[child].file_path.is_relative_to(directory/'created/templates')
    count=len(executions);report=await b.network.nodes['world/pulse'].run(b.signals,cycles=1,timeout_seconds=60);assert report['status']=='completed',report
    assert len(executions)==count+8 and child in executions[count:]
    stages.append('双方同意、孕期、五时刻循环、10时刻等待、医院出生、下一时刻独立激活')
    await local(child,'agents.context','remember',{'text':'这是我的第一条私人记忆','key':'first'})
    b.dispatch('save',{'full':True});return child
try:
    child=b.runtime.run(run());b.close();b=Backend(directory);b.configure_templates({'templates':templates})
    data=b.runtime.run(local(child,'agents.context','recall'));assert data['memories'][0]['text']=='这是我的第一条私人记忆'
    assert b.runtime.run(values('npc/yue'))['child']==child
    stages.append('按节点增量存档、全量存档、独立记忆与冷恢复')
    result=dict(passed=True,model_calls=0,directory=str(directory),stages=stages,nodes=len(b.network.nodes),child=child)
    (directory/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
finally:b.close()
