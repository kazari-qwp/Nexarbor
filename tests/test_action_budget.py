"""Period budgets and atomic world actions; no paid model calls."""
import unittest
import test_npc_world
import test_event_trigger_components

class GenericBudgetTests(unittest.TestCase):
    case=test_event_trigger_components.ComponentTests.case
    def test_independent_node_config_reset_snapshot_and_revocation(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);add(b,'worker')
            budget=b.modules.mount('worker','action.budget',dict(capacity=5,default_cost=2,costs={'read':0,'heavy':4}))
            assert budget.status(period='first')['remaining']==5
            assert budget.charge(action='heavy',period='first')['remaining']==1
            for _ in range(2):
                try:budget.charge(action='other',period='first')
                except ValueError as e:assert '需要2，剩余1/5' in str(e)
                else:raise AssertionError('overspent')
            assert budget.charge(action='read',period='first')['remaining']==1
            b.dispatch('save',{});b.close();b=Backend(folder)
            try:
                budget=b.modules.get('worker','action.budget')
                assert budget.status(period='first')['remaining']==1
                assert budget.status(period='second')['remaining']==5
                assert budget.status(period='first')['remaining']==1 # A query cannot refill it.
                assert budget.charge(action='other',period='second')['remaining']==3
                b.modules.unmount('worker','action.budget')
                try:budget.charge(action='read',period='second')
                except PermissionError:pass
                else:raise AssertionError('unmounted budget accepted')
            finally:b.close()
        """,'action_budget')

class TownBudgetTests(unittest.TestCase):
    case=test_npc_world.WorldTests.case

    def test_move_work_talk_zero_balance_and_free_memory_and_queries(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter';other='world/npc/wanderer'
            try:
                presence(b,actor,address('shop'));presence(b,other,address('forest'))
                # Run these tools INSIDE the actual signal Agent graph, while its native loop waits.
                def during(who):
                    moved=use(actor,address('forest'),'move_here')['items'][0]['result']
                    assert moved['action_budget']['cost']==3 and moved['action_budget']['remaining']==7
                    assert '本地：名称：树林' in '\n'.join(app.input_tail(actor))
                    assert any(v['tool']=='chop' for v in instance(b,actor,'tools.assembly').aliases.values())
                    cut=use(actor,business('forest'),'chop')['items'][0]['result']
                    assert cut['action_budget']['remaining']==1
                    said=use(actor,other,'talk',dict(content='树里有怪东西'))['items'][0]['result']
                    assert said['action_budget']['remaining']==0
                    snapshot=person(b,actor).state['inventory'].copy()
                    for _ in range(2):
                        try:use(actor,business('forest'),'chop')
                        except ValueError as error:assert '需要6，剩余0/10' in str(error)
                        else:raise AssertionError('exhausted action ran')
                    assert person(b,actor).state['inventory']==snapshot
                    assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==0
                    app.invoke(actor,'datanet_memory_write',dict(content='今天的行动已完成'))
                    assert app.invoke(actor,'datanet_memory_read',{})
                    app.event(actor,'agent/pre-step',{})
                    assert '行动值：0/10' in '\n'.join(app.input_tail(actor))
                port.during=during
                result=app.invoke('root','world_run_npc',dict(target=actor))
                assert result['pulse']['reports'][0]['returned'] and not port.conclusions,result
                assert len(person(b,other).state['inbox'])==1
                port.during=None
                app.invoke('root','world_run_npc',dict(target=actor))
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==10
            finally:stop(app,b)
        """)

    def test_failed_effect_rolls_back_budget_inventory_and_topology(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                begin(actor)
                events=instance(b,address('smithy'),'probability.events');original=events.config['events']
                events.config['events']=[dict(id='bad',actions=['move_here'],probability=1,max_occurrences=1,text='bad',effects=[dict(item='gold',quantity=-1)])]
                try:use(actor,address('smithy'),'move_here')
                except ValueError:pass
                else:raise AssertionError('bad effect accepted')
                assert person(b,actor).state['place']==address('mine')
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==10
                assert not events.state['counts']
                events.config['events']=original
                use(actor,address('smithy'),'move_here')
                a=person(b,actor).state;a['coins']=1
                try:use(actor,business('smithy'),'repair',dict(item='pickaxe'))
                except ValueError:pass
                else:raise AssertionError('unfunded repair accepted')
                assert a['coins']==1 and app.invoke(actor,'world_look',{})['action_budget']['remaining']==7
                a['coins']=4;use(actor,business('smithy'),'repair',dict(item='pickaxe'))
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==6
                assert use(actor,business('smithy'),'local_info',read=True)['items'][0]['result']['action_budget']['cost']==0
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==6
            finally:stop(app,b)
        """)

    def test_concurrent_calls_share_one_budget_and_failed_calls_do_not_send(self):
        self.case(r"""
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner';other='world/npc/miner2'
            try:
                begin(actor);assembly=instance(b,actor,'tools.assembly');assembly.assemble()
                tool=next(k for k,v in assembly.aliases.items() if v['tool']=='talk' and v['target']==other)
                def send(i):
                    try:app.invoke(actor,tool,dict(content='hello '+str(i)));return True
                    except ValueError as error:assert '行动值不足' in str(error);return False
                with ThreadPoolExecutor(max_workers=6) as workers:results=list(workers.map(send,range(12)))
                messages=person(b,other).state['inbox']
                assert sum(results)==10 and len(messages)==10
                assert len({v['id'] for v in messages})==10
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==0
                assert instance(b,other,'action.budget').status(period=tick(b))['remaining']==10
            finally:stop(app,b)
        """)

    def test_same_tick_cold_restore_does_not_refill_budget(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                begin(actor);use(actor,address('smithy'),'move_here');use(actor,'world/npc/smith','talk',dict(content='save'))
                b.dispatch('save',{});saved_tick=tick(b)
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert tick(b)==saved_tick and app.invoke(actor,'world_look',{})['action_budget']['remaining']==6
                begin(actor,'next-period')
                assert app.invoke(actor,'world_look',{})['action_budget']['remaining']==10
                template=instance(b,business('hospital'),'world.birth').config['child_template']['actor_modules']
                assert template['action.budget']['config']['capacity']==10 and 'event.trigger' in template
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
