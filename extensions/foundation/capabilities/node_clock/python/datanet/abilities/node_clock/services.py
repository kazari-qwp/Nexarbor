"""Explicit reusable node module; active only when mounted."""
import asyncio
from datanet.core.node_modules import NodeModule
OWNER="capabilities/node_clock"

def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value


class ClockText(NodeModule):
    def bind(self,r):
        graph=dict(type='call',id='advance_clock',operation='advance_clock',arguments=dict(signal_id={'$ref':'/event/payload/signal/signal_id'}))
        rules=[dict(id='advance-clock',event='signal/received',channels=self.config['channels'],where={},graph='main')]
        r.plugins['capabilities/event_trigger'].bind(self.node.node_id,rules,{'main':graph},{'advance_clock':self.advance},binding='clock.text')
    def advance(self,context,signal_id):return self.backend.dispatch('node_clock_advance',dict(target=self.node.node_id,signal_id=signal_id))
    def close(self):
        super().close()
        r=self.backend.modules.application
        if r and 'capabilities/event_trigger' in r.plugins:r.plugins['capabilities/event_trigger'].unbind(self.node.node_id,binding='clock.text')


def advance(b,p):
    m=b.modules.get(p['target'],'clock.text')
    if m.state.get('signal_id')!=p['signal_id']:
        m.state['tick']+=1;m.state['signal_id']=p['signal_id']
        slots=m.config['slots'];tick=m.state['tick']
        m.node.write('content',m.config['format'].format(day=tick//len(slots)+1,slot=slots[tick%len(slots)],tick=tick))
    return dict(m.state)



def register(s):
    s.node_module('clock.text',ClockText)
    s.rpc('node_clock_advance',advance,mutation=True)
