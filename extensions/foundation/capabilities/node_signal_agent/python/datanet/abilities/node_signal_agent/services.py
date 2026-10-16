"""Explicit reusable node module; active only when mounted."""
import asyncio
from datanet.core.node_modules import NodeModule
OWNER="capabilities/node_signal_agent"

def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value


class SignalAgent(NodeModule):
    bind_order=20
    def bind(self,r):
        self.r=r
        if not self.listeners:
            self.listen(r,OWNER,'agent/request',self.request)
            self.listen(r,OWNER,'agent/pre-step',self.pre_step)
        rules=[dict(id='execute-agent',channels=self.config['channels'],steps=[dict(tool='assemble_context',arguments={}),dict(tool='run_agent',arguments=dict(task={'$ref':'/signal/content/task'},timeout_ms={'$ref':'/signal/content/timeout_ms'}))])]
        r.plugins['capabilities/signal_response'].bind(self.node.node_id,rules,dict(assemble_context=self.assemble,run_agent=self.run),access_strength=self.config.get('strength',2),on_error=self.failed)
    def pre_step(self,e):
        if e['actor']!=self.node.node_id:return
        if self.config.get('guide'):self.r.load(e['actor'],'node:activity-guide',text(self.r,self.config['guide']))
        if self.state.get('status')=='running' and self.state.get('requests',0)>=self.config.get('max_requests',8):raise RuntimeError('Agent signal request budget exhausted')
    def request(self,e):
        if e['actor']==self.node.node_id and self.state.get('status')=='running':
            self.backend.dispatch('node_activity_request',dict(target=self.node.node_id))
    def assemble(self,context):
        self.r.emit('context/prepare',actor=self.node.node_id)
        return self.r.plugins['capabilities/context_assembly'].assemble(self.node.node_id)
    def execute(self,context,task,timeout_ms,execution_id):
        previous=getattr(self.r.local,'execution_id',None);self.r.local.execution_id=execution_id
        try:return self.r.plugins['capabilities/agent_runtime'].execute(self.config.get('manager','root'),self.node.node_id,task,kind=self.config.get('kind','agent'),timeout_ms=timeout_ms)
        finally:self.r.local.execution_id=previous
    async def run(self,context,task,timeout_ms):
        previous=getattr(self,'worker',None)
        if previous and not previous.done():raise RuntimeError('Previous Agent activity is still stopping')
        self.backend.dispatch('node_activity_start',dict(target=self.node.node_id,signal_id=context.signal.signal_id))
        worker=asyncio.create_task(asyncio.to_thread(self.execute,context,task,timeout_ms,getattr(self.r.local,'execution_id',None)))
        self.worker=worker
        worker.add_done_callback(lambda job:job.exception() if not job.cancelled() else None)
        result=await asyncio.shield(worker)
        if result['status']!='ok':raise RuntimeError('Agent activity did not complete normally')
        self.backend.dispatch('node_activity_end',dict(target=self.node.node_id,signal_id=context.signal.signal_id,status='completed'))
        return dict(session_id=result['session_id'],requests=self.state['requests'])
    async def failed(self,context,error):
        self.backend.dispatch('node_activity_end',dict(target=self.node.node_id,signal_id=context.signal.signal_id,status='unavailable',reason=str(error) or type(error).__name__))
        try:await asyncio.to_thread(self.r.host,'cancel-agent',actor=self.node.node_id)
        except Exception:pass
    def close(self):
        super().close()
        runtime=getattr(self.backend.network,'_signal_runtime',None)
        if runtime:runtime.unbind(self.node.node_id)


def start(b,p):
    m=b.modules.get(p['target'],'agent.signal')
    if m.state.get('status')=='running':raise RuntimeError('Activity already running')
    m.state.update(signal_id=p['signal_id'],status='running',requests=0,reason='')
    return dict(m.state)


def request(b,p):
    m=b.modules.get(p['target'],'agent.signal')
    if m.state.get('requests',0)>=m.config.get('max_requests',8):raise RuntimeError('Agent signal request budget exhausted')
    m.state['requests']+=1
    return dict(m.state)


def end(b,p):
    m=b.modules.get(p['target'],'agent.signal')
    if m.state.get('signal_id')!=p['signal_id']:return dict(ignored=True)
    if m.state.get('status')=='unavailable':return dict(m.state)
    m.state.update(status=p['status'],reason=p.get('reason','')[:500]);return dict(m.state)



def register(s):
    s.node_module('agent.signal',SignalAgent)
    for name,fn in [('start',start),('request',request),('end',end)]:s.rpc('node_activity_'+name,fn,mutation=True)
