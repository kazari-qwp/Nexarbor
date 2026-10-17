"""Collect declared information under the receiving Agent's ordinary read budget."""
import json
from types import SimpleNamespace
from datanet.core.node_modules import NodeModule
from datanet.core.access_budget import active_agent,access_context
from datanet.core.component_registry import node_enabled
from datanet.abilities.information_provider.services import collection_access

class Collector(NodeModule):
    def bind(self,r):self.r=r
    def collect(self,context=None):
        if not self.active or self.owner not in self.backend.components.enabled:raise PermissionError('Information collector is inactive')
        actor=self.node.node_id;strength=self.config.get('strength',self.r.state(actor)['strength'])
        if strength>self.r.state(actor)['strength']:raise PermissionError('Collection exceeds Agent grant')
        items=[]
        token=active_agent.set((SimpleNamespace(max_signal_strength=self.r.state(actor)['strength']),actor))
        try:
            with self.backend._transaction_lock:
                for node,path,remaining in self.backend.network.walk_states(actor,strength=strength):
                    if node.node_id==actor and not self.config.get('include_self',False) or not node_enabled(node):continue
                    visit=dict(origin=actor,path=list(path),hops=len(path)-1,remaining_strength=remaining)
                    access=collection_access.set(visit)
                    try:
                        with access_context(self.backend.network,node.node_id,remaining,path,channels=('access.read',)):value=node.get_information(visit)
                    finally:collection_access.reset(access)
                    if value:items.append(dict(**value,path=list(path),remaining_strength=remaining))
        finally:active_agent.reset(token)
        lines=[]
        for item in items:
            fields='，'.join(k+'：'+(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False)) for k,v in item['fields'].items())
            lines.append((item['label']+'：' if item['label'] else '')+fields)
        self.r.update_inputs(actor,'information:'+actor,tail=['[周边信息]\n'+'\n'.join(lines)] if lines else [])
        return dict(items=items)
    def close(self):
        if hasattr(self.node,'inputs'):self.node.inputs.update('information:'+self.node.node_id,dict(tail=[]))
        super().close()

def register(s):s.node_module('information.collector',Collector)
