"""Declarative opt-in publication of selected metadata; not an Agent tool."""
from contextvars import ContextVar
from copy import deepcopy
from types import SimpleNamespace
from datanet.core.node_modules import NodeModule
from datanet.core.metadata import lookup
from datanet.core.access_budget import current_access,active_agent

collection_access=ContextVar('information_collection',default=None)

class Information(NodeModule):
    def install(self):
        fields=self.config.get('fields',{})
        if not isinstance(fields,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in fields.items()):raise ValueError('Information fields must map names to metadata paths')
        labels=self.config.get('labels_by_hops',{})
        if not isinstance(labels,dict) or any(not isinstance(k,str) or not k.isdecimal() or not isinstance(v,str) for k,v in labels.items()):raise ValueError('Information labels must map hop counts to text')
        if getattr(self.node,'_information_provider',None):raise ValueError('Information provider already mounted')
        self.node._information_provider=self.get_information
    def get_information(self,context):
        frame=current_access.get()
        if not self.active or self.owner not in self.backend.components.enabled:raise PermissionError('Information provider is inactive')
        if context is not collection_access.get() or not context or not frame or frame['network'] is not self.backend.network or frame['node_id']!=self.node.node_id or frame['strength']!=context['remaining_strength']:raise PermissionError('Information is available only through the collector')
        # A node publishes only configured fields from its own metadata, never the full object.
        token=active_agent.set((SimpleNamespace(max_signal_strength=0),self.node.node_id))
        try:metadata=self.node.get_metadata()
        finally:active_agent.reset(token)
        fields={}
        for label,path in self.config.get('fields',{}).items():
            try:fields[label]=deepcopy(lookup(metadata,path))
            except (KeyError,IndexError,TypeError):continue
        if not fields:return None
        return dict(node_id=self.node.node_id,fields=fields,label=self.config.get('labels_by_hops',{}).get(str(context['hops']),''))
    def close(self):
        if getattr(self.node,'_information_provider',None)==self.get_information:del self.node._information_provider
        super().close()

def register(s):s.node_module('information.provider',Information)
