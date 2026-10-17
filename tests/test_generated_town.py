"""Integration of unchanged Agent-made modules through the public core API.

Run separately with DATANET_COMPONENT_ROOT=extensions/generated_town and its
extension.json selection. No model calls; the fake executor is test-only.
"""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datanet.core.backend import Backend
from datanet.core.tool_access import invoke_tool, list_tools

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'adapters/harness/studio'))
from executor import NativeExecutor


class GeneratedTownTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration=5
        base=ROOT/'build/generated-town-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.doc=json.loads((ROOT/'configs/npc_town/network.json').read_text(encoding='utf8'))
        self.app=Backend(self.temp.name,initial_document=self.doc)
        self.calls=[]
        async def execute(actor,message='',**options):self.calls.append(actor);return {'status':'completed'}
        self.app.agent_executor=execute
    async def asyncTearDown(self):self.app.close();self.temp.cleanup()
    def call(self,actor,target,tool,args=None):
        result=invoke_tool(self.app.network,actor,target,tool,args or {},strength=2)
        self.assertEqual(result.status,'ok',result)
        return result.items[0]['result']
    def op(self,node,module,operation,args=None):return self.app.modules.call(node,module,operation,args or {})
    def entity(self,node):return self.op(node,'entity.profile','read')
    def ap(self,node):return self.op(node,'action.points','get_balance')['remaining']
    def move(self,actor,place):
        r=self.call(actor,place,'move_here');self.assertTrue(r['ok'],r);return r
    async def pulse(self,cycles=1):
        result=await self.app.network.nodes['world/pulse'].run(self.app.signals,cycles=cycles,timeout_seconds=30)
        self.assertEqual(result['status'],'completed',result)
        self.assertTrue(all(r['returned'] for r in result['reports']),result)
        return result
    async def test_action_budget_locality_context_and_rollback(self):
        self.move('npc/shi','place/smith');self.assertEqual(self.ap('npc/shi'),7)
        r=self.call('npc/shi','service/smith_actions','act',{'action':'repair'})
        self.assertTrue(r['ok'],r);self.assertEqual(self.ap('npc/shi'),6)
        self.assertEqual(self.entity('npc/shi')['items']['pickaxe'],1)
        self.move('npc/shi','place/mine');self.assertEqual(self.ap('npc/shi'),3)
        before=copy.deepcopy(self.entity('npc/shi'))
        r=self.call('npc/shi','service/mine_actions','act',{'action':'mine'})
        self.assertFalse(r['ok'],r);self.assertEqual(before,self.entity('npc/shi'))
        self.assertEqual(self.ap('npc/shi'),3)
        tools=list_tools(self.app.network,'npc/shi','service/smith_actions',strength=2).items
        self.assertEqual(tools,[]) # neighboring address yes, its business no
        self.op('npc/shi','resident.context','prepare')
        self.assertIn('矿坑','\n'.join(self.app.network.nodes['npc/shi'].inputs.tail()))
        count=len(self.app.network.nodes['npc/shi'].inputs.pending())
        self.op('npc/shi','resident.context','prepare')
        self.assertEqual(len(self.app.network.nodes['npc/shi'].inputs.pending()),count)
        await self.pulse();self.assertEqual(self.ap('npc/shi'),10)
        self.assertTrue(self.call('npc/shi','service/mine_actions','act',{'action':'mine'})['ok'])
        self.assertEqual(self.ap('npc/shi'),4)
        self.assertEqual(self.entity('npc/shi')['items']['ore'],3)
        self.assertFalse(self.call('npc/shi','service/mine_actions','act',{'action':'mine'})['ok'])
    async def test_batch_production_costs_per_unit_but_trade_per_call(self):
        self.op('npc/shi','entity.profile','adjust',{'items':{'pickaxe':3}})
        before=copy.deepcopy(self.entity('npc/shi'))
        r=self.call('npc/shi','service/mine_actions','act',{'action':'mine','quantity':2})
        self.assertFalse(r['ok'],r);self.assertEqual(self.ap('npc/shi'),10)
        self.assertEqual(self.entity('npc/shi'),before)
        r=self.call('npc/shi','service/mine_actions','act',{'action':'mine','quantity':1})
        self.assertTrue(r['ok'],r);self.assertEqual(self.ap('npc/shi'),4)
        self.move('npc/lin','place/tavern');self.move('npc/lin','place/shop')
        r=self.call('npc/lin','service/shop_actions','act',{'action':'buy_pickaxe','quantity':2})
        self.assertTrue(r['ok'],r);self.assertEqual(self.ap('npc/lin'),3)
        self.assertEqual(self.entity('npc/lin')['coins'],5)
    async def test_presence_home_trade_transfer_and_stale_tools(self):
        # Both move to a common address; gifting uses the recipient's endpoint.
        self.move('npc/lin','place/tavern')
        self.assertTrue(self.call('npc/lin','npc/lu','give',{'coins':5})['ok'])
        self.assertEqual(self.entity('npc/lu')['coins'],5)
        self.assertTrue(self.call('npc/lu','npc/lin','talk',{'message':'谢谢，我会去挣钱。'})['ok'])
        self.assertEqual(self.ap('npc/lu'),9)
        port=NativeExecutor(self.app,None)
        data=port.prepare({'actor':'npc/lu'})
        talk=next(t['name'] for t in data['tools'] if 'talk_' in t['name'] and '林' in t['description'])
        self.move('npc/lin','place/home1')
        denied=port.invoke({'actor':'npc/lu','name':talk,'arguments':{'message':'你还在吗？'}})
        self.assertEqual(denied['status'],'forbidden');self.assertIn('居民楼1',''.join(denied['errors']))
        self.move('npc/lu','place/home2')
        before=self.ap('npc/lu')
        r=self.call('npc/lu','service/home2_actions','act',{'action':'rest'})
        self.assertFalse(r['ok']);self.assertEqual(before,self.ap('npc/lu'))
        self.move('npc/lu','place/shop')
        self.assertTrue(self.call('npc/lu','service/shop_actions','act',{'action':'buy_pickaxe'})['ok'])
        self.assertEqual(self.entity('npc/lu')['coins'],0)
        self.assertEqual(self.entity('npc/lu')['items']['pickaxe'],1)
        before=copy.deepcopy(self.entity('npc/lu'))
        self.assertFalse(self.call('npc/lu','service/shop_actions','act',{'action':'buy_axe'})['ok'])
        self.assertEqual(before,self.entity('npc/lu'))
    async def test_marriage_home_due_birth_next_tick_and_restart(self):
        await self.pulse()
        for actor in ['npc/lin','npc/yue']:self.move(actor,'place/civil')
        a=self.call('npc/lin','service/civil','register_marriage',{'partner':'npc/yue'})
        self.assertTrue(a['waiting']);self.assertNotIn('spouse',self.entity('npc/lin')['profile'])
        b=self.call('npc/yue','service/civil','register_marriage',{'partner':'npc/lin'})
        self.assertTrue(b['registered'],b)
        for actor in ['npc/lin','npc/yue']:self.move(actor,'place/home1')
        self.assertTrue(self.call('npc/lin','service/family1','plan_child')['waiting'])
        self.assertTrue(self.call('npc/yue','service/family1','plan_child')['planned'])
        due=self.entity('npc/yue')['profile']['due_tick'];self.assertEqual(due,10)
        await self.pulse(10);self.assertEqual(self.op('world/time','time.text','get_tick')['tick'],10)
        self.move('npc/yue','place/hospital')
        # Simulate one Agent turn invoking the public tool during its delivery.
        async def birth(actor,message='',**options):
            self.calls.append(actor)
            if actor=='npc/yue':self.born=self.call(actor,'service/hospital','give_birth',{'name':'小满','gender':'female'})
            return {'status':'completed'}
        self.app.agent_executor=birth;self.calls.clear();await self.pulse()
        self.assertTrue(self.born['created'],self.born);child=self.born['child']
        self.assertNotIn(child,self.calls)
        self.assertEqual(self.app.network.nodes[child].management_parent_id,'root')
        self.assertEqual(self.entity(child)['profile']['parents'],['npc/yue','npc/lin'])
        again=self.call('npc/yue','service/hospital','give_birth',{'name':'另一个','gender':'male'})
        self.assertTrue(again['already']);self.assertEqual(again['child'],child)
        self.app.dispatch('save',{'full':True});saved=self.app.store.head
        self.app.close();self.app=Backend(self.temp.name)
        self.assertEqual(self.app.store.head,saved)
        self.assertEqual(self.entity(child)['profile']['name'],'小满')
        self.calls.clear()
        async def record(actor,message='',**options):self.calls.append(actor);return {'status':'completed'}
        self.app.agent_executor=record;await self.pulse()
        self.assertIn(child,self.calls);self.assertEqual(self.ap(child),10)
    async def test_parallel_tick_and_five_tick_snapshot(self):
        active=set();max_active=0
        async def execute(actor,message='',**options):
            nonlocal max_active
            active.add(actor);max_active=max(max_active,len(active));await asyncio.sleep(.01);active.remove(actor)
            return {'status':'completed'}
        self.app.agent_executor=execute;await self.pulse(5)
        self.assertEqual(max_active,7)
        self.assertEqual(self.op('world/save','savepoint.counter','get_count')['count'],5)
        self.assertEqual(self.op('world/time','time.text','get_time')['text'],'第1天-午夜')
    async def test_provenance_and_independent_probability_cap(self):
        for folder in (ROOT/'extensions/generated_town/capabilities').iterdir():
            proof=json.loads((folder/'provenance.json').read_text(encoding='utf8'))
            for name,digest in proof['files'].items():self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),digest)
        config={'events':[dict(id='once',triggers=['test'],probability=1,max_hits=1,message='一次'),dict(id='always',triggers=['test'],probability=1,max_hits=None,message='一直')]}
        self.app.modules.mount('world/save','chance.events',config)
        first=self.op('world/save','chance.events','draw',{'trigger':'test'});second=self.op('world/save','chance.events','draw',{'trigger':'test'})
        self.assertEqual({e['id'] for e in first['events']},{'once','always'})
        self.assertEqual([e['id'] for e in second['events']],['always'])

    async def test_configuration_documents_restore_with_snapshot(self):
        saved=self.app.snapshot()
        self.assertEqual(saved['files']['world/common.md'],self.doc['files']['world/common.md'])
        target=self.app.directory/'personas/child.md';target.unlink()
        self.app.restore(saved)
        self.assertEqual(target.read_text(encoding='utf8'),self.doc['files']['personas/child.md'])
        self.assertIn('world/map.md',self.app.snapshot()['files'])

if __name__=='__main__':unittest.main()
