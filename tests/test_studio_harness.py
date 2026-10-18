"""Native session protocol regression, no model or external service calls."""
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'adapters/harness/studio'))
from remote import HarnessRemote,maker_prefix

class NativeSessionTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/studio-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.folder=Path(self.temp.name)
        (self.folder/'AGENTS.md').write_text('Use file tools, then return for host validation.',encoding='utf-8')
        (self.folder/'MODULE_GUIDE.md').write_text('Module contract',encoding='utf-8')
        self.checks=0;self.cancelled=[]
        def validate(p):
            self.checks+=1
            return dict(id=str(self.checks),workspace='work',status='failed' if self.checks==1 else 'passed',log='host test: wrong count')
        self.studio=SimpleNamespace(root=self.folder,folder=lambda id:self.folder,validate=validate,job=lambda p:dict(status='passed'),cancel=lambda p:self.cancelled.append(p))
        self.remote=HarnessRemote(self.studio);self.remote.authority='127.0.0.1:12345';self.remote.home=self.folder
    def tearDown(self):self.remote.close();self.temp.cleanup()
    def test_page_uses_projection_cursor_and_preserves_native_reason(self):
        calls=[]
        def rpc(method,args,timeout=8):
            calls.append((method,args))
            if method=='session/projections':return dict(asOfSeq=42,values={'tokenUsage':{'outputTokens':7}})
            return dict(records=[dict(type='event',event=dict(type='turn/end',seq=41,data={'reason':{'kind':'completed'}}))])
        self.remote.rpc=rpc;self.remote.jobs['job']=dict(session_id='native',status='running',phase='coding',after=40)
        result=self.remote.read({'task':'job'})
        self.assertEqual(calls[-1][1]['request']['throughSeq'],42)
        self.assertEqual(result['native_reason'],'completed');self.assertEqual(result['usage']['outputTokens'],7)
    def test_failed_host_validation_returns_to_same_native_session(self):
        calls=[];sequence=0
        def rpc(method,args,timeout=8):
            nonlocal sequence
            calls.append((method,args))
            if method=='session/create':return {'sessionId':'native-maker'}
            if method=='session/prompt':sequence+=1;return {}
            if method=='session/projections':return {'asOfSeq':sequence,'values':{}}
            if method=='session/page':return {'records':[dict(type='event',event=dict(type='turn/end',seq=sequence,data={'reason':{'kind':'completed'}}))]}
            return {}
        self.remote.rpc=rpc
        task=self.remote.start(dict(id='work',requirement='Migrate the clock',timeout=10))
        deadline=time.monotonic()+8
        while self.remote.jobs[task['id']]['status']=='running' and time.monotonic()<deadline:time.sleep(.05)
        job=self.remote.jobs[task['id']];self.assertEqual(job['status'],'completed',job);self.assertEqual(job['repairs'],1)
        prompts=[a['request'] for m,a in calls if m=='session/prompt']
        self.assertEqual(len(prompts),2);self.assertTrue(all(p['sessionId']=='native-maker' for p in prompts))
        self.assertIn('wrong count',prompts[1]['content'][0]['text'])
        self.assertEqual(self.remote.status()['jobs'][0]['session_id'],'native-maker')
    def test_cancel_only_owned_session_even_if_native_connection_fails(self):
        self.remote.jobs['job']=dict(session_id='owned',status='running')
        with patch.object(self.remote,'rpc',side_effect=RuntimeError('disconnected')) as rpc:
            with self.assertRaises(RuntimeError):self.remote.cancel({'task':'job'})
            rpc.assert_called_once_with('session/cancel',{'request':{'sessionId':'owned'}})
        self.assertEqual(self.remote.jobs['job']['status'],'cancelled')
    def test_nonloopback_address_is_rejected_before_authentication(self):
        (self.folder/'.credentials.yaml').write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'loopback'):
            self.remote.connect({'authority':'example.com:1234','home':str(self.folder)})
    def test_fork_preserves_prefix_and_reports_only_new_usage(self):
        prefix=maker_prefix(self.folder)
        self.remote.sessions['source']=dict(workspace='work',prefix=prefix)
        calls=[];reads=0
        def rpc(method,args,timeout=8):
            nonlocal reads
            calls.append((method,args))
            if method=='session/fork':return {'sessionId':'forked'}
            if method=='session/projections':
                reads+=1;return dict(asOfSeq=40+reads,values={'tokenUsage':{'outputTokens':100 if reads==1 else 123}})
            if method=='session/page':return {'records':[]}
            return {}
        self.remote.rpc=rpc
        with patch('remote.threading.Thread.start'):
            task=self.remote.start(dict(id='work',requirement='Fix the first tick',fork_session='source'))
        result=self.remote.read({'task':task['id']})
        self.assertEqual(result['usage']['outputTokens'],23)
        self.assertEqual(result['usage_cumulative']['outputTokens'],123)
        self.assertEqual(result['source_session'],'source')
        self.assertIn(('session/fork',{'request':{'sessionId':'source'}}),calls)
        self.remote.cancel({'task':task['id']})
        (self.folder/'MODULE_GUIDE.md').write_text('changed contract',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'prefix'):
            self.remote.start(dict(id='work',requirement='Try again',fork_session='source'))

    def test_frontend_guide_and_dependencies_invalidate_history_prefix(self):
        initial=maker_prefix(self.folder)
        (self.folder/'FRONTEND_GUIDE.md').write_text('页面协议',encoding='utf-8')
        page=maker_prefix(self.folder)
        self.assertNotEqual(initial,page)
        dependencies=self.folder/'dependencies';dependencies.mkdir()
        (dependencies/'catalog.json').write_text('[]',encoding='utf-8')
        self.assertNotEqual(page,maker_prefix(self.folder))

    def test_new_task_refreshes_guides_before_comparing_history(self):
        self.studio.prepare_agent=lambda p:(self.folder/'AGENTS.md').write_text('当前规范',encoding='utf-8')
        self.remote.sessions['old']=dict(workspace='work',prefix=maker_prefix(self.folder))
        with self.assertRaisesRegex(ValueError,'prefix'):
            self.remote.start(dict(id='work',requirement='继续',resume_session='old'))
        self.assertEqual((self.folder/'AGENTS.md').read_text(encoding='utf-8'),'当前规范')

if __name__=='__main__':unittest.main()
