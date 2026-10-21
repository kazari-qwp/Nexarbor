"""Historical Workspace implementation, exposed as one local module."""
import asyncio,os,hashlib
from pathlib import Path
from .workspace import Workspace
from datanet.core.module_protocol import ComponentResult
_LOCKS={}

def workspace(ctx):
    root=Path(os.environ.get('DATANET_PROJECT_DIRECTORY','.'))
    directory=root/ctx.config.get('directory','workspace/cooperation')/hashlib.sha256(ctx.node_id.encode()).hexdigest()[:12]
    return Workspace(directory, list(ctx.state.get('members',[])))

async def execute(ctx,activation):
    p=activation.parameters;op=activation.operation
    async with _LOCKS.setdefault(id(ctx),asyncio.Lock()):
        try:
            if op=='prepare':
                ctx.state['members']=p['members'];w=workspace(ctx)
                await asyncio.to_thread(w.prepare)
                return ComponentResult(data=dict(repository=w.repository(),directory=str(w.directory),members={n:str(w.personal(n)) for n in p['members']}))
            w=workspace(ctx)
            if op=='proposal':
                actor=p['actor'];artifacts=w.directory/'artifacts';artifacts.mkdir(exist_ok=True)
                value=await asyncio.to_thread(w.proposal,actor,p.get('test_scripts',[]),p.get('test_results',[]),p.get('logs',[]),artifacts)
            elif op=='repository':value=w.repository()
            else:
                value=await asyncio.to_thread(w.invoke,p['actor'],op,p.get('message','Publish contribution'))
                value['artifacts_path']=str(w.directory/'artifacts');Path(value['artifacts_path']).mkdir(exist_ok=True)
            return ComponentResult(data=value)
        except Exception as error:return ComponentResult(status='error',error=str(error))
