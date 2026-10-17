"""Successful-action events and deferred one-time opening inputs."""
import unittest
import test_npc_world

class EventTests(unittest.TestCase):
    case=test_npc_world.WorldTests.case

    def test_opening_once_no_wakeup_restart_and_pending_delivery(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                assert not port.calls and not instance(b,actor,'input.opening').state
                app.invoke('root','world_run_npc',dict(target=actor))
                source=b.network.nodes[actor].inputs.snapshot()['core:execution'];opening=source['inputs'][0]
                assert opening['text'].count('你的镐子坏了')==1 and opening['status']=='delivered'
                app.invoke('root','world_run_npc',dict(target=actor))
                entries=b.network.nodes[actor].inputs.snapshot()['core:execution']['inputs']
                assert len(entries)==2 and '初始处境' not in entries[1]['text']
                assert 'initial_goal' not in str(b.network.get_metadata(actor))
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                app.invoke('root','world_run_npc',dict(target=actor))
                assert '初始处境' not in b.network.nodes[actor].inputs.snapshot()['core:execution']['inputs'][-1]['text']
                # Simulate a crash after the atomic preparation, before host delivery.
                other='world/npc/lin';e=dict(id='prepared-before-crash',text='first task',delivery='followup')
                prepared=b.dispatch('opening_input_prepare',dict(target=other,event=e))
                assert '初始处境' in prepared['text']
                assert b.network.nodes[other].inputs.pending()
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                events=b.network.nodes[other].inputs.snapshot()['core:execution']['inputs']
                assert len(events)==1 and events[0]['id']=='prepared-before-crash'
                assert instance(b,other,'input.opening').state['prepared']
            finally:stop(app,b)
        """)

    def test_events_independent_caps_dedup_reward_and_restart(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/miner'
            try:
                m=instance(b,business('mine'),'probability.events')
                m.config['events']=[dict(id='once',actions=['mine'],probability=1,max_occurrences=1,text='gold',effects=[dict(item='gold',quantity=1)]),dict(id='never',actions=['mine'],probability=0,max_occurrences=None,text='never'),dict(id='always',actions=['mine'],probability=1,max_occurrences=None,text='wind')]
                m.state['counts']={};m.state['draws']={}
                begin(actor)
                try:use(actor,business('mine'),'mine')
                except Exception:pass
                else:raise AssertionError('broken pickaxe worked')
                assert not m.state['draws'] and not m.state['counts']
                person(b,actor).state['inventory']['pickaxe']=5
                value=use(actor,business('mine'),'mine')['items'][0]['result']
                assert [e['text'] for e in value['events']]==['gold','wind']
                assert person(b,actor).state['inventory']['gold']==1
                record=next(iter(m.state['draws']))
                assert len(m.draw(record,'mine',lambda _:(_ for _ in ()).throw(AssertionError('reward repeated'))))==2
                # A different resident shares the location-wide one-occurrence cap.
                other='world/npc/woodcutter';presence(b,other,address('mine'));person(b,other).state['inventory']['pickaxe']=5
                begin(other);value=use(other,business('mine'),'mine')['items'][0]['result']
                assert [e['text'] for e in value['events']]==['wind']
                assert person(b,other).state['inventory'].get('gold',0)==0
                assert m.state['counts']=={'once':1,'always':2}
            finally:stop(app,b)
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                m=instance(b,business('mine'),'probability.events')
                assert m.state['counts']=={'once':1,'always':2} and len(m.state['draws'])==2
                assert person(b,actor).state['inventory']['gold']==1
                begin(actor,'after-restart');value=use(actor,business('mine'),'mine')['items'][0]['result']
                assert [e['text'] for e in value['events']]==['wind']
            finally:stop(app,b)
        """)

    def test_configured_actions_exist_and_marriage_wait_is_not_celebrated(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            try:
                for m in b.modules.find('probability.events'):
                    assert all(action in m.node.tools for e in m.config['events'] for action in e['actions']),m.node.node_id
                node=business('civil_registry');m=instance(b,node,'probability.events')
                lin='world/npc/lin';yue='world/npc/yue'
                presence(b,lin,address('civil_registry'));presence(b,yue,address('civil_registry'));begin(lin);begin(yue)
                value=use(lin,node,'marry',dict(partner=yue))['items'][0]['result']
                assert value.get('waiting_for')==yue and 'married' not in value and not m.state['counts'] and not m.state['draws'],value
                value=use(yue,node,'marry',dict(partner=lin))['items'][0]['result']
                assert value['married']==lin and len(value['events'])==1 and m.state['counts']==dict(flowers=1)
            finally:stop(app,b)
        """)

    def test_effect_failure_rolls_back_action_counters_and_rewards(self):
        self.case(r"""
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(folder);port=WorldPort();app=Application(b,port,dict(rootNetwork='small_town'));app.bind_session('root-session')
            actor='world/npc/woodcutter'
            try:
                m=instance(b,business('forest'),'probability.events')
                m.config['events']=[dict(id='bad',actions=['chop'],probability=1,max_occurrences=1,text='reward',effects=[dict(item='gold',quantity=1),dict(item='gold',quantity=-1)])]
                begin(actor);before=json.loads(json.dumps(person(b,actor).state));seed=m.state['seed']
                try:use(actor,business('forest'),'chop')
                except Exception:pass
                else:raise AssertionError('invalid effect accepted')
                assert person(b,actor).state==before and m.state==dict(seed=seed,counts={},draws={})
            finally:stop(app,b)
        """)

if __name__=='__main__':unittest.main()
