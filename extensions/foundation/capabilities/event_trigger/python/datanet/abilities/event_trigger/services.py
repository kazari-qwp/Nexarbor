"""Node-mounted event wiring; module destinations are fixed by configuration."""
import asyncio
from datanet.core.node_modules import NodeModule

OWNER='capabilities/event_trigger'

class EventTrigger(NodeModule):
    bind_order=40
    def bind(self,r):
        self.r=r;operations={}
        for app,event,entry in self.listeners:
            if entry in app.listeners[event]:app.listeners[event].remove(entry)
        self.listeners.clear()
        for key,target in self.config['operations'].items():
            if set(target)!={'module','method'} or target['method'].startswith('_'):raise ValueError('Invalid module destination')
            module=self.backend.modules.get(self.node.node_id,target['module'])
            fn=getattr(module,target['method'])
            def invoke(context,_module=module,_fn=fn,**arguments):
                if not self.active or not _module.active or (_module.owner and _module.owner not in r.enabled):raise PermissionError('Event operation is unmounted or disabled')
                return _fn(context,**arguments)
            operations[key]=invoke
        plugin=r.plugins[OWNER]
        plugin.bind(self.node.node_id,self.config['rules'],self.config['graphs'],operations,access_strength=self.config.get('strength',0),binding='event.trigger')
        for event in {rule['event'] for rule in self.config['rules']} - {'signal/received'}:
            def handle(payload,_event=event):
                envelope=dict(type=_event,channels=payload.get('channels',[]),payload=payload)
                try:asyncio.get_running_loop()
                except RuntimeError:return plugin.emit_sync(self.node.node_id,envelope,binding='event.trigger')
                return plugin.emit(self.node.node_id,envelope,binding='event.trigger')
            self.listen(r,OWNER,event,handle)
    def close(self):
        plugin=self.r.plugins.get(OWNER) if hasattr(self,'r') else None
        if plugin:plugin.unbind(self.node.node_id,binding='event.trigger')
        super().close()

def configure(b,p):
    if p.get('actor')!='root':raise PermissionError('Event wiring is host-only')
    if p['target'] not in b.network.nodes:raise ValueError('Unknown event node')
    b.extension_state.setdefault('event_triggers',{}).setdefault(p['target'],{})[p['binding']]=p['configuration']
    return p['configuration']

def register(s):
    s.node_module('event.trigger',EventTrigger)
    s.rpc('event_trigger_configure',configure,mutation=True)
