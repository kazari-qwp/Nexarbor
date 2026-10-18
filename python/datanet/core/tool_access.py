"""沿频道授权的接口发现并调用节点工具；起点由所属节点固定。"""
from copy import deepcopy
from datanet.core.node import NodeResult
from datanet.core.access_budget import access_context, current_access, active_agent
from types import SimpleNamespace
import asyncio
import inspect
from contextlib import nullcontext

def _node_access(network,nodes,*,mutable=False):
    locks=getattr(network,'node_locks',None)
    return locks.access_sync(nodes,mutable=mutable) if locks else nullcontext()

def reachable(network,node_id,scope='network',strength=0,channels=()):
    yield from network.walk(node_id,scope=scope,strength=strength,channels=channels)

def list_nodes(network,node_id,scope='network',strength=0,channels=()):
    targets=[n.node_id for n,_,_ in network.walk_states(node_id,scope=scope,strength=strength,channels=channels)]
    with _node_access(network,targets):
        return _list_nodes(network,node_id,scope,strength,channels)

def _list_nodes(network,node_id,scope='network',strength=0,channels=()):
    return NodeResult(items=[{**node.describe(include_schema=False),'exposed_tool_count':sum(name in node.tools and name in node.expose for name in node.tool_definitions),'retrieval_path':path} for node,path in reachable(network,node_id,scope,strength,channels)])

def list_tools(network,node_id,target_node_id,scope='network',strength=0):
    if target_node_id not in network.nodes:return NodeResult(status='not_found',errors=['目标节点不存在'])
    with _node_access(network,[target_node_id]):
        return _list_tools(network,node_id,target_node_id,scope,strength)

def _list_tools(network,node_id,target_node_id,scope='network',strength=0):
    target=network.nodes.get(target_node_id)
    if target is None:return NodeResult(status='not_found',errors=['目标节点不存在'])
    paths={};items=[]
    for name,definition in target.tool_definitions.items():
        if name not in target.tools or name not in target.expose:continue
        channels=tuple(definition['access_channels'])
        frame=current_access.get()
        if frame and frame['network'] is network and not set(channels)<=set(frame['channels']):continue
        if channels not in paths:
            paths[channels]=next(((path,remaining) for node,path,remaining in network.walk_states(node_id,scope=scope,strength=strength,channels=channels) if node.node_id==target_node_id),None)
        reachable=paths[channels]
        if reachable is not None:
            path,remaining=reachable
            items.append({**deepcopy(definition),'node_id':target_node_id,'retrieval_path':path.copy(),'remaining_strength':remaining})
    return NodeResult(items=items)

