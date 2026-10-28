"""读取并发布本实例配置的元数据字段。"""
from collections.abc import Mapping
from copy import deepcopy
from domain.core import Module,access

class MetadataFieldsModule(Module):
    def __init__(self,config=None,state=None,**access_settings):
        super().__init__('metadata.fields',**access_settings)
        self.config=deepcopy(config or {});self.state=deepcopy(state or {});self.published={}

    async def execute(self,operation,**parameters):
        if operation!='read':raise ValueError('不支持的操作：'+str(operation or '未提供'))
        return await self.read()

    async def read(self):return next(iter((await self._read()).values()))

    @access(channels=())
    async def _read(self,node):
        fields=self.config.get('fields',{})
        if not isinstance(fields,Mapping):raise ValueError('配置项 fields 必须是对象。')
        self.published=deepcopy(dict(fields))
        return {'fields':deepcopy(self.published)}

    async def on_signal(self,context):
        if 'metadata.refresh' not in context.signal.channels:raise ValueError('本组件只响应 metadata.refresh。')
        return await self.read()
