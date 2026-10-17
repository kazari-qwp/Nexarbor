"""Real LangGraph runtime: activated-branch joins, parallel effects and event wiring."""
import unittest
import test_event_trigger_components
import test_npc_world

class ExecutionTests(unittest.TestCase):
    case=test_event_trigger_components.ComponentTests.case

    def test_nested_parallel_conditional_join_and_fresh_state(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});executor=app.plugins['capabilities/module_execution']
            def call(id,**arguments):return dict(type='call',id=id,operation=id,arguments=arguments)
            graph=dict(type='sequence',steps=[call('choose',value={'$ref':'/event/payload/choice'}),dict(type='parallel',steps=[
                dict(type='sequence',steps=[call('old'),call('old_extra')]),
                dict(type='branch',select={'$ref':'/results/choose/value'},cases={'new':call('new')},default=call('fallback'))
            ]),call('publish',old={'$ref':'/results/old/value'})])
            async def scenario(choice):
                started=set();both=asyncio.Event();finished=[]
                async def choose(c,value):return value
                async def work(label):
                    started.add(label)
                    if len(started)==2:both.set()
                    await asyncio.wait_for(both.wait(),1)
                    await asyncio.sleep(.01 if label=='old' else .03)
                    finished.append(label);return label
                async def old(c):return await work('old')
                async def old_extra(c):assert 'old' in finished;finished.append('old_extra')
                async def new(c):return await work('new')
                async def fallback(c):return await work('fallback')
                async def publish(c,old):
                    assert old=='old' and len(finished)==3 and 'old_extra' in finished,finished
                    return 'published'
                operations=dict(choose=choose,old=old,old_extra=old_extra,new=new,fallback=fallback,publish=publish)
                result=await executor.execute('root',graph,operations,dict(type='move',channels=[],payload={'choice':choice}))
                keys=set(result['results']);assert ('new' in keys)==(choice=='new')
                assert ('fallback' in keys)==(choice!='new') and result['results']['publish']['value']=='published'
            try:
                asyncio.run(scenario('new'));asyncio.run(scenario('unknown'))
                # The graph must be rejected before any operation runs.
                try:asyncio.run(executor.execute('root',graph,{},{}))
                except PermissionError:pass
                else:raise AssertionError('ungranted operation ran')
            finally:stop(app,b)
        """)

    def test_unbind_revokes_later_operations_and_other_binding_survives(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});trigger=app.plugins['capabilities/event_trigger'];calls=[]
            async def first(c):calls.append('first');trigger.unbind('root',binding='first')
            async def forbidden(c):raise AssertionError('revoked operation ran')
            graph=dict(type='sequence',steps=[dict(type='call',id=n,operation=n,arguments={}) for n in ['first','forbidden']])
            rule=dict(id='main',event='demo',channels=['scene'],where={'/payload/allowed':True},graph='main')
            trigger.bind('root',[rule],{'main':graph},dict(first=first,forbidden=forbidden),binding='first')
            async def other(c):calls.append('other')
            trigger.bind('root',[dict(rule,id='other',event='other',channels=[],where={})],{'main':dict(type='call',id='other',operation='other',arguments={})},dict(other=other),binding='second')
            async def run():
                for channels,payload in [(['wrong'],{'allowed':True}),(['scene'],{}),(['scene'],{'allowed':False})]:
                    result=await trigger.emit('root',dict(type='demo',channels=channels,payload=payload));assert result['matched']==0
                try:await trigger.emit('root',dict(type='demo',channels=['scene'],payload={'allowed':True}))
                except RuntimeError as e:assert 'revoked' in str(e)
                else:raise AssertionError('revoked graph continued')
                await trigger.emit('root',dict(type='other',channels=[],payload={}))
                assert calls==['first','other']
            try:asyncio.run(run())
            finally:stop(app,b)
        """)

    def test_parallel_timeout_tracks_every_unfinished_sync_worker(self):
        self.case(r"""
        import threading
        from langgraph.graph import StateGraph
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});trigger=app.plugins['capabilities/event_trigger'];executor=app.plugins['capabilities/module_execution'];add(b,'worker');link(b,'root','worker')
            releases=[threading.Event(),threading.Event()];started=[threading.Event(),threading.Event()]
            def one(c):started[0].set();releases[0].wait(3);return 1
            def two(c):started[1].set();releases[1].wait(3);return 2
            graph=dict(type='parallel',steps=[dict(type='call',id=name,operation=name,arguments={}) for name in ['one','two']])
            trigger.bind('worker',[dict(id='work',event='signal/received',channels=['tick'],where={},graph='work')],{'work':graph},dict(one=one,two=two))
            async def run():
                try:
                    report=await b.signals.propagate(Signal('root',['tick'],2,node_timeout_seconds=.2))
                    assert report['status']=='timed_out' and all(e.is_set() for e in started)
                    assert len(executor.workers['worker'])==2
                    releases[0].set()
                    for _ in range(100):
                        if len(executor.workers['worker'])==1:break
                        await asyncio.sleep(.002)
                    assert len(executor.workers['worker'])==1
                    report=await b.signals.propagate(Signal('root',['tick'],2));assert report['status']=='failed'
                finally:
                    for release in releases:release.set()
                    await asyncio.gather(*(task for tasks in executor.workers.values() for task in tasks),return_exceptions=True)
                report=await b.signals.propagate(Signal('root',['tick'],2));assert report['status']=='completed'
                await b.signals.close()
            try:asyncio.run(run())
            finally:stop(app,b)
        """)

    def test_mounted_event_configuration_async_bus_restore_and_unmount(self):
        self.case(r"""
        from datanet.core.text_node import TextFileNode
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);app=Application(b,Port(),{});b.modules.bind(app)
            b.network.add_node(TextFileNode('timer','Timer','text',b.directory/'timer.md'))
            clock=b.modules.mount('timer','clock.text',dict(channels=['unused'],slots=['morning'],format='day {day}'),dict(tick=-1))
            graph=dict(type='call',id='advance',operation='advance',arguments=dict(signal_id={'$ref':'/event/payload/id'}))
            config=dict(operations={'advance':dict(module='clock.text',method='advance')},rules=[dict(id='advance',event='demo/tick',channels=[],where={'/payload/ready':True},graph='tick')],graphs={'tick':graph})
            b.modules.mount('timer','event.trigger',config)
            b.modules.bind(app) # Rebinding must not duplicate ordinary-event listeners.
            try:
                app.emit('demo/tick',id='a',ready=False);assert clock.state['tick']==-1
                app.emit('demo/tick',id='a',ready=True);assert clock.state['tick']==0
                asyncio.run(app.emit_async('demo/tick',id='b',ready=True));assert clock.state['tick']==1
                b.dispatch('save',{})
            finally:stop(app,b)
            b=Backend(folder);app=Application(b,Port(),{});b.modules.bind(app)
            try:
                clock=b.modules.get('timer','clock.text');assert clock.state['tick']==1
                asyncio.run(app.emit_async('demo/tick',id='c',ready=True));assert clock.state['tick']==2
                b.modules.unmount('timer','event.trigger')
                app.emit('demo/tick',id='d',ready=True);assert clock.state['tick']==2
                # Removing the general event trigger must not remove clock's own signal binding.
                assert 'timer' in b.signals.bindings
            finally:stop(app,b)
        """,'node_clock')

