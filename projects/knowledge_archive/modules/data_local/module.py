"""保留原本地数据读写与只读规则；实际文件归 DataNode 管理。"""
from copy import deepcopy
from domain.core import Module,access
from app.data.text import TextFileAccess

class DataLocalModule(Module):
    def __init__(self,transaction,config=None,state=None,**access_settings):
        super().__init__('data.local',**access_settings)
        self.transaction=transaction;self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    def check(self,write):
        if write and self.config.get('read_only',False):raise PermissionError('该数据节点已配置为只读')
        return True

    async def inspect(self):return next(iter((await self._operate('inspect',{})).values()))
    async def read(self,key):return next(iter((await self._operate('read',{'method':'key','key':key})).values()))
    async def query(self,request):return next(iter((await self._operate('read',request)).values()))
    async def write(self,key,value,mode='upsert'):return next(iter((await self._operate('write',dict(key=key,value=value,mode=mode))).values()))

    @access(channels=())
    async def _operate(self,node,operation,parameters):
        dataer=TextFileAccess(node,max_chars=self.config.get('max_chars')) if node.saver.kind=='markdown' else node.dataer
        if operation=='inspect':return dataer.get_schema()
        if operation=='read':return dataer.read(parameters)
        self.check(write=True)
        async with self.transaction([node.info.node_id]):return dataer.write(**parameters)
