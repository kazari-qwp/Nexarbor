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
        tools=dict(assemble_context=self.assemble,run_agent=self.run)
        steps=[]
        for entry in self.config.get('prepare',[]):
            if entry['step'] in tools:raise ValueError('Duplicate or reserved preparation step')
            module=self.backend.modules.get(self.node.node_id,entry['module'])
            tools[entry['step']]=getattr(module,entry['method'])
            steps.append(dict(type='call',id=entry['step'],operation=entry['step'],arguments={}))
        if not steps:steps=[dict(type='call',id='assemble_context',operation='assemble_context',arguments={})]
        steps.append(dict(type='call',id='run_agent',operation='run_agent',arguments=dict(task={'$ref':'/event/payload/signal/content/task'},timeout_ms={'$ref':'/event/payload/signal/content/timeout_ms'})))
        rules=[dict(id='execute-agent',event='signal/received',channels=self.config['channels'],where={},graph='main')]
        r.plugins['capabilities/event_trigger'].bind(self.node.node_id,rules,{'main':dict(type='sequence',steps=steps)},tools,access_strength=self.config.get('strength',2),on_error=self.failed,binding='agent.signal')
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
        try:
            if self.config.get('prepare'):self.assemble(context)
            return self.r.plugins['capabilities/agent_runtime'].execute(self.config.get('manager','root'),self.node.node_id,task,kind=self.config.get('kind','agent'),timeout_ms=timeout_ms)
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
        r=self.backend.modules.application
        if r and 'capabilities/event_trigger' in r.plugins:r.plugins['capabilities/event_trigger'].unbind(self.node.node_id,binding='agent.signal')


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
