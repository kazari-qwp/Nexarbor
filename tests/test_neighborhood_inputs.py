"""Agent-local collection and direct graph tools; no model APIs."""
import unittest
import test_npc_world

class NeighborhoodTests(unittest.TestCase):
    case=test_npc_world.WorldTests.case

    def test_information_is_opt_in_projected_and_collector_only(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner';smith='world/npc/smith'
            try:
                collector=instance(b,actor,'information.collector')
                report=collector.collect();items={x['node_id']:x for x in report['items']}
                assert items[address('mine')]['label']=='本地' and len(items[address('mine')]['path'])==2
                assert items[address('smithy')]['label']=='相邻' and len(items[address('smithy')]['path'])==3
                assert business('mine') not in items and not port.calls
                assert b.network.nodes[business('mine')].get_information({}) is None
                try:b.network.nodes[address('mine')].get_information({})
                except PermissionError:pass
                else:raise AssertionError('provider accepted a direct call')
                presence(b,actor,address('smithy'))
                report=collector.collect();items={x['node_id']:x for x in report['items']}
                assert items[smith]['fields']=={'姓名':'老锤','性别':'male'}
                assert not any('background' in str(x) or 'coins' in str(x) for x in items.values())
                assert 'get_information' not in b.network.nodes[smith].tools
                b.modules.unmount(address('smithy'),'information.provider')
                assert address('smithy') not in {x['node_id'] for x in collector.collect()['items']}
            finally:stop(app,b)
        """)

    def test_standalone_tool_assembly_direct_move_and_next_tick_refresh(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                collector=instance(b,actor,'information.collector');assembler=instance(b,actor,'tools.assembly')
                collector.collect();assembler.assemble();assert not port.calls
                aliases=dict(assembler.aliases)
                assert any(v['tool']=='mine' for v in aliases.values())
                assert not any(v['tool']=='repair' for v in aliases.values())
                assert not any(v['tool']=='move_here' and v['target']==address('mine') for v in aliases.values())
                move=next(k for k,v in aliases.items() if v['target']==address('smithy') and v['tool']=='move_here')
                assert '铁匠铺' in app.state(actor)['dynamic'][move]['description']
                begin(actor)
                result=app.invoke(actor,move,{})
                assert result['items'][0]['result']==dict(arrived=address('smithy'),tick_finished=True)
                assert len(port.conclusions)==1 and assembler.aliases==aliases
                assert '本地：名称：矿坑' in '\n'.join(app.input_tail(actor))
                old=next(k for k,v in aliases.items() if v['tool']=='mine')
                try:app.invoke(actor,old,{})
                except PermissionError:pass
                else:raise AssertionError('stale tool retained authority')
                b.dispatch('node_activity_end',dict(target=actor,signal_id='fixture',status='completed'))
                result=app.invoke('root','world_run_npc',dict(target=actor))
                steps=result['pulse']['reports'][0]['deliveries'][1]['value']['responders'][0]['steps']
                assert [s['tool'] for s in steps]==['collect_information','assemble_tools','run_agent']
                assert '本地：名称：铁匠铺' in '\n'.join(app.input_tail(actor))
                assert any(v['tool']=='repair' for v in assembler.aliases.values())
                assert old not in app.state(actor)['dynamic']
                assert len(port.calls)==1
            finally:stop(app,b)
        """)

    def test_live_contact_revocation_definition_change_and_unmount(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner';smith='world/npc/smith'
            try:
                presence(b,actor,address('smithy'));assembler=instance(b,actor,'tools.assembly');assembler.assemble()
                talk=next(k for k,v in assembler.aliases.items() if v['target']==smith and v['tool']=='talk')
                presence(b,smith,address('home2'));begin(actor)
                try:app.invoke(actor,talk,dict(content='no delivery'))
                except PermissionError:pass
                else:raise AssertionError('departed NPC still reachable')
                assert not person(b,smith).state['inbox']
                repair=next(k for k,v in assembler.aliases.items() if v['tool']=='repair')
                b.network.nodes[business('smithy')].tool_definitions['repair']['parameters']['properties']['new']={'type':'string'}
                try:app.invoke(actor,repair,dict(item='pickaxe'))
                except PermissionError:pass
                else:raise AssertionError('stale schema accepted')
                b.modules.unmount(actor,'tools.assembly')
                assert not any(d['owner']=='capabilities/tool_assembly' for d in app.state(actor)['dynamic'].values())
                collector=instance(b,actor,'information.collector');collector.collect()
                b.modules.unmount(actor,'information.collector')
                assert not any('[周边信息]' in t for t in app.input_tail(actor))
                for fn in (collector.collect,assembler.assemble):
                    try:fn()
                    except PermissionError:pass
                    else:raise AssertionError('unmounted preparation method accepted')
                try:app.invoke(actor,repair,dict(item='pickaxe'))
                except PermissionError:pass
                else:raise AssertionError('unmounted alias accepted')
            finally:stop(app,b)
        """)

    def test_restore_and_child_receive_components_without_initial_movement(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                assert not instance(b,actor,'tools.assembly').aliases
                app.invoke('root','world_run_npc',dict(target=actor))
                assert any(v['tool']=='mine' for v in instance(b,actor,'tools.assembly').aliases.values())
                birth=instance(b,business('hospital'),'world.birth').config['child_template']['actor_modules']
                assert {'information.collector','information.provider','tools.assembly'}<=birth.keys()
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                assert not instance(b,actor,'tools.assembly').aliases
                app.invoke('root','world_run_npc',dict(target=actor))
                assert any(v['tool']=='mine' for v in instance(b,actor,'tools.assembly').aliases.values())
                assert '本地：名称：矿坑' in '\n'.join(app.input_tail(actor))
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
