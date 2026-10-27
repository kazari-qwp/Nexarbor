"""知识命令继续复用同节点 data.local 的只读检查与节点事务。"""
from copy import deepcopy
from domain.core import Module,access

class DataKnowledgeModule(Module):
    def __init__(self,transaction,config=None,state=None,**access_settings):
        super().__init__('data.knowledge',**access_settings)
        self.transaction=transaction;self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    async def execute(self,operation,**arguments):return next(iter((await self._operate(operation,arguments)).values()))
    async def put(self,**arguments):return await self.execute('put',**arguments)
    async def history(self,**arguments):return await self.execute('history',**arguments)
    async def remove(self,**arguments):return await self.execute('remove',**arguments)
    async def restore(self,**arguments):return await self.execute('restore',**arguments)
    async def index(self,**arguments):return await self.execute('index',**arguments)
    async def search(self,**arguments):return await self.execute('search',**arguments)
    async def fetch(self,**arguments):return await self.execute('fetch',**arguments)

    @access(channels=())
    async def _operate(self,node,operation,arguments):
        writing=operation not in ('history','search','fetch')
        node.modules.get('data.local').check(write=writing)
        command=dict(operation=operation,arguments=arguments)
        if not writing:return node.dataer.write('$command',command)
        async with self.transaction([node.info.node_id]):return node.dataer.write('$command',command)
