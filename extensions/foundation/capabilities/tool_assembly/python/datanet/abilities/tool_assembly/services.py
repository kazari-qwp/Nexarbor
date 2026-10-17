"""Agent-local aliases over graph-exposed tools; authority is checked on every call."""
from copy import deepcopy
from hashlib import sha256
import json,re
from types import SimpleNamespace
from datanet.core.node_modules import NodeModule
from datanet.core.access_budget import active_agent
from datanet.core.component_registry import node_enabled
from datanet.core.tool_access import list_tools
OWNER='capabilities/tool_assembly'

def alias(target,direction,spec,label):
    digest=sha256(json.dumps([target,direction,spec,label],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]
    return 'near_'+re.sub('[^A-Za-z0-9_]','_',spec['name'])[:28]+'_'+digest

class Assembly(NodeModule):
    def install(self):self.aliases={}
    def bind(self,r):self.r=r
    def allowed(self,node,path,tool):
        if node.node_id==self.node.node_id and not self.config.get('include_self',False):return False
        rule=self.config.get('filters',{}).get(tool,{})
        return not rule.get('hops') or len(path)-1 in rule['hops']
    def assemble(self,context=None):
        if not self.active or self.owner not in self.backend.components.enabled:raise PermissionError('Tool assembly module is inactive')
        actor=self.node.node_id;strength=self.config.get('strength',self.r.state(actor)['strength'])
        if strength>self.r.state(actor)['strength']:raise PermissionError('Assembly exceeds Agent grant')
        bindings={};definitions={}
        token=active_agent.set((SimpleNamespace(max_signal_strength=self.r.state(actor)['strength']),actor))
        try:
            with self.backend._transaction_lock:
                for direction in self.config.get('directions',['read','write']):
                    for node,path,remaining in self.backend.network.walk_states(actor,direction=direction,strength=strength):
                        if not node_enabled(node):continue
                        for tool,spec in node.tool_definitions.items():
                            if tool not in node.tools or tool not in node.expose or spec['read_only']!=(direction=='read') or not self.allowed(node,path,tool):continue
                            name=alias(node.node_id,direction,spec,node.name)
                            bindings[name]=dict(target=node.node_id,direction=direction,tool=tool,strength=strength,spec=deepcopy(spec))
                            definitions[name]=dict(owner=OWNER,name=name,description=node.name+'：'+spec['description'],parameters=deepcopy(spec['parameters']))
        finally:active_agent.reset(token)
        dynamic=self.r.state(actor)['dynamic']
        for name in self.aliases:dynamic.pop(name,None)
        for name in definitions:
            if name in dynamic:raise ValueError('Assembled tool conflicts with an existing tool')
        dynamic.update(definitions);self.aliases=bindings
        self.r.refresh(actor)
        return dict(tools=[dict(name=name,target=v['target'],tool=v['tool'],direction=v['direction']) for name,v in bindings.items()])
    def invoke(self,name,args):
        if not self.active:raise PermissionError('Tool assembly module is inactive')
        binding=self.aliases.get(name)
        if not binding:raise PermissionError('Assembled tool is no longer available')
        actor=self.node.node_id;strength=binding['strength']
        if strength>self.r.state(actor)['strength']:raise PermissionError('Assembly exceeds Agent grant')
        token=active_agent.set((SimpleNamespace(max_signal_strength=self.r.state(actor)['strength']),actor))
        try:
            with self.backend._transaction_lock:
                node=self.backend.network.nodes.get(binding['target'])
                if not node or not node_enabled(node):raise PermissionError('Assembled target is inactive')
                live=list_tools(self.backend.network,actor,binding['target'],strength=strength,direction=binding['direction'])
                found=next((spec for spec in live.items if spec['name']==binding['tool']),None)
                if not found:
                    # Applications may explain a denial, never grant access through this hook.
                    failure=dict(actor=actor,target=binding['target'],tool=binding['tool'],message='Assembled tool is no longer reachable or its definition changed')
                    self.r.emit('node/tool-unavailable',failure=failure)
                    raise PermissionError(failure['message'])
                if not self.allowed(node,found['retrieval_path'],binding['tool']) or alias(node.node_id,binding['direction'],{k:v for k,v in found.items() if k not in ('node_id','retrieval_path','remaining_strength')},node.name)!=name:raise PermissionError('Assembled tool is no longer reachable or its definition changed')
                result=self.r.rpc('invoke_tool',actor=actor,target=binding['target'],tool=binding['tool'],arguments=args,direction=binding['direction'],strength=strength)
            self.r.emit('node/tool-invoked',actor=actor,target=binding['target'],tool=binding['tool'],direction=binding['direction'],result=result)
            return result
        finally:active_agent.reset(token)
    def close(self):
        if hasattr(self,'r') and self.node.node_id in self.r.states:
            dynamic=self.r.state(self.node.node_id)['dynamic']
            for name in self.aliases:dynamic.pop(name,None)
        self.aliases={};super().close()

def register(s):s.node_module('tools.assembly',Assembly)
