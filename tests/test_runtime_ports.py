"""官方执行端口只运行当前节点；沿真实框架调度，使用无模型宿主回调。"""
import os,sys,subprocess,tempfile,textwrap,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RuntimePorts(unittest.TestCase):
    def test_self_execution_is_async_and_model_wait_holds_no_exclusive_lock(self):
        source=r'''
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()/'adapters/harness/studio'))
from executor import NativeExecutor
from datanet.core.backend import Backend
from datanet.core.module_protocol import ModuleDefinition,ComponentResult
b=Backend(sys.argv[1]);calls=[]
class Port:
    def host(self,method,p):
        if method=='agent-context-capture':return {n:dict(session_id=s,adapter='test') for n,s in p['bindings'].items()}
        if method=='agent-context-restore':return dict(contexts=p['contexts'])
        assert method=='agent-run' and p['actor']=='root' and not b.node_locks.exclusive
        calls.append(p);return dict(status='completed',session_id='test-own-session',steps=1,requests=0)
try:
    b.studio_executor=NativeExecutor(b,Port());b.root.execution_binding={'executor':'harness','strength':0,'channels':['tools']}
    b.root.offered_tools=[{'ref':'runtime:agent_run','channels':['runtime.agent']}]
    b.modules.mount('root','tools.collector',access={'strength':0,'channels':['tools']})
    async def execute(ctx,activation):
        if activation.parameters.get('locked'):
            async with ctx.network.lock_nodes([ctx.node_id]):return ComponentResult(data=await ctx.network.invoke(ctx.node_id,'runtime:agent_run',{}))
        return ComponentResult(data=await ctx.network.invoke(ctx.node_id,'runtime:agent_run',{'message':'执行本地工作'}))
    b.modules.factories['starter']=ModuleDefinition(execute,node_types=['agent'],operations=[{'name':'run','channels':['run'],'parameters':{'type':'object'},'result':{}}])
    b.modules.mount('root','starter',access={'strength':0,'channels':['runtime.agent']})
    result=b.runtime.run(b.modules.call('root','starter','run'));assert result['data']['session_id']=='test-own-session' and len(calls)==1
    try:b.runtime.run(b.modules.call('root','starter','run',{'locked':True}))
    except RuntimeError as error:assert '锁' in str(error)
    else:raise AssertionError('持独占锁时启动了模型')
    assert len(calls)==1
finally:b.close()
'''
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATANET_COMPONENT_ROOT=str(ROOT/'extensions/development'),DATANET_COMPONENT_SELECTION='["capabilities/component_studio","capabilities/tool_collector","capabilities/runtime_ports"]',DATANET_COMPONENT_PROFILE='{}')
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as temporary:
            result=subprocess.run([sys.executable,'-c',textwrap.dedent(source),temporary],env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=40)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
