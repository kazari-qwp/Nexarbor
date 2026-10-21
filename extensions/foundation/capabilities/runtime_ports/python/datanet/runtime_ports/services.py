"""显式安装并通过节点 offered_tools 授予；不提供任意网络或文件操作。"""
from datanet.core.agent_node import AgentNode
from pathlib import Path
import os

TEXT_READ=dict(name='read_text',description='读取项目内或显式 roots 下的 UTF-8 文本，最多 1 MiB；返回 text/path，不写文件。',parameters={'type':'object','properties':{'path':{'type':'string','minLength':1},'roots':{'type':'array','items':{'type':'string','minLength':1}}},'required':['path'],'additionalProperties':False})


def read_text(project,args):
    root=Path(project).resolve();name=args['path'];path=Path(name)
    target=(path if path.is_absolute() else root/path).resolve()
    roots=[root]+[(Path(value) if Path(value).is_absolute() else root/value).resolve() for value in args.get('roots',[])]
    if not any(target.is_relative_to(folder) for folder in roots):raise PermissionError('文本路径越出项目和明确配置的目录')
    with target.open('rb') as stream:content=stream.read(1024*1024+1)
    if len(content)>1024*1024:raise ValueError('文本文件超过 1 MiB')
    return dict(text=content.decode('utf-8-sig'),path=str(target))

def checkpoint(backend,args):
    return backend.dispatch('save',{'full':args.get('full',False)})

DEFINITIONS=[dict(name='agent_run',description='运行当前调用节点自己的 Agent；不能在节点事务中等待模型。',parameters={'type':'object','properties':{'message':{'type':'string'}},'additionalProperties':False}),
 dict(name='checkpoint',description='请求保存当前网络与增量检查点，可请求全量。',parameters={'type':'object','properties':{'full':{'type':'boolean'}},'additionalProperties':False})]
DEFINITIONS.append(TEXT_READ)
CHANNELS={'agent_run':['runtime.agent'],'checkpoint':['runtime.checkpoint'],'read_text':['runtime.text']}

async def run_agent(backend,actor,args):
    """The official self-execution boundary, shared by real and test model adapters."""
    if backend.node_locks.current:raise RuntimeError('不能持节点锁等待模型')
    if not isinstance(backend.network.nodes[actor],AgentNode):raise ValueError('该端口只运行调用节点自己的 Agent')
    from datanet.core.access_budget import current_access,active_agent
    frame=current_access.set(None);identity=active_agent.set(None)
    try:
        if hasattr(backend,'studio_executor'):
            executor=backend.studio_executor;node,binding=executor.binding(actor)
            await executor.module_tools.visit(actor,actor,strength=binding.get('strength',0),channels=binding.get('channels',[]))
        async with backend.node_locks.suspend_access():
            return await backend.execute_agent(actor,args.get('message',''))
    finally:active_agent.reset(identity);current_access.reset(frame)

def register(services):
    def install(backend):
        async def execute(actor,name,args):
            if name=='read_text':return read_text(os.environ.get('DATANET_PROJECT_DIRECTORY') or backend.directory,args)
            if name=='checkpoint':return checkpoint(backend,args)
            return await run_agent(backend,actor,args)
        backend.external_tools.register('runtime',DEFINITIONS,execute)
    services.initializers.append(install)
    services.rpc('runtime_catalog',lambda b,p:[dict(**d,channels=CHANNELS[d['name']]) for d in b.external_tools.catalog() if d['provider']=='runtime'])
