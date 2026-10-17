from datanet.core.node_modules import NodeModule

class ModuleExecutor(NodeModule):
    def bind(self,r):self.r=r
    async def execute(self,context,graph,event,operations):
        if not self.active or self.owner not in self.r.enabled:raise PermissionError('Module executor is unmounted')
        return await self.r.plugins['capabilities/module_execution'].execute(self.node.node_id,graph,operations,event,context)

def register(s):s.node_module('modules.executor',ModuleExecutor)
