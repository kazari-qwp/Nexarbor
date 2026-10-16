"""Explicit reusable node module; active only when mounted."""
import asyncio
from datanet.core.node_modules import NodeModule
OWNER="capabilities/node_context_sources"

def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value


class Context(NodeModule):
    bind_order=0
    def bind(self,r):
        self.r=r
        assembly=r.plugins['capabilities/context_assembly']
        assembly.configure(self.node.node_id,self.config['sources'],self.config.get('document_roots',[]))
        for actor in self.config['actors']:assembly.bind(actor,self.node.node_id)
    def unmount(self):
        result=self.backend.dispatch('context_assembly_remove',dict(actor='root',node_id=self.node.node_id))
        for actor in result['actors']:
            patch=dict(system_prompt='',context=[],tail=[])
            if hasattr(self,'r'):self.r.update_inputs(actor,'context-assembly:'+self.node.node_id,**patch)
            else:self.backend.network.nodes[actor].update_inputs('context-assembly:'+self.node.node_id,**patch)
        super().unmount()


def register(s):
    s.node_module('context.sources',Context)
