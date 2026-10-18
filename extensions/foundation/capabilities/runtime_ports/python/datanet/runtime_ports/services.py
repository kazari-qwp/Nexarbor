"""显式安装并通过节点 offered_tools 授予；不提供任意网络或文件操作。"""
from datanet.core.agent_node import AgentNode

DEFINITIONS=[dict(name='agent_run',description='运行当前调用节点自己的 Agent；不能在节点事务中等待模型。',parameters={'type':'object','properties':{'message':{'type':'string'}},'additionalProperties':False}),
 dict(name='checkpoint',description='请求保存当前网络与增量检查点，可请求全量。',parameters={'type':'object','properties':{'full':{'type':'boolean'}},'additionalProperties':False})]
CHANNELS={'agent_run':['runtime.agent'],'checkpoint':['runtime.checkpoint']}

def register(services):
    def install(backend):
        async def execute(actor,name,args):
            if name=='checkpoint':return backend.dispatch('save',{'full':args.get('full',False)})
            if backend.node_locks.current:raise RuntimeError('不能持节点锁等待模型')
            if not isinstance(backend.network.nodes[actor],AgentNode):raise ValueError('该端口只运行调用节点自己的 Agent')
            if hasattr(backend,'studio_executor'):backend.studio_executor.visit(dict(actor=actor,target=actor))
            return await backend.execute_agent(actor,args.get('message',''))
        backend.external_tools.register('runtime',DEFINITIONS,execute)
    services.initializers.append(install)
    services.rpc('runtime_catalog',lambda b,p:[dict(**d,channels=CHANNELS[d['name']]) for d in b.external_tools.catalog() if d['provider']=='runtime'])
