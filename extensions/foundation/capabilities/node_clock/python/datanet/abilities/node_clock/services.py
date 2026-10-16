"""Explicit reusable node module; active only when mounted."""
import asyncio
from datanet.core.node_modules import NodeModule
OWNER="capabilities/node_clock"

def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value


class ClockText(NodeModule):
    def bind(self,r):
        rules=[dict(id='advance-clock',channels=self.config['channels'],steps=[dict(tool='advance_clock',arguments=dict(signal_id={'$ref':'/signal/signal_id'}))])]
        r.plugins['capabilities/signal_response'].bind(self.node.node_id,rules,{'advance_clock':self.advance})
    def advance(self,context,signal_id):return self.backend.dispatch('node_clock_advance',dict(target=self.node.node_id,signal_id=signal_id))
    def close(self):
        super().close()
        runtime=getattr(self.backend.network,'_signal_runtime',None)
        if runtime:runtime.unbind(self.node.node_id)


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
