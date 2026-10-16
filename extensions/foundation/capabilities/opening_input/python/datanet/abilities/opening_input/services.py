"""Once-only opening input, committed with the first execution event; no eager wakeup."""
from copy import deepcopy
from datanet.core.node_modules import NodeModule
from datanet.core.agent_inputs import text

class Opening(NodeModule):
    def install(self):text(self.config['text'])
    def bind(self,r):
        self.r=r
        if not self.listeners:self.listen(r,self.owner,'agent/execution-input',self.prepare)
    def prepare(self,e):
        if e['actor']!=self.node.node_id:return
        result=self.r.rpc('opening_input_prepare',target=e['actor'],event=e['input_event'])
        e['input_event'].clear();e['input_event'].update(result)

def prepare(b,p):
    m=b.modules.get(p['target'],'input.opening');event=deepcopy(p['event'])
    if m.state.get('prepared'):return event
    event['text']=text(m.config['text'])+'\n\n'+event['text']
    # The marker and the deliverable are one journal commit, so a crash cannot lose the input.
    m.node.inputs.update('core:execution',dict(inputs=[event]))
    m.state.update(prepared=True,event_id=event['id'])
    return event

def register(s):
    s.node_module('input.opening',Opening)
    s.rpc('opening_input_prepare',prepare,mutation=True)
