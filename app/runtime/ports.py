"""原运行端口：自己的 Agent、检查点与显式文本文件读取。"""

from pathlib import Path
import os
from domain.agent import AgentNode

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
    return backend.save(full=args.get('full',False))

DEFINITIONS=[dict(name='agent_run',description='运行当前调用节点自己的 Agent；不能在节点事务中等待模型。',parameters={'type':'object','properties':{'message':{'type':'string'}},'additionalProperties':False}),
 dict(name='checkpoint',description='请求保存当前网络与增量检查点，可请求全量。',parameters={'type':'object','properties':{'full':{'type':'boolean'}},'additionalProperties':False})]
DEFINITIONS.append(TEXT_READ)
CHANNELS={'agent_run':['runtime.agent'],'checkpoint':['runtime.checkpoint'],'read_text':['runtime.text']}

async def run_agent(backend, actor, arguments):
    if backend.node_locks.current:
        raise RuntimeError("不能持节点锁等待模型")
    if not isinstance(backend.network.get(actor), AgentNode):
        raise ValueError("该端口只运行调用节点自己的 Agent")
    async with backend.node_locks.suspend_access():
        return await backend.execute_agent(actor, arguments.get("message", ""))


async def execute(backend, actor, name, arguments):
    if name == "read_text":
        return read_text(os.environ.get("NEXARBOR_PROJECT_DIRECTORY") or os.environ.get("DATANET_PROJECT_DIRECTORY") or backend.directory, arguments)
    if name == "checkpoint":
        return checkpoint(backend, arguments)
    if name == "agent_run":
        return await run_agent(backend, actor, arguments)
    raise ValueError("未登记的运行端口：" + name)
