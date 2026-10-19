"""真实小镇组件的并发验收；仅模型用确定性替身，零付费调用。"""
import asyncio,json,os,sys,time
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8='1',DATANET_DEFER_VECTORS='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION=json.dumps(json.loads((ROOT/'extensions/development/extension.json').read_text(encoding='utf-8'))['select']+['capabilities/runtime_ports','capabilities/template_instantiation']),DATANET_COMPONENT_PROFILE='{}')
sys.path.insert(0,str(ROOT/'python'))
from datanet.core.backend import Backend
from datanet.core.json_values import thaw
folder=ROOT/'build'/('town-parallel-'+str(int(time.time()*1000)));folder.mkdir(parents=True)
b=Backend(folder,initial_document=json.loads((ROOT/'configs/npc_town_v3/network.json').read_text(encoding='utf-8')))
actors={n for n in b.network.nodes if n.startswith('npc/')}
counts=Counter();active=Counter();entered=set();events=[];peak=0
async def local(actor,module,operation,args=None):
 r=await b.modules.call(actor,module,operation,args or {});assert r['status']=='ok',r;return r['data']
async def send(actor,target,key):
 r=await b.modules.access(actor,target,'messages.box','send',{'text':key,'key':key},strength=2,channels=['chat']);assert r['status']=='ok',r;return r['data']
async def wait_completed(actor):
 for _ in range(2000):
  entries=thaw(b.modules.instances[(actor,'agents.activity')].state).get('activities',[])
  if entries and entries[-1]['status']=='completed':return
  await asyncio.sleep(.001)
 raise AssertionError('等待角色完成超时 '+actor)
async def run():
 global peak
 all_started=asyncio.Event();reply_received=asyncio.Event()
 async def model(actor,message,**options):
  global peak
  counts[actor]+=1;active[actor]+=1;assert active[actor]==1,('同角色并发模型',actor)
  entered.add(actor);events.append([actor,counts[actor],'start']);peak=max(peak,sum(active.values()))
  if entered==actors:all_started.set()
  try:
   await asyncio.wait_for(all_started.wait(),2)
   if actor=='npc/lin' and counts[actor]==1:
    await wait_completed('npc/yue')
    await send(actor,'npc/yue','并行问候')
   elif actor=='npc/yue' and counts[actor]==2:
    notes=await local(actor,'messages.box','read');assert notes['messages'][-1]['text']=='并行问候'
    assert (await local('npc/lin','records.store','read'))['values']['ap']==9
    await send(actor,'npc/lin','本时刻回应');reply_received.set()
   elif actor=='npc/lin' and counts[actor]==2:
    await asyncio.wait_for(reply_received.wait(),2)
    notes=await local(actor,'messages.box','read');assert notes['messages'][-1]['text']=='本时刻回应'
   return {'status':'completed','output':'确定性并发验收','steps':0}
  finally:events.append([actor,counts[actor],'end']);active[actor]-=1
 b.agent_executor=model
 report=await b.network.nodes['world/pulse'].run(b.signals,cycles=1,timeout_seconds=15)
 assert report['status']=='completed',report
 assert peak==7,(peak,events)
 assert counts['npc/lin']==counts['npc/yue']==2,counts
 assert all(counts[n]==1 for n in actors-{'npc/lin','npc/yue'}),counts
 for actor in ['npc/lin','npc/yue']:
  assert (await local(actor,'records.store','read'))['values']['ap']==9
  state=thaw(b.modules.instances[(actor,'agents.activity')].state)
  assert state['completed_total']==1 and state['activities'][-1]['completed_count']==1,state
  assert state['activities'][-1]['runs']==2,state
 wave=list(b.network.signal_runs.values())[-1]
 assert set(wave['layers'][1])==actors,wave['layers']
 assert wave['layers'][2]==['world/save'] and all(e['status']=='processed' for e in wave['deferred']),wave
 assert not b.node_locks.exclusive and not b.node_locks.active and not b.node_locks.suspended
 # 同时双向收费投递不能死锁，重试同一请求不得再次扣费。
 left,right=await asyncio.gather(send('npc/lin','npc/yue','同时L'),send('npc/yue','npc/lin','同时R'))
 assert not left['duplicate'] and not right['duplicate']
 again=await send('npc/lin','npc/yue','同时L');assert again['duplicate']
 assert (await local('npc/lin','records.store','read'))['values']['ap']==8
 assert (await local('npc/yue','records.store','read'))['values']['ap']==8
 # 普通同步读写、免费消息不得调用事务接口；事务由真正多步骤业务拥有。
 locks=b.node_locks;real=locks.transaction
 def unnecessary(*a,**k):raise AssertionError('普通操作不应申请事务锁')
 locks.transaction=unnecessary
 try:
  await local('npc/lin','records.store','read');await local('npc/lin','records.store','apply',{'set':{'ap':8}})
  spec=thaw(b.network.nodes['npc/yue'].modules['messages.box']);spec['config']['send_cost']=0
  b.modules.unmount('npc/yue','messages.box');b.modules.mount('npc/yue','messages.box',**spec)
  await send('npc/lin','npc/yue','免费便条')
 finally:locks.transaction=real
 result=dict(passed=True,paid_calls=0,max_parallel_models=peak,activity_runs=dict(counts),remaining_ap=8,wave_layers=wave['layers'],deferred=wave['deferred'],events=events)
 (folder/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,directory=str(folder),max_parallel_models=peak,activity_runs=dict(counts),paid_calls=0),ensure_ascii=False))
try:b.runtime.run(run())
finally:b.close()
