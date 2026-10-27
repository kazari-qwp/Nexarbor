"""局部管理员入口；范围采集仍统一经过access。"""
from copy import deepcopy
from domain.core import Module,access

class NetworkAdministratorModule(Module):
    def __init__(self,manage,config=None,state=None,**access_settings):
        super().__init__('network.administrator',**access_settings)
        self.manage=manage;self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    @access()
    def collect(self,node,read):return read(node)

    @access(channels=())
    async def _operate(self,node,operation,parameters):return await self.manage(self,operation,parameters)

    async def inspect(self,**p):return next(iter((await self._operate('inspect',p)).values()))
    async def build(self,**p):return next(iter((await self._operate('build',p)).values()))
    async def status(self,**p):return next(iter((await self._operate('status',p)).values()))
    async def apply(self,**p):return next(iter((await self._operate('apply',p)).values()))
    async def cancel(self,**p):return next(iter((await self._operate('cancel',p)).values()))
