"""用宿主独立重测模型给出的借还配置；不读取它自己的测试断言。"""
import asyncio,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
os.environ.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(json.loads((ROOT/'extensions/development/extension.json').read_text(encoding='utf-8'))['select']+['capabilities/runtime_ports','capabilities/template_instantiation']),DATANET_COMPONENT_PROFILE='{}')
from datanet.core.backend import Backend
source=ROOT/'build/shop-wish-lab/studio/work/module-e118dbbae6/presets.json';preset=json.loads(source.read_text(encoding='utf-8'))['presets'][0]
directory=ROOT/'build'/('shop-wish-verification-'+str(int(time.time()*1000)));directory.mkdir()
b=Backend(directory,initial_document=json.loads((ROOT/'configs/npc_town_v3/network.json').read_text(encoding='utf-8')))
async def local(node,module,operation,args=None):
    r=await b.modules.call(node,module,operation,args or {});assert r['status']=='ok',r;return r['data']
async def run():
    shop=b.network.nodes['place/shop'];before={a['id'] for a in shop.modules['service.actions']['config']['actions']};access=shop.modules['service.actions']['access']
    b.modules.unmount('place/shop','service.actions');b.modules.mount('place/shop','service.actions',config=preset['config'],access=access)
    assert before<={a['id'] for a in preset['config']['actions']}
    async def call(target,module,op,args=None):return await b.modules.access('npc/sen',target,module,op,args or {},strength=2,channels=['movement','service'])
    for place in ['place/home2','place/shop']:assert (await call(place,'movement.here','move'))['status']=='ok'
    await local('npc/sen','records.store','apply',{'set':{'ap':10}})
    async def values(node):return (await local(node,'records.store','read'))['values']
    actor=await values('npc/sen');stock=await values('place/shop')
    positive=next(a for a in preset['config']['actions'] if a.get('actor_deltas',{}).get('debt')==1);negative=next(a for a in preset['config']['actions'] if a.get('actor_deltas',{}).get('debt')==-1)
    async def action(rule,quantity,key):return await call('place/shop','service.actions','perform',{'action':rule,'quantity':quantity,'key':key})
    first=await action(positive['id'],5,'loan');assert first['status']=='ok',first
    assert (await values('npc/sen'))['debt']==5 and (await values('npc/sen'))['ap']==9
    assert (await values('place/shop'))['coins']==stock['coins']-5
    rejected=await action(positive['id'],4,'over');assert rejected['status']=='error',rejected
    assert (await values('npc/sen'))['debt']==5 and (await values('npc/sen'))['ap']==9
    assert (await action(negative['id'],2,'repay'))['status']=='ok'
    assert (await values('npc/sen'))['debt']==3 and (await values('npc/sen'))['coins']==actor['coins']+3
    assert (await values('place/shop'))['coins']==stock['coins']-3
    rejected=await action(negative['id'],4,'too-much');assert rejected['status']=='error',rejected
    assert (await values('npc/sen'))['debt']==3 and (await values('npc/sen'))['ap']==8
    assert (await action('buy_axe',1,'ordinary-trade'))['status']=='ok'
    assert (await values('npc/sen'))['axe']==2
try:
    b.runtime.run(run());result=dict(passed=True,new_implementations=0,used_component=preset['module'],preserved_trade=True,loan_and_repay=True,credit_cap=8,over_repayment_rejected=True,model_calls_in_verification=0,directory=str(directory));(directory/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
finally:b.close()
