import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Rpc:
    def __init__(self,directory,profile=None,binary=False):
        env={**os.environ,'DATANET_PRODUCT_ROOT':str(ROOT),'DATANET_COMPONENT_ROOT':str(ROOT/'extensions/multi_agent'),'DATANET_COMPONENT_PROFILE':json.dumps(profile or {}),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'}
        args=[str(ROOT/'adapters/harness/runtime/backend/datanet-backend.exe')] if binary else [sys.executable,str(ROOT/'adapters/harness/backend/server.py')]
        self.process=subprocess.Popen([*args,str(directory)],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
    def call(self,name,**params):
        self.process.stdin.write(json.dumps({'id':1,'method':name,'params':params})+'\n');self.process.stdin.flush()
        while True:
            line=self.process.stdout.readline()
            if not line:raise RuntimeError(self.process.stderr.read())
            value=json.loads(line)
            if value.get('id')==1:return value
    def result(self,name,**params):
        r=self.call(name,**params)
        if 'error' in r:raise RuntimeError(r['error'])
        return r['result']
    def close(self):
        self.process.stdin.close();self.process.wait(timeout=10)
        stderr=self.process.stderr.read();self.process.stdout.close();self.process.stderr.close()
        if self.process.returncode:raise RuntimeError(stderr)
class ComponentsTests(unittest.TestCase):
    def test_core_without_harness(self):
        env={**os.environ,'PYTHONPATH':str(ROOT/'python'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','DATANET_COMPONENT_ROOT':str(ROOT/'extensions/multi_agent')}
        subprocess.run([sys.executable,'-c',"from datanet.core.component_registry import codecs,toolboxes; import sys; assert {'node','text_file','discussion_board','value'}<=codecs().keys(); assert 'local_data' in toolboxes(); assert 'config' not in sys.modules; assert not any(x.startswith('harness_components') for x in sys.modules)"],env=env,check=True)
    def test_node_toolbox_revocation(self):
        env={**os.environ,'PYTHONPATH':str(ROOT/'python'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','DATANET_COMPONENT_ROOT':str(ROOT/'extensions/multi_agent')}
        script='''
from datanet.core.component_registry import codecs,toolboxes,enabled_components
node=codecs()['value'].node_class('v','value','value',7)
node.toolboxes=['local_data']
toolboxes()['local_data'](node)
definition=dict(node.tool_definitions['write'])
enabled=enabled_components()
enabled.remove('capabilities/local_data')
assert node.invoke_tool('write',key='value',value=9).status=='forbidden'
assert node.read({'method':'key','key':'value'}).items[0]['value']==7
assert node.tool_definitions['write']==definition
enabled.add('capabilities/local_data')
assert node.invoke_tool('write',key='value',value=9).status=='ok'
assert node.read({'method':'key','key':'value'}).items[0]['value']==9
'''
        subprocess.run([sys.executable,'-c',script],env=env,check=True)
    def test_restored_toolbox_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            b=Rpc(directory)
            try:
                b.result('load_root_network',package='project_root')
                result=b.result('create_node',actor='root',child_id='value',node_spec={'type':'value','parameters':{'value':7},'toolboxes':['local_data'],'expose':['read','get_schema','write']},options={'allow_custom':True,'scope':'descendants'})
                self.assertEqual(result['status'],'ok',result)
            finally:b.close()
            b=Rpc(directory,{'capabilities/local_data':False})
            try:
                for tool,args,direction in [('read',{'request':{'method':'key','key':'value'}},'read'),('get_schema',{},'read'),('write',{'key':'value','value':9},'write')]:
                    result=b.result('invoke_tool',actor='root',target='root/value',tool=tool,arguments=args,strength=100)
                    self.assertEqual(result['status'],'forbidden',result)
                self.assertEqual(b.result('read',actor='root',target='root/value',request={'method':'key','key':'value'},strength=100)['items'][0]['value'],7)
                b.result('save')
            finally:b.close()
            b=Rpc(directory)
            try:
                result=b.result('invoke_tool',actor='root',target='root/value',tool='write',arguments={'key':'value','value':9},strength=100)
                self.assertEqual(result['status'],'ok',result)
            finally:b.close()
    def test_unplug_restore_state(self):
        with tempfile.TemporaryDirectory() as directory:
            b=Rpc(directory)
            try:
                b.result('load_root_network',package='project_root')
                group=b.result('create_network',preset='discussion_group',instance_id='persist',project='资料',rounds=1,actor='root',strength=100)
                self.assertEqual(group['status'],'ok',group)
                b.result('group_task',group_id='persist',task='保存该任务')
                b.result('bind_agent',target='root',kind='root',session_id='test-root',creator_node_id=None)
                feedback=b.result('report_feedback',actor='root',category='other',message='保存该反馈')
            finally:b.close()
            b=Rpc(directory,{'capabilities/discussion_group':False,'capabilities/problem_handling':False})
            try:
                info=b.result('recovery_info');self.assertEqual(info['groups'],{});self.assertEqual(info['feedback'],[])
                self.assertIn('unknown method',b.call('start_round',group_id='persist')['error'])
                self.assertGreater(b.result('ping')['nodes'],3)
                b.result('save')
            finally:b.close()
            b=Rpc(directory)
            try:
                info=b.result('recovery_info');self.assertEqual(info['groups']['persist']['task'],'保存该任务');self.assertEqual(info['feedback'][0]['id'],feedback['id'])
                b.result('start_round',group_id='persist')
            finally:b.close()
    def test_disable_node_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            b=Rpc(directory)
            try:
                b.result('load_root_network',package='project_root')
                b.result('write',actor='root',target='root/project',key='content',value='保留正文',strength=100)
                value=b.result('create_node',actor='root',child_id='value',node_spec={'type':'value','parameters':{'value':7}},options={'allow_custom':True,'scope':'descendants'})
                self.assertEqual(value['status'],'ok',value)
            finally:b.close()
            b=Rpc(directory,{'capabilities/text':False,'capabilities/value':False})
            try:
                self.assertIn('unknown method',b.call('text_bindings',actor='root')['error'])
                result=b.result('read',actor='root',target='root/project',request={'method':'key','key':'content'},strength=100)
                self.assertEqual(result['status'],'forbidden')
                result=b.result('read',actor='root',target='root/value',request={'method':'key','key':'value'},strength=100)
                self.assertEqual(result['status'],'forbidden')
                b.result('save')
            finally:b.close()
            b=Rpc(directory)
            try:
                self.assertEqual(b.result('query_text',actor='root',target='root/project',strength=100)['text'].split('\n',1)[1],'保留正文')
                self.assertEqual(b.result('read',actor='root',target='root/value',request={'method':'key','key':'value'},strength=100)['items'][0]['value'],7)
            finally:b.close()
    @unittest.skipUnless(os.environ.get('DATANET_TEST_BINARY')=='1','binary fixture is a separate invocation')
    def test_binary_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            b=Rpc(directory,binary=True)
            try:
                self.assertTrue(b.result('ping')['ok'])
                self.assertEqual(b.result('load_root_network',package='project_root')['status'],'ok')
                group=b.result('create_network',actor='root',preset='discussion_group',instance_id='binary',project_nodes=['root/project','root/progress'],rounds=1,strength=100)
                self.assertEqual(group['status'],'ok',group)
                self.assertEqual(b.result('recovery_info')['groups']['binary']['total_rounds'],1)
            finally:b.close()
if __name__=='__main__':unittest.main()