class TownEventTests(unittest.TestCase):
    case=test_npc_world.WorldTests.case

    def test_successful_movement_event_runs_parallel_preparation_then_context(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            def step(id):return dict(type='call',id=id,operation=id,arguments={})
            config=dict(operations={
                'info':dict(module='information.collector',method='collect'),
                'tools':dict(module='tools.assembly',method='assemble'),
                'context':dict(module='agent.signal',method='assemble')
            },rules=[dict(id='arrived',event='node/tool-invoked',channels=[],where={'/payload/actor':actor,'/payload/tool':'move_here'},graph='refresh')],graphs={
                'refresh':dict(type='sequence',steps=[dict(type='parallel',steps=[step('info'),step('tools')]),step('context')])
            })
            b.modules.unmount(actor,'event.trigger')
            b.modules.mount(actor,'event.trigger',config)
            try:
                instance(b,actor,'information.collector').collect();instance(b,actor,'tools.assembly').assemble();begin(actor)
                assert '本地：名称：矿坑' in '\n'.join(app.input_tail(actor))
                try:use(actor,address('hospital'),'move_here')
                except PermissionError:pass
                else:raise AssertionError('nonadjacent movement accepted')
                assert '本地：名称：矿坑' in '\n'.join(app.input_tail(actor))
                use(actor,address('smithy'),'move_here')
                assert '本地：名称：铁匠铺' in '\n'.join(app.input_tail(actor))
                assert '本地：名称：矿坑' not in '\n'.join(app.input_tail(actor))
                assert any(v['tool']=='repair' for v in instance(b,actor,'tools.assembly').aliases.values())
                assert not port.calls and not port.conclusions
                assert actor in b.signals.bindings
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
