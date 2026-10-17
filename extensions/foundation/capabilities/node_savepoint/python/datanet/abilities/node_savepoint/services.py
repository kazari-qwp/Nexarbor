"""Count signals on an explicitly mounted node; request periodic full recovery points."""
from datanet.core.node_modules import NodeModule

class Savepoint(NodeModule):
    def install(self):
        interval=self.config.get('interval',5)
        if type(interval) is not int or interval<1:raise ValueError('Savepoint interval must be a positive integer')
        self.state.setdefault('count',0)
    def bind(self,r):
        graph=dict(type='call',id='count_signal',operation='count_signal',arguments=dict(signal_id={'$ref':'/event/payload/signal/signal_id'}))
        rules=[dict(id='count-savepoint',event='signal/received',channels=self.config['channels'],where={},graph='main')]
        r.plugins['capabilities/event_trigger'].bind(self.node.node_id,rules,{'main':graph},{'count_signal':self.arrive},binding='checkpoint.counter')
    def arrive(self,context,signal_id):
        return self.backend.dispatch('node_savepoint_arrive',dict(target=self.node.node_id,signal_id=signal_id))
    def close(self):
        super().close()
        r=self.backend.modules.application
        if r and 'capabilities/event_trigger' in r.plugins:r.plugins['capabilities/event_trigger'].unbind(self.node.node_id,binding='checkpoint.counter')

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
