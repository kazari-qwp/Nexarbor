"""最终演示的私有 Git 工作区与固定验收快照；沿用原 Workspace。"""
import asyncio
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from domain.core import Module,access
from .workspace import Workspace

class GitWorkspaceModule(Module):
    def __init__(self,project_directory,config=None,state=None,**access_settings):
        super().__init__('git.workspace',**access_settings)
        self.directory=Path(project_directory).resolve();self.config=deepcopy(config or {});self.state=deepcopy(state or {});self._lock=asyncio.Lock()

    def workspace(self,node):
        directory=self.directory/self.config.get('directory','workspace/cooperation')/sha256(node.info.node_id.encode()).hexdigest()[:12]
        return Workspace(directory,list(self.state.get('members',[])))

    async def execute(self,action,**parameters):
        return next(iter((await self._operate(action,parameters)).values()))

    async def prepare(self,**parameters):return await self.execute('prepare',**parameters)
    async def proposal(self,**parameters):return await self.execute('proposal',**parameters)
    async def repository(self,**parameters):return await self.execute('repository',**parameters)
    async def inspect(self,**parameters):return await self.execute('inspect',**parameters)
    async def sync(self,**parameters):return await self.execute('sync',**parameters)
    async def publish(self,**parameters):return await self.execute('publish',**parameters)

    @access(channels=())
    async def _operate(self,node,op,p):
        async with self._lock:
            if op=='prepare':
                self.state['members']=p['members'];w=self.workspace(node);await asyncio.to_thread(w.prepare)
                return dict(repository=w.repository(),directory=str(w.directory),members={n:str(w.personal(n)) for n in p['members']})
            w=self.workspace(node)
            if op=='proposal':
                artifacts=w.directory/'artifacts';artifacts.mkdir(exist_ok=True)
                return await asyncio.to_thread(w.proposal,p['actor'],p.get('test_scripts',[]),p.get('test_results',[]),p.get('logs',[]),artifacts)
            if op=='repository':return w.repository()
            value=await asyncio.to_thread(w.invoke,p['actor'],op,p.get('message','Publish contribution'))
            value['artifacts_path']=str(w.directory/'artifacts');Path(value['artifacts_path']).mkdir(exist_ok=True)
            return value