def validate_arguments(value, schema):
    """当前工具使用的 JSON Schema 子集：类型、字段、必填、枚举与数组。"""
    types = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'integer': int, 'number': (int, float), 'null': type(None)}
    expected = schema.get('type')
    choices = expected if isinstance(expected, list) else [expected]
    if expected is not None and (not any((type(value) in (types[t] if isinstance(types[t], tuple) else (types[t],)) for t in choices))):
        raise TypeError(f'参数类型不符合定义：{expected}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('参数不在允许的枚举值中')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        if any((name not in value for name in schema.get('required', []))):
            raise ValueError('缺少工具必填参数')
        if schema.get('additionalProperties') is False and set(value) - properties.keys():
            raise ValueError('包含未声明的工具参数')
        for name, item in value.items():
            if name in properties:
                validate_arguments(item, properties[name])
    if isinstance(value, list) and 'items' in schema:
        for item in value:
            validate_arguments(item, schema['items'])

def invoke_tool(network,node_id,target_node_id,tool_name,arguments,scope='network',strength=0):
    """Synchronous host entry; asynchronous tools also complete before returning."""
    if target_node_id not in network.nodes:return NodeResult(status='not_found',errors=['目标节点不存在'])
    with _node_access(network,[target_node_id],mutable=True):
        return _invoke_tool(network,node_id,target_node_id,tool_name,arguments,scope,strength,asynchronous=False)


async def invoke_tool_async(network,node_id,target_node_id,tool_name,arguments,scope='network',strength=0):
    locks=getattr(network,'node_locks',None)
    if locks:
        if target_node_id not in network.nodes:return NodeResult(status='not_found',errors=['目标节点不存在'])
        async with locks.access([target_node_id]):
            return await _invoke_async_owned(network,node_id,target_node_id,tool_name,arguments,scope,strength)
    return await _invoke_async_owned(network,node_id,target_node_id,tool_name,arguments,scope,strength)

async def _invoke_async_owned(network,node_id,target_node_id,tool_name,arguments,scope,strength):
    result=_invoke_tool(network,node_id,target_node_id,tool_name,arguments,scope,strength,asynchronous=True)
    return await result if inspect.isawaitable(result) else result


def _invoke_tool(network,node_id,target_node_id,tool_name,arguments,scope,strength,*,asynchronous):
    if not isinstance(target_node_id,str) or not isinstance(tool_name,str) or not isinstance(arguments,dict):raise TypeError('目标和工具名必须为字符串，arguments 必须为字典')
    frame=current_access.get()
    if frame is not None and frame['network'] is network and target_node_id in frame['visited']:return NodeResult(status='forbidden',errors=['本次访问不允许重复调用已访问节点'])
    node=network.nodes.get(target_node_id)
    if node is None:return NodeResult(status='not_found',errors=['目标节点不存在'])
    if tool_name in node.agent_tool_definitions or tool_name not in node.expose:return NodeResult(status='forbidden',errors=['Tool is private or not exposed by node'])
    definition=node.tool_definitions.get(tool_name)
    if definition is None or tool_name not in node.tools:return NodeResult(status='not_found',errors=['目标没有注册该工具'])
    # The callee's trusted declaration determines authorization. No caller-supplied
    # channels enter this operation, including through a triggering signal.
    channels=tuple(definition['access_channels'])
    if frame and frame['network'] is network and not set(channels)<=set(frame['channels']):return NodeResult(status='forbidden',errors=['嵌套调用不能扩大访问频道'])
    for target,path,remaining in network.walk_states(node_id,scope=scope,strength=strength,channels=channels):
        if target.node_id!=target_node_id:continue
        validate_arguments(arguments,definition['parameters'])
        if not asynchronous and inspect.iscoroutinefunction(node.tools[tool_name]):
            try:asyncio.get_running_loop()
            except RuntimeError:pass
            else:raise RuntimeError('Use await invoke_tool_async inside an event loop')
        identity=active_agent.set(active_agent.get() or (SimpleNamespace(max_signal_strength=strength),node_id))
        try:
            with access_context(network,target_node_id,remaining,path,channels=channels):result=node.invoke_tool(tool_name,**arguments)
        finally:active_agent.reset(identity)
        source={'node_id':target_node_id,'tool_name':tool_name,'retrieval_path':path.copy(),'remaining_strength':remaining,'access_channels':list(channels)}
        def finish(value):
            if isinstance(value,NodeResult):
                value=deepcopy(value);value.sources=[{**s,'tool_name':tool_name,'tool_path':path.copy()} for s in value.sources];value.sources.append(source);return value
            return NodeResult(items=[{'result':value}],sources=[source])
        if inspect.isawaitable(result):
            if not asynchronous:
                try:asyncio.get_running_loop()
                except RuntimeError:pass
                else:
                    if inspect.iscoroutine(result):result.close()
                    raise RuntimeError('Use await invoke_tool_async inside an event loop')
            async def complete():
                token=active_agent.set(active_agent.get() or (SimpleNamespace(max_signal_strength=strength),node_id))
                try:
                    with access_context(network,target_node_id,remaining,path,channels=channels):return finish(await result)
                finally:active_agent.reset(token)
            return complete() if asynchronous else asyncio.run(complete())
        return finish(result)
    return NodeResult(status='forbidden',errors=['目标工具所需频道不可达'])

def discovery_definitions():
    scope={'type':'string','enum':['local','network'],'description':'local只访问本体；默认network。'}
    strength={'type':'number','minimum':0,'description':'访问强度，受所属Agent授权上限约束；嵌套继承剩余额度。'}
    result=[]
    for name,description,properties,required in (
        ('list_nodes','列出沿指定频道可达的节点概况；不授予工具调用权限。',{'channels':{'type':'array','items':{'type':'string'},'description':'本次概况查询的频道；省略时仅查询自身，不授予工具调用权限。'}},[]),
        ('list_tools','发现一个节点向你开放的工具及参数；框架按各工具声明的频道检查权限。',{'target_node_id':{'type':'string'}},['target_node_id']),
        ('invoke_tool','调用已发现的节点工具；访问频道由工具声明决定，无需填写。',{'target_node_id':{'type':'string'},'tool_name':{'type':'string'},'arguments':{'type':'object'}},['target_node_id','tool_name','arguments'])):
        result.append({'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':{**properties,'scope':deepcopy(scope),'strength':deepcopy(strength)},'required':required,'additionalProperties':False}}})
    return result

def attach_discovery_tools(network,owner):
    discovered=set()
    def discover(target_node_id,scope='network',strength=0):
        result=list_tools(network,owner.node_id,target_node_id,scope,strength)
        if result.status=='ok':discovered.update((target_node_id,item['name']) for item in result.items)
        return result
    def invoke(target_node_id,tool_name,arguments,scope='network',strength=0):
        if (target_node_id,tool_name) not in discovered:return NodeResult(status='forbidden',errors=['请先通过list_tools发现目标工具'])
        return invoke_tool(network,owner.node_id,target_node_id,tool_name,arguments,scope,strength)
    owner.tools.update({'list_nodes':lambda scope='network',strength=0,channels=():list_nodes(network,owner.node_id,scope,strength,channels),'list_tools':discover,'invoke_tool':invoke})
    return discovery_definitions()
