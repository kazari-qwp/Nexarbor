"""原活动状态机及消息通知在独立信号层中的联动。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.module_signals import ModuleSignals
from app.runtime.requester import requester_id
from app.runtime.signal_work import current_work
from domain.agent import AgentNode
from domain.core import Link, MarkdownNode, Network, Node, NodeInfo
from domain.pulse_node import PulseNode
from projects.npc_town.modules.agents_activity import AgentsActivityModule
from projects.npc_town.modules.clock_counter import ClockCounterModule
from projects.npc_town.modules.records_store import RecordsStoreModule
from projects.npc_town.modules.messages_box import MessagesBoxModule
from projects.npc_town.modules.messages_relay import MessagesRelayModule

ROOT=Path(__file__).resolve().parents[1]


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='.activity-',dir=ROOT/'build')
        self.addCleanup(self.temp.cleanup)
        self.actor=AgentNode(NodeInfo('alice','Alice'))
        self.saver=NetworkSaver()
        self.backend=Backend(self.temp.name,network=Network([self.actor]),saver=self.saver)
        self.addCleanup(lambda:self.backend.close())
        self.calls=[]
        self.effect=None
        async def agent_run(actor,message):
            self.assertIsNone(self.backend.node_locks.current)
            self.calls.append((actor,message))
            if self.effect is not None:await self.effect(actor,message)
            return dict(status='completed',output='done')
        self.backend.agent_executor=agent_run
        self.account=RecordsStoreModule({'initial':{'ap':1}})
        self.activity=AgentsActivityModule(self.backend.execute_agent,{'enabled':True,'budget':5,'prompt':'original task'},modules=[self.account])
        self.actor.install(self.activity)
        self.saver.tables.module_types.update({
            'records.store':lambda spec:RecordsStoreModule(),
            'agents.activity':lambda spec:AgentsActivityModule(self.backend.execute_agent),
            'messages.box':lambda spec:MessagesBoxModule(self.backend.node_locks.transaction),
            'messages.relay':lambda spec:MessagesRelayModule(),
            'clock.counter':lambda spec:ClockCounterModule(self.backend.node_locks.transaction,self.checkpoint),
        })

    async def checkpoint(self,**kwargs):
        await self.backend.node_locks.wait_prepared()
        self.backend.save(**kwargs)

    async def ap(self):return (await self.account.read())['values']['ap']

    async def test_disabled_activity_skips_model_and_budget_reset(self):
        self.activity.config['enabled']=False
        self.assertEqual((await self.activity.activate('one'))['status'],'skipped')
        self.assertEqual(await self.ap(),1);self.assertEqual(self.calls,[])

    async def test_new_key_resets_budget_once_and_completed_key_is_idempotent(self):
        async def use_ap(actor,message):await self.account.apply(deltas={'ap':-1})
        self.effect=use_ap
        result=await self.activity.activate('one')
        self.assertEqual(result['completed_count'],1);self.assertEqual(result['completed_total'],1)
        self.assertEqual(await self.ap(),4)
        self.assertTrue((await self.activity.activate('one'))['duplicate'])
        self.assertEqual(await self.ap(),4);self.assertEqual(self.calls,[('alice','original task')])
        self.assertEqual((await self.activity.activate('two'))['completed_total'],2)
        self.assertEqual(await self.ap(),4)
        self.assertEqual(self.activity.published['活动完成次数'],2)

    async def test_overlapping_keys_and_running_key_replay_are_rejected(self):
        entered=asyncio.Event();release=asyncio.Event()
        async def hold(actor,message):entered.set();await release.wait()
        self.effect=hold
        first=asyncio.create_task(self.activity.activate('one'))
        await asyncio.wait_for(entered.wait(),1)
        try:
            for key in ('one','two'):
                with self.assertRaises(ValueError):await self.activity.activate(key)
        finally:release.set();await first
        self.assertEqual(len(self.calls),1)

    async def test_failed_key_is_not_silently_replayed(self):
        async def fail(actor,message):raise RuntimeError('model failed')
        self.effect=fail
        with self.assertRaisesRegex(RuntimeError,'model failed'):await self.activity.activate('one')
        self.assertEqual(self.activity.state['activities'][0]['status'],'failed')
        with self.assertRaises(ValueError):await self.activity.activate('one')
        self.assertEqual(len(self.calls),1)

    async def test_notification_requires_current_signal_and_never_creates_activity(self):
        with self.assertRaisesRegex(ValueError,'当前信号'):await self.activity.notify('one')
        class Work:signal_id='one'
        token=current_work.set(Work())
        try:
            self.assertEqual(await self.activity.notify('one'),{'skipped':True})
            await self.activity.activate('one')
            await self.account.apply(set={'ap':0})
            await self.activity.notify('one')
        finally:current_work.reset(token)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(await self.ap(),0)
        self.assertEqual(self.activity.state['completed_total'],1)

    async def test_pending_notifications_use_remaining_budget_and_reaction_limit(self):
        self.activity.config['max_reactions']=2
        class Work:signal_id='one'
        token=current_work.set(Work())
        async def notify(actor,message):
            await self.account.apply(deltas={'ap':-1})
            self.assertEqual(await self.activity.notify('one'),{'queued':True})
        self.effect=notify
        try:await self.activity.activate('one')
        finally:current_work.reset(token)
        self.assertEqual(len(self.calls),3);self.assertEqual(await self.ap(),2)
        self.assertEqual(self.activity.state['activities'][0]['runs'],3)
        self.assertEqual(self.activity.state['completed_total'],1)
        self.assertIn('收到新便条',self.calls[1][1])

    async def test_saved_completed_activity_rebinds_without_duplicate_model_execution(self):
        await self.activity.activate('one');self.backend.save()
        self.backend.restore(self.backend.store.latest())
        self.activity=self.backend.network.get('alice').modules.get('agents.activity')
        self.assertTrue((await self.activity.activate('one'))['duplicate'])
        self.assertEqual(len(self.calls),1)
        await self.activity.activate('two')
        self.assertEqual(len(self.calls),2)

    async def test_actual_message_notification_finishes_before_next_signal_layer(self):
        net=self.backend.network
        pulse=PulseNode(NodeInfo('p','Pulse'),channels=['tick'],strength=3)
        path=Path(self.temp.name)/'clock.md';path.write_text('',encoding='utf-8')
        clock=MarkdownNode(NodeInfo('clock','Clock'),path)
        clock_module=ClockCounterModule(self.backend.node_locks.transaction,self.checkpoint,{'write_text':True})
        clock.install(clock_module)
        bob=AgentNode(NodeInfo('bob','Bob'))
        bob.install(RecordsStoreModule({'initial':{'ap':0}}))
        bob_activity=AgentsActivityModule(self.backend.execute_agent,{'enabled':True,'budget':2})
        bob.install(bob_activity)
        box=MessagesBoxModule(self.backend.node_locks.transaction,{'notify_activity':True},channels=['chat'],strength=1)
        bob.install(box)
        relay=MessagesRelayModule(strength=1);self.actor.install(relay)
        sink=Node(NodeInfo('sink','Sink'))
        for node in (pulse,clock,bob,sink):net.add(node)
        for source,target in [('p','clock'),('clock','alice'),('clock','bob'),('alice','sink'),('bob','sink'),('sink','p')]:
            net.get(source).links.add(Link(target,'tick'))
        self.actor.links.add(Link('bob','chat'));bob.links.add(Link('alice','chat'))
        finished=asyncio.Event();events=[]
        async def work(actor,message):
            events.append((actor,'reaction' if '收到新便条' in message else 'initial'))
            self.assertEqual(requester_id.get(),actor)
            if actor=='bob':
                if len([item for item in events if item[0]=='bob'])==1:finished.set()
                else:self.assertEqual((await box.read())['messages'][0]['text'],'question')
            else:
                await finished.wait()
                result=await relay.send_to('bob','question',key='message-one')
                self.assertTrue(result['notification']['queued'])
        self.effect=work
        subscriptions=ModuleSignals(self.backend.signals);subscriptions.refresh()
        async def after(context):self.assertIn(('bob','reaction'),events)
        self.backend.signals.bind('sink',after)
        result=await pulse.run(self.backend.signals)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['reports'][0]['layers'],[['clock'],['alice','bob'],['sink'],['p']])
        self.assertEqual(clock_module.state['tick'],1)
        self.assertEqual(path.read_text(encoding='utf-8'),'第1天 清晨')
        self.assertEqual(bob_activity.state['completed_total'],1)
        self.assertEqual(bob_activity.state['activities'][0]['runs'],2)
