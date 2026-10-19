"""网络制作副本只输出当前成品格式，不执行生成的启动代码。"""
import json
from .assembly import assemble_document
from datanet.core.serialization import _build

def validate_execution(node,backend,*,allow_missing=False,network=None):
    from datanet.core.execution_binding import validate_execution_binding
    if node.execution_binding and node.execution_binding.get('executor')!='harness':raise ValueError('此制作宿主只支持 executor=harness')
    return validate_execution_binding(node,network or backend.network,backend.components.module_types,allow_missing=allow_missing)

def validate_network(document,backend,library,*,allow_missing=False):
    if not isinstance(document,dict) or set(document)!={'network','files'}:raise ValueError('预设使用 {network, files} 成品格式')
    if allow_missing:library={k:v for k,v in library.items() if k in backend.components.module_types}
    document=assemble_document(document,library,backend.components.module_types,allow_missing=allow_missing)
    candidate=_build(document['network'],backend.directory)
    for node in candidate.nodes.values():
        validate_execution(node,backend,allow_missing=allow_missing,network=candidate)
        from datanet.core.node_toolboxes import validate_exposure
        validate_exposure(node)
        backend.external_tools.validate_node(node)
        if hasattr(node,'file_path') and not node.file_path.is_relative_to(backend.directory):raise ValueError('文档路径必须在网络工作目录内')
        for name,spec in node.modules.items():
            definition=backend.components.module_types.get(name)
            if definition is None:
                if allow_missing:continue
                raise ValueError('未发布或未登记模块：'+name)
            if ('node' if node.signal_type=='subnode' else node.signal_type) not in definition.node_types:
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
