"""A model-text double behind the real self-execution boundary, never a whole port mock."""
from hashlib import sha256
import inspect
from types import MethodType

def register_agent(backend,callback,*,prepare=None,acknowledge=None,views=None):
    import datanet
    from .service import PROJECT
    path=str(PROJECT/'extensions/foundation/capabilities/runtime_ports/python/datanet')
    if path not in datanet.__path__:datanet.__path__.append(path)
    from datanet.runtime_ports.services import DEFINITIONS,run_agent
    from datanet.core.backend import Backend
    from datanet.core.execution_binding import validate_execution_binding
    if not hasattr(backend,'execute_agent'):backend.execute_agent=MethodType(Backend.execute_agent,backend)
    running=set()
    async def execute_model(actor,message='',**options):
        if actor in running:raise RuntimeError('该 Agent 正在执行，不能重叠启动模型')
        running.add(actor)
        try:return await model_turn(actor,message,**options)
        finally:running.remove(actor)

    async def model_turn(actor,message='',**options):
        if prepare:
            view=await prepare(actor)
            if views is not None:views[actor]=view
            if acknowledge:await acknowledge(actor,view['inputs'])
        else:
            node=backend.network.nodes[actor]
            if not node.execution_binding:raise ValueError('模型替身也需要真实执行绑定；ModuleHarness 用 h.bind_agent(actor,binding) 显式配置，见模块教程05；完整消费用 NetworkHarness，不补改候选配置')
            validate_execution_binding(node,backend.network,backend.components.module_types)
        text=callback(actor,message)
        if inspect.isawaitable(text):text=await text
        if not isinstance(text,str):raise TypeError('模型替身只返回模型正文字符串；不要返回或代做业务协议状态')
        return dict(status='completed',session_id='test-'+sha256(actor.encode()).hexdigest()[:24],steps=1,output=text,error=None,requests=0)
    backend.agent_executor=execute_model
    definitions=[{key:item[key] for key in ('name','description','parameters')} for item in backend.external_tools.catalog() if item['provider']=='runtime' and item['name']!='agent_run']
    definitions.append(next(item for item in DEFINITIONS if item['name']=='agent_run'))
    previous=backend.external_tools._providers.get('runtime')
    async def dispatch(actor,name,args):
        if name=='agent_run':return await run_agent(backend,actor,args)
        if previous is None:raise RuntimeError('未登记的运行端口：'+name)
        value=previous(actor,name,args)
        return await value if inspect.isawaitable(value) else value
    backend.external_tools.register('runtime',definitions,dispatch)
