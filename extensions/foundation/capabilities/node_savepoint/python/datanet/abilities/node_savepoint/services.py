"""Count signals on an explicitly mounted node; request periodic full recovery points."""
from datanet.core.node_modules import NodeModule

class Savepoint(NodeModule):
    def install(self):
        interval=self.config.get('interval',5)
        if type(interval) is not int or interval<1:raise ValueError('Savepoint interval must be a positive integer')
        self.state.setdefault('count',0)
    def bind(self,r):
        rules=[dict(id='count-savepoint',channels=self.config['channels'],steps=[dict(tool='count_signal',arguments=dict(signal_id={'$ref':'/signal/signal_id'}))])]
        r.plugins['capabilities/signal_response'].bind(self.node.node_id,rules,{'count_signal':self.arrive})
    def arrive(self,context,signal_id):
        return self.backend.dispatch('node_savepoint_arrive',dict(target=self.node.node_id,signal_id=signal_id))
    def close(self):
        super().close()
        runtime=getattr(self.backend.network,'_signal_runtime',None)
        if runtime:runtime.unbind(self.node.node_id)

def arrive(b,p):
    m=b.modules.get(p['target'],'checkpoint.counter')
    if m.state.get('last_signal')==p['signal_id']:return dict(count=m.state['count'],reused=True)
    m.state['count']+=1;m.state['last_signal']=p['signal_id']
    full=m.state['count']%m.config.get('interval',5)==0
    if full:b.dispatch('save',dict(full=True))
    return dict(count=m.state['count'],full_snapshot=full)

def register(s):
    s.node_module('checkpoint.counter',Savepoint)
    s.rpc('node_savepoint_arrive',arrive,mutation=True)
