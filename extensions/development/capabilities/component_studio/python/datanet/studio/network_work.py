"""网络制作副本只输出当前成品格式，不执行生成的启动代码。"""
import json
from .assembly import assemble_document
from datanet.core.serialization import _build

def validate_execution(node,backend,*,allow_missing=False):
    """在制作阶段检查宿主执行配置，避免只有图结构合法却无法启动。"""
    binding=node.execution_binding
    if not binding:return
    if binding.get('executor')!='harness':raise ValueError('此制作宿主只支持 executor=harness')
    if node.signal_type!='agent':raise ValueError('只有 Agent 节点可以绑定 Harness 执行器')
    if set(binding)-{'executor','strength','channels','max_steps','timeout_seconds','prepare'}:raise ValueError('Harness执行配置只支持executor/strength/channels/max_steps/timeout_seconds/prepare')
    strength=binding.get('strength',0)
    if type(strength) not in (int,float) or not 0<=strength<=32:raise ValueError('执行器strength须为0至32')
    channels=binding.get('channels',[])
    if not isinstance(channels,list) or any(not isinstance(c,str) or not c for c in channels) or len(set(channels))!=len(channels):raise ValueError('执行器channels须为唯一非空字符串列表')
    if type(binding.get('max_steps',12)) is not int or not 1<=binding.get('max_steps',12)<=100:raise ValueError('执行器max_steps须为1至100')
    timeout=binding.get('timeout_seconds',90)
    if type(timeout) not in (int,float) or not 1<=timeout<=600:raise ValueError('执行器timeout_seconds须为1至600')
    prepare=binding.get('prepare',[])
    if not isinstance(prepare,list):raise ValueError('execution.prepare须为操作对象数组，不是true或单个对象')
    for item in prepare:
        if not isinstance(item,dict) or set(item)-{'node','module','operation','arguments'} or not {'module','operation'}<=set(item):raise ValueError('prepare每项声明module/operation/arguments')
        if item.get('node',node.node_id)!=node.node_id:raise ValueError('上下文准备只能调用本节点模块')
        module=item['module'];operation=item['operation']
        if module not in node.modules:raise ValueError('prepare引用未装配的本地模块：'+str(module))
        definition=backend.components.module_types.get(module)
        if definition is None and allow_missing:continue
        if definition is None or operation not in definition.operations:raise ValueError('prepare引用未知模块操作')
        definition.validate(item.get('arguments',{}),definition.operations[operation]['parameters'])

def validate_network(document,backend,library,*,allow_missing=False):
    if not isinstance(document,dict) or set(document)!={'network','files'}:raise ValueError('预设使用 {network, files} 成品格式')
    if allow_missing:library={k:v for k,v in library.items() if k in backend.components.module_types}
    document=assemble_document(document,library,backend.components.module_types,allow_missing=allow_missing)
    candidate=_build(document['network'],backend.directory)
    for node in candidate.nodes.values():
        validate_execution(node,backend,allow_missing=allow_missing)
        from datanet.core.node_toolboxes import validate_exposure
        validate_exposure(node)
        backend.external_tools.validate_node(node)
        if hasattr(node,'file_path') and not node.file_path.is_relative_to(backend.directory):raise ValueError('文档路径必须在网络工作目录内')
        for name,spec in node.modules.items():
            definition=backend.components.module_types.get(name)
            if definition is None:
                if allow_missing:continue
                raise ValueError('未发布或未登记模块：'+name)
            if node.signal_type not in definition.node_types:
                if allow_missing:continue
                raise ValueError('模块不支持节点类型：'+name)
            try:definition.validate(spec['config'],definition.config_schema);definition.validate(spec['state'],definition.state_schema)
            except Exception:
                if not allow_missing:raise
    from datanet.core.component_registry import resource_roots
    for node in candidate.nodes.values():
        for _,path,_ in resource_roots(node):
            if not path.is_relative_to(backend.directory):raise ValueError('节点数据必须在网络工作目录内')
    from datanet.core.resource_data import decode_data
    for name,content in document['files'].items():
        if not (backend.directory/name).resolve().is_relative_to(backend.directory):raise ValueError('资源必须在网络目录内')
        decode_data(content)
    return document

def check_work(folder,backend,library,workspace=None):
    document=json.loads((folder/'network.json').read_text(encoding='utf-8'))
    scoped=getattr(backend,'network_administrator',None)
    if scoped and scoped.has(workspace or folder.name):document=scoped.check(workspace or folder.name,document)
    document=validate_network(document,backend,library)
    return dict(valid=True,nodes=len(document['network']['nodes']),document=document)
