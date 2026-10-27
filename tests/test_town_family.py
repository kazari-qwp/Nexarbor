"""家庭计划和出生的原两阶段流程；模板端口在此使用故障可控夹具。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.edge_changes import apply_edges
from app.runtime.requester import as_requester
from domain.agent import AgentNode
from domain.annotated_link import AnnotatedLink
from domain.core import Link, MarkdownNode, Network, Node, NodeInfo
from projects.npc_town.modules.agreements_pair import AgreementsPairModule
from projects.npc_town.modules.family_birth import FamilyBirthModule
from projects.npc_town.modules.family_household import FamilyHouseholdModule
from projects.npc_town.modules.place_info import PlaceInfoModule
from projects.npc_town.modules.records_store import RecordsStoreModule
from projects.npc_town.modules.world_time import WorldTimeModule

ROOT=Path(__file__).resolve().parents[1]
CHANNELS=('family','records','location','time','family.pregnancy','family.parent')


class FamilyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.family-',dir=ROOT/'build');self.addCleanup(self.temp.cleanup)
        self.home=Node(NodeInfo('house','House'));self.hospital=Node(NodeInfo('hospital','Hospital'))
        self.a=AgentNode(NodeInfo('a','A'));self.b=AgentNode(NodeInfo('b','B'))
        self.cm=Node(NodeInfo('cm','Mother context'));self.cp=Node(NodeInfo('cp','Partner context'))
        nodes=[self.home,self.hospital,self.a,self.b,self.cm,self.cp]
        for key in ['clock','pregnancy','parent']:
            path=Path(self.temp.name)/(key+'.md');path.write_text(key,encoding='utf-8')
            node=MarkdownNode(NodeInfo(key,key),path);nodes.append(node);setattr(self,key,node)
        self.net=Network(nodes);self.saver=NetworkSaver()
        self.backend=Backend(self.temp.name,network=self.net,saver=self.saver);self.addCleanup(lambda:self.backend.close())
        self.ar=RecordsStoreModule({'initial':{'ap':10,'home':'house','can_gestate':True,'context_node':'cm'}})
        self.br=RecordsStoreModule({'initial':{'ap':10,'home':'house','can_gestate':False,'context_node':'cp'}})
        self.a.install(self.ar);self.b.install(self.br)
        for actor in (self.a,self.b):actor.install(PlaceInfoModule({'location':'house'}))
        self.time=WorldTimeModule(self.transaction,{}, {'tick':12});self.clock.install(self.time)
        pair=AgreementsPairModule(self.transaction,{'address':'house','rules':[{'id':'family_plan','eligible_field':'can_gestate','equal_fields':['home'],'cost':1}]},channels=CHANNELS,strength=3)
        self.home.install(pair)
        self.plan=FamilyHouseholdModule(self.transaction,channels=CHANNELS,strength=3);self.home.install(self.plan)
        self.jobs=[];self.fail_template=False
        self.birth=FamilyBirthModule(self.transaction,self.instantiate,{'duration':10,'cost':1,'templates':[{'home':'house','template':'newborn-house'}]},channels=CHANNELS,strength=3)
        self.hospital.install(self.birth)
        for provider in (self.home,self.hospital):
            for target in ['a','b','cm','cp']:provider.links.add(Link(target,['family','records','location']))
            provider.links.add(Link('clock','time'));provider.links.add(Link('pregnancy','family.pregnancy'));provider.links.add(Link('parent','family.parent'))
        self.saver.tables.module_types.update({
            'records.store':lambda spec:RecordsStoreModule(),'place.info':lambda spec:PlaceInfoModule(),
            'world.time':lambda spec:WorldTimeModule(self.transaction),
            'agreements.pair':lambda spec:AgreementsPairModule(self.transaction),
            'family.household':lambda spec:FamilyHouseholdModule(self.transaction),
            'family.birth':lambda spec:FamilyBirthModule(self.transaction,self.instantiate),
        })

    def transaction(self,nodes,**options):return self.backend.node_locks.transaction(nodes,**options)

    async def instantiate(self,actor,**job):
        self.assertIsNone(self.backend.node_locks.current)
        self.jobs.append((actor,job))
        if self.fail_template:raise RuntimeError('template host failed')
        return {'node_ids':{'child':'child-1'}}

    async def records(self):return (await self.ar.read())['values']

    async def pregnancy_ready(self):
        pregnancy={'id':'preg-1','start_tick':0,'parents':['a','b'],'home':'house'}
        await self.ar.apply(set={'pregnant':True,'pregnancy':pregnancy})
        self.a.modules.get('place.info').state['location']='hospital'
        self.cm.links.add(AnnotatedLink('pregnancy',['context.assembler.context'],threshold=1,attributes={'context':'pregnancy'}))
        return pregnancy

    async def test_household_only_after_both_approvals_and_duplicate_is_idempotent(self):
        with as_requester('a'):first=await self.plan.plan('b','a1')
        self.assertEqual(first['status'],'open');self.assertNotIn('pregnancy',await self.records())
        with as_requester('b'):second=await self.plan.plan('a','b1')
        self.assertEqual(second['status'],'completed')
        values=await self.records();self.assertEqual(values['pregnancy']['start_tick'],12)
        self.assertEqual(values['pregnancy']['parents'],['a','b'])
        self.assertEqual([edge.target_id for edge in self.cm.links],['pregnancy'])
        with as_requester('b'):self.assertTrue((await self.plan.plan('a','b1'))['duplicate'])
        self.assertEqual(len(list(self.cm.links)),1)

    async def test_household_failure_after_approval_rolls_back_second_consent_and_fee(self):
        with as_requester('a'):await self.plan.plan('b','a1')
        await self.br.apply(set={'can_gestate':True})
        # Both can gestate: agreement succeeds provisionally, pregnancy selection must roll the whole operation back.
        with as_requester('b'):
            with self.assertRaisesRegex(ValueError,'一位'):await self.plan.plan('a','b1')
        pair=self.home.modules.get('agreements.pair')
        self.assertEqual(pair.state['agreements'][0]['status'],'open')
        self.assertEqual(len(pair.state['agreements'][0]['approvals']),1)
        self.assertNotIn('pregnancy',await self.records())
        self.assertEqual((await self.br.read())['values']['ap'],10)

    async def test_time_source_must_be_unique_and_reachable(self):
        self.home.links.remove(next(edge for edge in self.home.links if edge.target_id=='clock'))
        with as_requester('a'):
            with self.assertRaisesRegex(ValueError,'唯一'):await self.plan.plan('b','a1')
        self.assertEqual(self.plan.state,{})

    async def test_birth_inspect_elapsed_and_not_ready_no_charge_or_job(self):
        pregnancy=await self.pregnancy_ready();pregnancy['start_tick']=10
        await self.ar.apply(set={'pregnancy':pregnancy})
        with as_requester('a'):
            info=await self.birth.inspect();self.assertEqual(info['elapsed'],2);self.assertFalse(info['ready'])
            with self.assertRaisesRegex(ValueError,'生产时间'):await self.birth.deliver('Baby','one')
        self.assertEqual((await self.records())['ap'],10);self.assertEqual(self.jobs,[])

    async def test_birth_template_failure_preserves_paid_pending_job_and_retry_same_name(self):
        await self.pregnancy_ready();self.fail_template=True
        with as_requester('a'):
            with self.assertRaisesRegex(RuntimeError,'template host failed'):await self.birth.deliver('Baby','one')
        self.assertEqual((await self.records())['ap'],9);self.assertIn('preg-1',self.birth.state['pending'])
        self.assertTrue((await self.records())['pregnant'])
        self.fail_template=False
        with as_requester('a'):
            with self.assertRaisesRegex(ValueError,'原姓名'):await self.birth.deliver('Changed','one')
            result=await self.birth.deliver('Baby','one')
            self.assertTrue((await self.birth.deliver('Baby','one'))['duplicate'])
        self.assertEqual(result['child'],'child-1');self.assertEqual((await self.records())['ap'],9)
        self.assertEqual(self.jobs[0][1],self.jobs[1][1]);self.assertEqual(self.jobs[0][1]['key'],'birth-preg-1')

    async def test_birth_finalizes_both_parent_references_and_context_edges(self):
        await self.pregnancy_ready()
        with as_requester('a'):await self.birth.deliver('Baby','one')
        own=await self.records();other=(await self.br.read())['values']
        for values in (own,other):self.assertTrue(values['is_parent']);self.assertEqual(values['child_preg-1'],'child-1')
        self.assertFalse(own['pregnant']);self.assertNotIn('pregnancy',own)
        self.assertEqual([edge.target_id for edge in self.cm.links],['parent']);self.assertEqual([edge.target_id for edge in self.cp.links],['parent'])
        self.assertEqual(self.birth.state['pending'],{});self.assertEqual(len(self.birth.state['births']),1)

    async def test_birth_pending_job_survives_journal_reopen(self):
        await self.pregnancy_ready();self.fail_template=True
        with as_requester('a'):
            with self.assertRaises(RuntimeError):await self.birth.deliver('Baby','one')
        self.backend.save();self.backend.close();self.backend=Backend(self.temp.name,saver=self.saver)
        self.birth=self.backend.network.get('hospital').modules.get('family.birth');self.ar=self.backend.network.get('a').modules.get('records.store')
        self.fail_template=False
        with as_requester('a'):await self.birth.deliver('Baby','one')
        self.assertEqual((await self.records())['ap'],9);self.assertEqual(len(self.birth.state['births']),1)

    async def test_edge_batch_removes_only_matching_metadata_and_rolls_back(self):
        first=AnnotatedLink('pregnancy',['context.assembler.context'],threshold=1,attributes={'context':'pregnancy'})
        other=AnnotatedLink('pregnancy',['other'],attributes={'context':'pregnancy'})
        self.cm.links.add(first);self.cm.links.add(other)
        with self.assertRaises(ValueError):
            async with self.transaction(['cm']):
                apply_edges([(self.cm,'remove',AnnotatedLink('pregnancy',['context.assembler.context'],threshold=1,attributes={'context':'pregnancy'}))])
                self.assertEqual(list(self.cm.links),[other])
                raise ValueError('rollback')
        self.assertEqual(list(self.cm.links),[first,other])
