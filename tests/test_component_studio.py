"""Real work-copy verification and core assembly, with no model calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from datanet.core.backend import Backend
from datanet.core.tool_access import invoke_tool

ROOT=Path(__file__).resolve().parents[1]
CLOCK='''from datanet.studio.contract import StudioModule
class Module(StudioModule):
    def setup(self):
        self.state.setdefault('tick',-1)
        self.state.setdefault('signal_id','')
    def on_signal(self,context):
        if self.state['signal_id']==context.signal.signal_id:return dict(self.state)
        self.state['tick']+=1
        self.state['signal_id']=context.signal.signal_id
        tick=self.state['tick'];slots=self.config['slots']
        self.node.write('content',self.config['format'].format(day=tick//len(slots)+1,slot=slots[tick%len(slots)],tick=tick))
        return dict(self.state)
'''

class StudioTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/studio-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.app=Backend(self.temp.name);self.studio=self.app.studio
    def tearDown(self):self.app.close();self.temp.cleanup()
    def save(self,w,file,text):
        old=self.studio.read({'id':w['id']})['files'].get(file,'')
        return self.studio.save(dict(id=w['id'],file=file,content=text,expected=hashlib.sha256(old.encode()).hexdigest()))
    def check(self,w,timeout=15):
        job=self.studio.validate(dict(id=w['id'],timeout=timeout));deadline=time.monotonic()+timeout+12
        while job['status']=='running' and time.monotonic()<deadline:time.sleep(.05);job=self.studio.job({'job':job['id']})
        self.assertNotEqual(job['status'],'running',job);return job
    def test_legacy_clock_fails_then_migrated_clock_wraps_and_restores(self):
        w=self.studio.create({'sample':'town_clock'})
        self.assertIn('legacy.py',''.join(w['references']))
        self.assertEqual(self.check(w)['status'],'failed')
        self.save(w,'module.py',CLOCK)
        result=self.check(w);self.assertEqual(result['status'],'passed',result['log'])
        self.studio.publish({'id':w['id']});self.studio.town({})
        self.studio.mount(dict(node='town/time',module='town.clock'))
        result=self.app.dispatch('studio_pulse',{'cycles':6})
        self.assertEqual(self.app.network.nodes['town/time'].read({'method':'key','key':'content'}).items[0]['content'],'第2天-早上')
        self.assertEqual(self.app.modules.get('town/time','town.clock').state['tick'],5)
        self.app.close();self.app=Backend(self.temp.name);self.studio=self.app.studio
        self.assertEqual(self.app.modules.get('town/time','town.clock').state['tick'],5)
        self.app.dispatch('studio_pulse',{'cycles':1})
        self.assertIn('中午',self.app.network.nodes['town/time'].read({'method':'key','key':'content'}).items[0]['content'])
    def test_published_tool_requires_channels_and_strength(self):
        w=self.studio.create({'sample':'blank'})
        spec=json.loads(w['files']['module.json'])
        spec['tools']=[dict(name='look',description='查看计数',parameters={'type':'object','properties':{},'additionalProperties':False},channels=['town.local'])]
        self.save(w,'module.json',json.dumps(spec));self.save(w,'module.py',w['files']['module.py']+'\n    def look(self):return dict(self.state)\n')
        result=self.check(w);self.assertEqual(result['status'],'passed',result['log'])
        self.studio.publish({'id':w['id']});self.studio.town({});self.studio.mount(dict(node='town/smith',module='example.counter'))
        self.assertEqual(invoke_tool(self.app.network,'town/miner','town/smith','look',{},strength=1).status,'forbidden')
        self.assertEqual(invoke_tool(self.app.network,'town/miner','town/smith','look',{},strength=2).status,'ok')
        self.app.network.nodes['town/miner'].interfaces=[]
        self.assertEqual(invoke_tool(self.app.network,'town/miner','town/smith','look',{},strength=3).status,'forbidden')
        with self.assertRaises(ValueError):self.studio.publish({'id':w['id']})
    def test_modified_source_cannot_reuse_an_old_validation(self):
        w=self.studio.create({'sample':'blank'});self.assertEqual(self.check(w)['status'],'passed')
        self.save(w,'module.py',w['files']['module.py']+'\n# changed\n')
        with self.assertRaises(ValueError):self.studio.publish({'id':w['id']})
        with self.assertRaises(ValueError):self.save(w,'../../escape.py','pass')
        with self.assertRaises(PermissionError):self.save(w,'AGENTS.md','replace')
        with self.assertRaises(ValueError):self.studio.save(dict(id=w['id'],file='module.py',expected='stale',content='pass'))
    def test_validation_deadline_stops_infinite_python(self):
        w=self.studio.create({'sample':'blank'})
        self.save(w,'module.py','while True: pass\n')
        result=self.check(w,1);self.assertEqual(result['status'],'timeout')
        self.assertNotIn(result['id'],self.studio.processes)
    def test_invalid_graph_keeps_current_network(self):
        self.studio.town({});before=self.studio.state()['live']['document']
        invalid=copy.deepcopy(before);invalid['network']['version']=6
        result=self.studio.graph_validate({'document':invalid});self.assertFalse(result['valid'])
        with self.assertRaises(ValueError):self.studio.apply(dict(document=invalid,base_commit=self.app.store.head))
        self.assertEqual(self.studio.state()['live']['document'],before)
    def test_ready_town_modules_publish_fork_and_restore_together(self):
        for sample in ['ready_clock','ready_savepoint']:
            workspace=self.studio.create({'sample':sample});result=self.check(workspace)
            self.assertEqual(result['status'],'passed',result['log'])
            release=self.studio.publish({'id':workspace['id']})
            view=self.studio.release_read({'module':release['id']})
            self.assertTrue(view['readOnly']);self.assertIn('class Module',view['files']['module.py'])
            fork=self.studio.fork({'module':release['id']})
            self.assertEqual(fork['files']['module.py'],view['files']['module.py'])
        self.app.dispatch('studio_town',{})
        for node,module in [('town/time','town.clock'),('town/save','town.savepoint')]:
            self.app.dispatch('studio_mount',dict(node=node,module=module))
        self.app.dispatch('studio_pulse',{'cycles':6})
        self.assertEqual(self.app.modules.get('town/save','town.savepoint').state['count'],6)
        self.assertEqual(self.app.modules.get('town/time','town.clock').state['tick'],5)
        self.assertGreaterEqual(self.app.store.stats()['full_snapshot_count'],1)
        self.app.close();self.app=Backend(self.temp.name);self.studio=self.app.studio
        self.app.dispatch('studio_pulse',{'cycles':1})
        self.assertEqual(self.app.modules.get('town/save','town.savepoint').state['count'],7)
    def test_missing_dependency_and_module_source_helper(self):
        w=self.studio.create({'sample':'blank'})
        self.save(w,'helpers.py','VALUE = 1\n')
        self.save(w,'module.py',w['files']['module.py'].replace('from datanet.studio.contract import StudioModule','from datanet.studio.contract import StudioModule\nfrom .helpers import VALUE'))
        result=self.check(w);self.assertEqual(result['status'],'passed',result['log'])
        spec=json.loads(w['files']['module.json']);spec['requires']=['missing.module']
        self.save(w,'module.json',json.dumps(spec));self.assertEqual(self.check(w)['status'],'passed')
        with self.assertRaisesRegex(ValueError,'dependencies'):self.studio.publish({'id':w['id']})
