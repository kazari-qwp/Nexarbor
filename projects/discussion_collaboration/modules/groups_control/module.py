"""根只调用两个小组入口；不调度单个成员。"""
from copy import deepcopy
from domain.core import Module,access

class GroupsControlModule(Module):
    def __init__(self,config=None,state=None,**access_settings):
        super().__init__('groups.control',**access_settings);self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    @access()
    async def _groups(self,node,wanted):
        if node.modules.get(wanted) is not None:return dict(id=node.info.node_id,name=node.info.name)

    @access()
    async def _call(self,node,target,wanted,operation,parameters):
        if node.info.node_id==target:return await node.modules.get(wanted).execute(operation,**parameters)

    async def execute(self,operation,**parameters):
        wanted='discussion.group' if operation=='datanet_discuss' else 'collaboration.group'
        candidates=[item for item in (await self._groups(wanted)).values() if item is not None]
        p=dict(parameters);group=p.pop('group_id',None)
        if group:candidates=[item for item in candidates if item['id']==group or item['name']==group]
        if len(candidates)!=1:raise ValueError('请连接唯一的小组入口，或指定 group_id')
        target=candidates[0]['id'];action='wait' if operation=='wait_group' else 'discuss' if wanted=='discussion.group' else 'control'
        return (await self._call(target,wanted,action,p))[target]

    async def datanet_discuss(self,**p):return await self.execute('datanet_discuss',**p)
    async def datanet_cooperate(self,**p):return await self.execute('datanet_cooperate',**p)
    async def wait_group(self,**p):return await self.execute('wait_group',**p)
