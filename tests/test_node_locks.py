"""Deterministic node transaction, admission, rollback and journal regressions."""
import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.module_protocol import ModuleDefinition, ComponentResult
from datanet.core.node_modules import NodeModules
from datanet.core.signals import Signal


class NodeLockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.b = SimpleNamespace(network=Network(), agents={}, _transaction_lock=RLock(),
            components=SimpleNamespace(module_owners={},module_extensions={},enabled=set()))
        for node in ('a','b','c','u','hidden'):
            self.b.network.add_node(AgentNode(node,node,file_path=Path(self.temp.name)/(node+'.md')))
        for source,target in [('a','b'),('a','c'),('u','b'),('u','a'),('c','b')]:
            self.b.network.nodes[source].connect(target,channels=['red'])
        self.handlers = {}
        async def execute(ctx, activation):
            if activation.kind == 'signal':
                return await self.handlers['signal'](ctx,activation)
            if activation.operation == 'read': return ComponentResult(data=dict(ctx.state))
            if activation.operation == 'set':
                ctx.state['value'] = activation.parameters['value']
                return ComponentResult(data=dict(ctx.state))
            return await self.handlers[ctx.node_id](ctx,activation)
        definition = ModuleDefinition(execute,operations=[dict(name=name,channels=['red'],parameters={'type':'object'},result={})
            for name in ('run','read','set')],signals=['red'])
        self.b.modules = NodeModules(self.b,{'probe':definition})
        for node in self.b.network.nodes:
            self.b.modules.mount(node,'probe',state={'value':'old'},access=dict(strength=2,channels=['red']))
        self.locks = self.b.node_locks
        self.b.signals = self.b.network.signals

    async def asyncTearDown(self):
        await self.b.signals.close()
        self.assertEqual(self.locks.exclusive,{})
        self.assertEqual(self.locks.active,{})
        self.assertEqual(self.locks.waiters,set())
        self.assertEqual(self.locks.dependencies,{})
        self.assertEqual(self.locks.leases,{})
        self.assertEqual(self.locks.suspended,{})
        self.b.modules.clear(); self.temp.cleanup()

    async def call(self,node,operation='run',**parameters):
        return await self.b.modules.call(node,'probe',operation,parameters)

    async def test_external_wait_releases_admission_and_reenters_after_short_transaction(self):
        waiting,returned,held,release=(asyncio.Event() for _ in range(4))
        async def actor():
            async with self.locks.access(['a']):
                async with self.locks.suspend_access():waiting.set();await returned.wait()
                self.assertFalse(self.locks.exclusive)
                self.assertIn('a',self.locks.active)
        async def writer():
            async with self.locks.transaction('u',['a'],strength=1,channels=['red']):held.set();await release.wait()
        task=asyncio.create_task(actor());await waiting.wait()
        write=asyncio.create_task(writer());await asyncio.wait_for(held.wait(),1)
        returned.set();await asyncio.sleep(.01);self.assertFalse(task.done())
        release.set();await asyncio.gather(task,write)

    async def test_external_wait_cancellation_and_deleted_target_clean_admission(self):
        entered=asyncio.Event()
        async def actor():
            async with self.locks.access(['a']):
                async with self.locks.suspend_access():entered.set();await asyncio.Event().wait()
        task=asyncio.create_task(actor());await entered.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        async with self.locks.access(['a']):
            async with self.locks.suspend_access():self.b.network.nodes.pop('a')
        self.assertEqual(self.locks.suspended,{})

    async def test_external_wait_must_not_let_go_of_an_explicit_transaction(self):
        async with self.locks.transaction('u',['a'],strength=1,channels=['red']):
            with self.assertRaisesRegex(RuntimeError,'Release node transactions'):
                async with self.locks.suspend_access():pass

    async def test_queries_calls_and_signals_wait_without_blocking_event_loop(self):
        ready,release = asyncio.Event(),asyncio.Event(); signals=[]
        async def hold(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                await ctx.network.call('b','probe','set',{'value':'new'})
                ready.set();await release.wait()
            return ComponentResult()
        async def query(ctx,activation):
            return ComponentResult(data=await ctx.network.metadata('b'))
        async def signal(ctx,activation):
            signals.append(ctx.node_id);return ComponentResult()
        self.handlers.update(a=hold,u=query,signal=signal)
        owner=asyncio.create_task(self.call('a'));await ready.wait()
        reader=asyncio.create_task(self.call('b','read'))
        query_task=asyncio.create_task(self.call('u'))
        receipt=self.b.signals.emit(Signal('c',['red'],1))
        await asyncio.sleep(.02)
        self.assertFalse(reader.done());self.assertFalse(query_task.done());self.assertEqual(signals,[])
        self.assertIn('b',{n.node_id for n,_,_ in self.b.network.walk_states('u',strength=1,channels=['red'])})
        release.set();await owner
        self.assertEqual((await reader)['data']['value'],'new');await query_task
        await self.b.signals.wait(receipt['signal_id']);self.assertEqual(signals,['b'])

    async def test_active_access_finishes_before_lock_is_granted(self):
        entered,finish,acquired = asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def busy(ctx,activation):entered.set();await finish.wait();return ComponentResult()
        async def hold(ctx,activation):
            async with ctx.network.lock_nodes(['b']):acquired.set()
            return ComponentResult()
        self.handlers.update(a=hold,b=busy)
        running=asyncio.create_task(self.call('b'));await entered.wait()
        owner=asyncio.create_task(self.call('a'));await asyncio.sleep(.01)
        self.assertFalse(acquired.is_set());finish.set();await running;await owner
        self.assertTrue(acquired.is_set())

    async def test_exception_restores_state_links_publications_inputs_and_bindings(self):
        self.b.agents['b']={'activity':'before'}
        async def alter(ctx,activation):
            ctx.publish_metadata({'state':'changed'});ctx.update_inputs({'tail':['changed']})
            ctx.state['value']='new';return ComponentResult()
        self.handlers['b']=alter
        before=deepcopy(self.b.network.nodes['b'].interfaces)
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                await ctx.network.call('b','probe','run')
                self.b.network.nodes['b'].connect('c',channels=['red'])
                self.b.agents['b']['activity']='changed'
                raise ValueError('abort')
        self.handlers['a']=owner
        with self.assertRaisesRegex(ValueError,'abort'):await self.call('a')
        self.assertEqual((await self.call('b','read'))['data']['value'],'old')
        self.assertEqual(self.b.network.nodes['b'].interfaces,before)
        self.assertEqual(self.b.network.nodes['b'].inputs.tail(),[])
        self.assertNotIn('extensions',self.b.network.nodes['b'].get_metadata())
        self.assertEqual(self.b.agents['b']['activity'],'before')

    async def test_cancellation_rolls_back_and_releases_queued_access(self):
        ready=asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                await ctx.network.call('b','probe','set',{'value':'partial'})
                ready.set();await asyncio.Event().wait()
        self.handlers['a']=owner
        task=asyncio.create_task(self.call('a'));await ready.wait()
        read=asyncio.create_task(self.call('b','read'));await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual((await read)['data']['value'],'old')

    async def test_call_chain_reentry_does_not_grant_more_channels_or_strength(self):
        async def nested(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                ctx.state['value']='nested'
                with self.assertRaises(PermissionError):
                    async with ctx.network.lock_nodes(['hidden']):pass
                with self.assertRaises(PermissionError):await ctx.network.metadata('hidden')
            return ComponentResult()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):await ctx.network.call('b','probe','run')
            return ComponentResult()
        self.handlers.update(a=owner,b=nested)
        await self.call('a');self.assertEqual((await self.call('b','read'))['data']['value'],'nested')

    async def test_nested_cannot_expand_group_and_uncaught_nested_failure_aborts_group(self):
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['a','b']):
                with self.assertRaisesRegex(RuntimeError,'cannot expand'):
                    async with ctx.network.lock_nodes(['c']):pass
                try:
                    async with ctx.network.lock_nodes(['b']):
                        await ctx.network.call('b','probe','set',{'value':'partial'})
                        raise ValueError('nested')
                except ValueError:pass
            return ComponentResult()
        self.handlers['a']=owner
        with self.assertRaisesRegex(RuntimeError,'rolled back'):await self.call('a')
        self.assertEqual((await self.call('b','read'))['data']['value'],'old')

    async def test_revalidate_queued_access_after_path_is_removed(self):
        ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['u','b']):
                ready.set();await release.wait()
                self.b.network.nodes['u'].interfaces.clear()
            return ComponentResult()
        async def reader(ctx,activation):return ComponentResult(data=await ctx.network.call('b','probe','read'))
        self.handlers.update(a=owner,u=reader)
        # Make u reachable to the lock owner, without granting hidden nodes.
        self.b.network.nodes['a'].connect('u',channels=['red'])
        owner_task=asyncio.create_task(self.call('a'));await ready.wait()
        pending=asyncio.create_task(self.b.modules.access('u','b','probe','read',strength=1,channels=['red']))
        await asyncio.sleep(.01);self.assertFalse(pending.done())
        release.set();await owner_task
        with self.assertRaises(PermissionError):await pending

    async def test_timeout_and_cancellation_do_not_take_part_of_a_group(self):
        ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):ready.set();await release.wait()
            return ComponentResult()
        self.handlers['a']=owner
        task=asyncio.create_task(self.call('a'));await ready.wait()
        with self.assertRaises(TimeoutError):
            async with self.locks.transaction('u',['b','c'],strength=2,channels=['red'],timeout=.02):pass
        self.assertNotIn('c',self.locks.exclusive)
        release.set();await task

    async def test_unawaited_children_finish_before_commit_or_rollback(self):
        async def slow(ctx,activation):
            await asyncio.sleep(.01);ctx.state['value']='child';return ComponentResult()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):ctx.network.call('b','probe','run')
            return ComponentResult()
        self.handlers.update(a=owner,b=slow)
        await self.call('a');self.assertEqual((await self.call('b','read'))['data']['value'],'child')

    async def test_uncommitted_topology_is_not_visible_to_other_owners(self):
        ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['a','b']):
                self.b.network.nodes['a'].interfaces.clear()
                ready.set();await release.wait()
            return ComponentResult()
        self.handlers['a']=owner
        task=asyncio.create_task(self.call('a'));await ready.wait()
        reached={n.node_id for n,_,_ in self.b.network.walk_states('a',strength=2,channels=['red'])}
        self.assertIn('b',reached)
        release.set();await task
        self.assertEqual({n.node_id for n,_,_ in self.b.network.walk_states('a',strength=2,channels=['red'])},{'a'})

    async def test_mutating_unlocked_nodes_and_lifecycle_changes_are_rejected(self):
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                with self.assertRaises(PermissionError):ctx.state['value']='not locked'
                with self.assertRaises(PermissionError):await ctx.network.call('c','probe','set',{'value':'bad'})
                with self.assertRaises(RuntimeError):self.b.modules.unmount('b','probe')
            return ComponentResult()
        self.handlers['a']=owner;await self.call('a')

    async def test_concurrent_upgrades_queue_without_holding_admission(self):
        from datanet.core.node_locks import NodeLockDeadlockError
        started=set();both=asyncio.Event()
        self.b.network.nodes['b'].connect('a',channels=['red'])
        async def owner(ctx,activation):
            started.add(ctx.node_id)
            if len(started)==2:both.set()
            await both.wait()
            async with ctx.network.lock_nodes(['a','b']):pass
            return ComponentResult()
        self.handlers.update(a=owner,b=owner)
        results=await asyncio.wait_for(asyncio.gather(self.call('a'),self.call('b'),return_exceptions=True),1)
        self.assertTrue(all(isinstance(result,dict) for result in results),results)

    async def test_sibling_access_started_before_lock_must_drain(self):
        entered,release,acquired=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def child(ctx,activation):entered.set();await release.wait();return ComponentResult()
        async def owner(ctx,activation):
            request=ctx.network.call('b','probe','run');await entered.wait()
            async with ctx.network.lock_nodes(['b']):acquired.set()
            await request;return ComponentResult()
        self.handlers.update(a=owner,b=child)
        task=asyncio.create_task(self.call('a'));await entered.wait();await asyncio.sleep(.01)
        self.assertFalse(acquired.is_set());release.set();await task
        self.assertTrue(acquired.is_set())

    async def test_host_adapter_ticket_preserves_ancestry_and_expires(self):
        async def owner(ctx,activation):
            with self.locks.export_owner('a') as ticket:
                async def callback():
                    with self.locks.import_owner(ticket,'a'):
                        async with self.locks.transaction('a',['a','b'],strength=1,channels=['red']):
                            await self.call('b','set',value='host')
                await asyncio.to_thread(lambda:asyncio.run(callback()))
            with self.assertRaises(PermissionError):
                with self.locks.import_owner(ticket,'a'):pass
            return ComponentResult()
        self.handlers['a']=owner
        await asyncio.wait_for(self.call('a'),1)

    async def test_queued_second_signal_does_not_prevent_first_handler_locking_itself(self):
        entered=asyncio.Event();release=asyncio.Event();count=[]
        async def signal(ctx,activation):
            count.append(ctx.node_id)
            if len(count)==1:
                entered.set();await release.wait()
            async with ctx.network.lock_nodes([ctx.node_id]):ctx.state['value']='signaled'
            return ComponentResult()
        self.handlers['signal']=signal
        first=self.b.signals.emit(Signal('c',['red'],1));await entered.wait()
        second=self.b.signals.emit(Signal('c',['red'],1));await asyncio.sleep(.01);release.set()
        await asyncio.wait_for(asyncio.gather(self.b.signals.wait(first['signal_id']),self.b.signals.wait(second['signal_id'])),1)
        self.assertEqual(count,['b','b'])

    async def test_explicit_commit_and_rollback_and_abandoned_scope_cleanup(self):
        async def owner(ctx,activation):
            lock=await ctx.network.lock_nodes(['b'])
            await ctx.network.call('b','probe','set',{'value':'committed'});await lock.commit()
            lock=await ctx.network.lock_nodes(['b'])
            await ctx.network.call('b','probe','set',{'value':'discarded'});await lock.rollback()
            return ComponentResult()
        self.handlers['a']=owner;await self.call('a')
        self.assertEqual((await self.call('b','read'))['data']['value'],'committed')
        async def forgotten(ctx,activation):
            await ctx.network.lock_nodes(['b'])
            await ctx.network.call('b','probe','set',{'value':'forgotten'})
            return ComponentResult()
        self.handlers['a']=forgotten
        with self.assertRaisesRegex(RuntimeError,'Unclosed'):await self.call('a')
        self.assertEqual((await self.call('b','read'))['data']['value'],'committed')

    async def test_closed_loop_signal_waits_for_locked_return_node(self):
        processing,finish_signal=asyncio.Event(),asyncio.Event()
        locked,release=asyncio.Event(),asyncio.Event()
        self.b.network.nodes['b'].connect('a',channels=['red'])
        async def signal(ctx,activation):processing.set();await finish_signal.wait();return ComponentResult()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['a']):locked.set();await release.wait()
            return ComponentResult()
        self.handlers.update(u=owner,signal=signal)
        receipt=self.b.signals.emit(Signal('a',['red'],2,close_loop=True))
        await processing.wait();task=asyncio.create_task(self.call('u'));await locked.wait();finish_signal.set()
        wait=asyncio.create_task(self.b.signals.wait(receipt['signal_id']));await asyncio.sleep(.01)
        self.assertFalse(wait.done());release.set();await task
        self.assertTrue((await wait)['returned'])

    async def test_two_held_groups_cannot_deadlock_on_cross_reads(self):
        from datanet.core.node_locks import NodeLockDeadlockError
        self.b.network.nodes['b'].connect('a',channels=['red'])
        ready=set();both=asyncio.Event()
        async def holder(ctx,activation):
            async with ctx.network.lock_nodes([ctx.node_id]):
                ready.add(ctx.node_id)
                if len(ready)==2:both.set()
                await both.wait()
                await ctx.network.metadata('b' if ctx.node_id=='a' else 'a')
            return ComponentResult()
        self.handlers.update(a=holder,b=holder)
        results=await asyncio.wait_for(asyncio.gather(self.call('a'),self.call('b'),return_exceptions=True),1)
        self.assertEqual(sum(isinstance(result,NodeLockDeadlockError) for result in results),1)
        self.assertEqual(sum(isinstance(result,dict) for result in results),1)

    async def test_native_wait_releases_outer_access_and_callback_keeps_wave_identity(self):
        import importlib.util
        from threading import Event
        from datanet.core.signal_work import current_work
        spec=importlib.util.spec_from_file_location('native_wait_fixture',Path(__file__).resolve().parents[1]/'adapters/harness/studio/executor.py')
        native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
        started=asyncio.Event();release=Event();loop=asyncio.get_running_loop()
        class Transport:
            def host(_,method,params):
                self.assertEqual(method,'agent-run');loop.call_soon_threadsafe(started.set)
                if not release.wait(2):raise TimeoutError('模型等待验收超时')
                with self.locks.import_owner(params['node_access_ticket'],'a'):
                    self.assertEqual(current_work.get().signal_id,'native-wave')
                    self.assertEqual(__import__('datanet.core.node_locks',fromlist=['_access_stack'])._access_stack.get(),())
                    asyncio.run(self.b.modules.access('a','b','probe','set',{'value':'callback'},strength=1,channels=['red']))
                return dict(status='completed',session_id='native-test')
        executor=object.__new__(native.NativeExecutor);executor.backend=self.b;executor.transport=Transport()
        async def visit(*args,**kwargs):return []
        executor.module_tools=SimpleNamespace(visit=visit)
        executor.binding=lambda actor:(self.b.network.nodes[actor],dict(strength=1,channels=['red']))
        async def actor():
            token=current_work.set(SimpleNamespace(signal_id='native-wave'))
            try:
                async with self.locks.access(['a']):return await executor.run('a')
            finally:current_work.reset(token)
        task=asyncio.create_task(actor());await started.wait()
        try:
            async with self.locks.transaction('u',['a'],strength=1,channels=['red']):
                self.assertFalse(task.done())
        finally:release.set()
        self.assertEqual((await asyncio.wait_for(task,2))['status'],'completed')
        self.assertEqual((await self.call('b','read'))['data']['value'],'callback')

    async def test_native_network_listing_waits_for_locked_metadata(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'adapters/harness/studio/executor.py'
        spec=importlib.util.spec_from_file_location('node_lock_native_executor',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        executor=object.__new__(module.NativeExecutor);executor.backend=self.b
        self.b.network.nodes['u'].execution_binding={'executor':'harness','strength':2,'channels':['red']}
        ready,release=asyncio.Event(),asyncio.Event()
        async def holder(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                self.b.network.nodes['b'].name='new name';ready.set();await release.wait()
            return ComponentResult()
        self.handlers['a']=holder
        owner=asyncio.create_task(self.call('a'));await ready.wait()
        query=asyncio.create_task(asyncio.to_thread(executor.visit,{'actor':'u'}))
        await asyncio.sleep(.01);self.assertFalse(query.done())
        release.set();await owner
        nodes=(await asyncio.wait_for(query,1))['nodes']
        self.assertEqual(next(n['name'] for n in nodes if n['node_id']=='b'),'new name')

    async def test_standard_executor_waits_for_locked_node(self):
        from datanet.core.execution import ExecutorRegistry,ExecutionResult
        calls=[]
        class Executor:
            def run(self,request,tools):calls.append(request.node_id);return ExecutionResult('completed')
        registry=ExecutorRegistry(self.b.network);registry.register('fixture',Executor());registry.bind('b','fixture','b')
        ready,release=asyncio.Event(),asyncio.Event()
        async def holder(ctx,activation):
            async with ctx.network.lock_nodes(['b']):ready.set();await release.wait()
            return ComponentResult()
        self.handlers['a']=holder
        owner=asyncio.create_task(self.call('a'));await ready.wait()
        execution=asyncio.create_task(asyncio.to_thread(registry.run,'b','run'))
        await asyncio.sleep(.01);self.assertEqual(calls,[])
        release.set();await owner;await asyncio.wait_for(execution,1)
        self.assertEqual(calls,['b'])

    async def test_private_topology_tool_obeys_the_same_target_lock(self):
        from datanet.core.interface_management import attach_interface_management_tools
        self.b.network.nodes['b'].management_parent_id='u'
        attach_interface_management_tools(self.b.network,self.b.network.nodes['u'],scope='children',allow_external_targets=True)
        ready,release=asyncio.Event(),asyncio.Event()
        async def holder(ctx,activation):
            async with ctx.network.lock_nodes(['b']):ready.set();await release.wait()
            return ComponentResult()
        self.handlers['a']=holder
        owner=asyncio.create_task(self.call('a'));await ready.wait()
        operation=asyncio.create_task(asyncio.to_thread(self.b.network.nodes['u'].tools['manage_interfaces'],
            'add',node_id='b',target_node_id='c',interface={'metadata':{'channels':['red']}}))
        await asyncio.sleep(.01);self.assertFalse(operation.done())
        release.set();await owner
        self.assertEqual((await asyncio.wait_for(operation,1)).status,'ok')
        self.assertEqual(self.b.network.nodes['b'].interfaces[0].target_node_id,'c')


class NodeLockPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from datanet.core.backend import Backend
        self.temp=TemporaryDirectory();self.handlers={}
        async def execute(ctx,activation):
            if activation.operation=='set':
                ctx.state['value']=activation.parameters['value']
                return ComponentResult()
            if activation.operation=='mutate':
                ctx.state['value']='new';ctx.publish_metadata({'label':'new'})
                ctx.update_inputs({'tail':['new place']})
                self.b.network.nodes[ctx.node_id].write_memory('new memory')
                self.b.agents[ctx.node_id]={'activity':'new'}
                return ComponentResult()
            return await self.handlers[ctx.node_id](ctx,activation)
        self.definition=ModuleDefinition(execute,operations=[dict(name=name,channels=['red'],parameters={'type':'object'},result={})
            for name in ('run','set','mutate')])
        def services():
            return SimpleNamespace(module_types={'probe':self.definition},module_owners={},module_extensions={},
                enabled=set(),node_presets={},network_presets={},finalizers=[],mutations=set(),routes={},
                install=lambda b:None,graph_loaded=lambda b:None,snapshot=lambda b:{},
                restore=lambda b,d:None,restore_node=lambda b,n,d:None,toolkits=lambda b:{})
        self.service_patch=patch('datanet.core.backend.ComponentServices',side_effect=services)
        self.addCleanup(self.service_patch.stop)
        self.service_patch.start();self.b=Backend(self.temp.name)
        self.addCleanup(lambda:self.b.close())
        for node in ('b','c'):
            self.b.network.add_node(AgentNode(node,node,file_path=self.b.directory/(node+'.md')))
            self.b.network.nodes['root'].connect(node,channels=['red'])
        for node in ('root','b','c'):
            self.b.modules.mount(node,'probe',state={'value':'old'},access=dict(strength=1,channels=['red']))
        self.b.network.nodes['b'].write_memory('old memory')
        self.b.agents['b']={'activity':'old'}
        self.b.dispatch('save',{})

    async def asyncTearDown(self):
        self.assertEqual(self.b.node_locks.exclusive,{})
        self.b.close();self.service_patch.stop();self.temp.cleanup()

    def entry(self,document,node):
        return next(entry for entry in document['network']['nodes'] if entry['node_id']==node)

    async def test_unrelated_save_uses_before_images_then_success_commits_whole_group(self):
        ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['root','b']):
                ctx.state['value']='new root'
                await ctx.network.call('b','probe','mutate')
                self.b.network.nodes['root'].interfaces.clear()
                ready.set();await release.wait()
            return ComponentResult()
        self.handlers['root']=owner
        task=asyncio.create_task(self.b.modules.call('root','probe','run'));await ready.wait()
        await self.b.modules.call('c','probe','set',{'value':'other committed'})
        await asyncio.to_thread(self.b.dispatch,'save',{})
        saved=self.b.store.latest()
        self.assertEqual(self.entry(saved,'root')['modules']['probe']['state']['value'],'old')
        self.assertEqual(len(self.entry(saved,'root')['connections']['interfaces']),2)
        self.assertIn('root → b, c',self.b.reachable_structure('root',channels=['red'],depth=1)['interfaces'])
        self.assertEqual(self.entry(saved,'b')['modules']['probe']['state']['value'],'old')
        self.assertEqual(self.entry(saved,'c')['modules']['probe']['state']['value'],'other committed')
        self.assertEqual(saved['files']['b.md'],'old memory')
        self.assertEqual(saved['agents']['b']['activity'],'old')
        self.assertEqual(saved['node_publications']['b'],{})
        release.set();await task
        saved=self.b.store.latest()
        self.assertEqual(self.entry(saved,'root')['connections']['interfaces'],[])
        self.assertEqual(self.entry(saved,'root')['modules']['probe']['state']['value'],'new root')
        self.assertEqual(self.entry(saved,'b')['modules']['probe']['state']['value'],'new')
        self.assertEqual(self.entry(saved,'c')['modules']['probe']['state']['value'],'other committed')
        self.assertEqual(saved['files']['b.md'],'new memory')
        self.assertEqual(saved['node_publications']['b']['probe'],{'label':'new'})

    async def test_rollback_restores_files_and_keeps_other_nodes_committed(self):
        ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                await ctx.network.call('b','probe','mutate')
                ready.set();await release.wait();raise RuntimeError('abort transaction')
        self.handlers['root']=owner
        task=asyncio.create_task(self.b.modules.call('root','probe','run'));await ready.wait()
        await self.b.modules.call('c','probe','set',{'value':'kept'})
        await asyncio.to_thread(self.b.dispatch,'save',{})
        release.set()
        with self.assertRaisesRegex(RuntimeError,'abort transaction'):await task
        self.assertEqual(self.b.network.nodes['b'].read_memory()['content'],'old memory')
        self.assertEqual(self.b.network.nodes['b'].inputs.tail(),[])
        self.assertNotIn('extensions',self.b.network.nodes['b'].get_metadata())
        self.assertEqual(self.b.modules.instances[('b','probe')].state['value'],'old')
        self.assertEqual(self.b.modules.instances[('c','probe')].state['value'],'kept')

    async def test_restart_restores_committed_state_and_published_metadata(self):
        from datanet.core.backend import Backend
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):await ctx.network.call('b','probe','mutate')
            return ComponentResult()
        self.handlers['root']=owner
        await self.b.modules.call('root','probe','run');self.b.close();self.b=Backend(self.temp.name)
        self.assertEqual(self.b.modules.instances[('b','probe')].state['value'],'new')
        self.assertEqual(self.b.network.nodes['b'].read_memory()['content'],'new memory')
        self.assertEqual(self.b.network.nodes['b'].get_metadata()['extensions']['probe'],{'label':'new'})
        self.assertEqual(self.b.node_locks.exclusive,{})

    async def test_commit_failure_rolls_back_and_stops_future_access(self):
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):await ctx.network.call('b','probe','mutate')
            return ComponentResult()
        self.handlers['root']=owner
        with patch.object(self.b.store,'commit',side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(OSError,'disk failure'):await self.b.modules.call('root','probe','run')
        self.assertTrue(self.b.failed)
        self.assertEqual(self.b.network.nodes['b'].read_memory()['content'],'old memory')
        with self.assertRaisesRegex(RuntimeError,'restart'):
            await self.b.modules.call('b','probe','set',{'value':'must not run'})

    def install_context_port(self):
        logs={'session-b':['before']};restored=[]
        def cursor(session):return dict(adapter='test',session_id=session,event_count=len(logs[session]),prefix_hash=str(logs[session]))
        class Port:
            async def capture(_,bindings):return {node:cursor(session) for node,session in bindings.items()}
            async def restore(_,contexts):
                result={}
                for node,value in contexts.items():
                    session='fork-'+str(len(restored));logs[session]=logs[value['session_id']][:value['event_count']]
                    restored.append(session);result[node]=cursor(session)
                return dict(contexts=result)
        self.b.context_port=Port();self.b.agents['b']['session_id']='session-b'
        return logs,restored,cursor

    async def test_context_only_change_is_a_node_delta_and_reuses_unchanged_cursor(self):
        logs,restored,cursor=self.install_context_port()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):logs['session-b'].append('inside')
            return ComponentResult()
        self.handlers['root']=owner
        await self.b.modules.call('root','probe','run')
        saved=self.b.store.latest();entry=self.entry(saved,'b')
        self.assertEqual(entry['context_cursor']['event_count'],2)
        self.assertEqual(entry['modules']['probe']['state']['value'],'old')
        count=self.b.store.head
        async def noop(ctx,activation):
            async with ctx.network.lock_nodes(['b']):pass
            return ComponentResult()
        self.handlers['root']=noop;await self.b.modules.call('root','probe','run')
        self.assertEqual(self.b.store.head,count)
        self.assertEqual(restored,[])

    async def test_context_before_image_is_saved_and_failure_forks_original_prefix(self):
        logs,restored,cursor=self.install_context_port();ready,release=asyncio.Event(),asyncio.Event()
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):
                logs['session-b'].append('uncommitted');ready.set();await release.wait()
                raise ValueError('context abort')
        self.handlers['root']=owner
        task=asyncio.create_task(self.b.modules.call('root','probe','run'));await ready.wait()
        await asyncio.to_thread(self.b.dispatch,'save',{})
        self.assertEqual(self.entry(self.b.store.latest(),'b')['context_cursor']['event_count'],1)
        info=self.b.dispatch('persistence_info',{})
        self.assertEqual(info['locked_contexts']['b']['event_count'],1)
        release.set()
        with self.assertRaisesRegex(ValueError,'context abort'):await task
        self.assertEqual(logs['session-b'],['before','uncommitted'])
        self.assertEqual(logs[restored[0]],['before'])
        self.assertEqual(self.b.agents['b']['session_id'],restored[0])
        self.assertEqual(self.entry(self.b.store.latest(),'b')['context_cursor']['session_id'],restored[0])

    async def test_save_waits_for_context_preparation_without_observing_partial_record(self):
        logs,restored,cursor=self.install_context_port();entered,release=asyncio.Event(),asyncio.Event()
        port=self.b.context_port;original=port.capture
        async def slow(bindings):entered.set();await release.wait();return await original(bindings)
        port.capture=slow
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):pass
            return ComponentResult()
        self.handlers['root']=owner
        task=asyncio.create_task(self.b.modules.call('root','probe','run'));await entered.wait()
        save=asyncio.create_task(asyncio.to_thread(self.b.dispatch,'save',{}))
        await asyncio.sleep(.02);self.assertFalse(save.done())
        self.assertTrue(self.b.dispatch('persistence_info',{})['node_locks_preparing'])
        release.set();await task;await save
        self.assertEqual(self.entry(self.b.store.latest(),'b')['context_cursor']['event_count'],1)

    async def test_node_records_keep_boundary_links_without_copying_targets(self):
        from datanet.core.node_records import merge_records
        records=self.b.capture_node_records(['root'])
        self.assertEqual(set(records),{'root'})
        self.assertEqual({edge['target_node_id'] for edge in records['root']['node']['connections']['interfaces']},{'b','c'})
        before=self.b.snapshot()
        self.b.network.nodes['root'].name='changed'
        self.b.modules.instances[('c','probe')].state['value']='independent'
        merged=merge_records(self.b.snapshot(),records)
        self.assertEqual(self.entry(merged,'root')['name'],self.entry(before,'root')['name'])
        self.assertEqual(self.entry(merged,'c')['modules']['probe']['state']['value'],'independent')

    async def test_bound_agent_without_context_port_fails_before_module_changes(self):
        self.b.agents['b']['session_id']='missing-port'
        async def owner(ctx,activation):
            async with ctx.network.lock_nodes(['b']):raise AssertionError('must not enter')
            return ComponentResult()
        self.handlers['root']=owner
        with self.assertRaisesRegex(RuntimeError,'context capture port'):await self.b.modules.call('root','probe','run')
        self.assertEqual(self.b.modules.instances[('b','probe')].state['value'],'old')

    async def test_commit_waits_for_another_groups_cursor_preparation(self):
        ready,finish=asyncio.Event(),asyncio.Event()
        capturing,prepared,finish_prepare,finish_other=(asyncio.Event() for _ in range(4))
        self.b.agents['b']['session_id']='session-b';self.b.agents['c']={'session_id':'session-c'}
        calls=[]
        class Port:
            async def capture(_,bindings):
                calls.append(set(bindings))
                if set(bindings)=={'c'} and calls.count({'c'})==1:
                    capturing.set();await finish_prepare.wait()
                return {node:dict(adapter='test',session_id=session,event_count=1) for node,session in bindings.items()}
        self.b.context_port=Port()
        async def first():
            async with self.b.node_locks.transaction('root',['b'],strength=1,channels=['red']):
                self.b.network.nodes['b'].name='first committed';ready.set();await finish.wait()
        async def second():
            async with self.b.node_locks.transaction('root',['c'],strength=1,channels=['red']):
                self.b.network.nodes['c'].name='second committed';prepared.set();await finish_other.wait()
        first_task=asyncio.create_task(first());await ready.wait()
        second_task=asyncio.create_task(second());await capturing.wait();finish.set()
        await asyncio.sleep(.01);self.assertFalse(first_task.done())
        finish_prepare.set();await prepared.wait();await asyncio.wait_for(first_task,1)
        self.assertEqual(self.entry(self.b.store.latest(),'b')['name'],'first committed')
        self.assertEqual(self.entry(self.b.store.latest(),'c')['name'],'c')
        finish_other.set();await asyncio.wait_for(second_task,1)
        self.assertEqual(self.entry(self.b.store.latest(),'c')['name'],'second committed')


if __name__=='__main__':unittest.main()
