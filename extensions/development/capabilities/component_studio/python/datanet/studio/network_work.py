"""网络制作副本只输出当前成品格式，不执行生成的启动代码。"""
import json
from .assembly import assemble_document
from datanet.core.serialization import _build

def validate_network(document,backend,library):
    if not isinstance(document,dict) or set(document)!={'network','files'}:raise ValueError('预设使用 {network, files} 成品格式')
    document=assemble_document(document,library,backend.components.module_types)
    candidate=_build(document['network'],backend.directory)
    if 'root' not in candidate.nodes:raise ValueError('网络预设需要 root 节点')
    for node in candidate.nodes.values():
        backend.external_tools.validate_node(node)
        if hasattr(node,'file_path') and not node.file_path.is_relative_to(backend.directory):raise ValueError('文档路径必须在网络工作目录内')
        for name,spec in node.modules.items():
            definition=backend.components.module_types.get(name)
            if definition is None:raise ValueError('未发布或未登记模块：'+name)
            if node.signal_type not in definition.node_types:raise ValueError('模块不支持节点类型：'+name)
            definition.validate(spec['config'],definition.config_schema);definition.validate(spec['state'],definition.state_schema)
    for name,content in document['files'].items():
        if not isinstance(content,str) or not (backend.directory/name).resolve().is_relative_to(backend.directory):raise ValueError('文档必须是网络目录内的文本')
    return document

def check_work(folder,backend,library):
    document=validate_network(json.loads((folder/'network.json').read_text(encoding='utf-8')),backend,library)
    return dict(valid=True,nodes=len(document['network']['nodes']),document=document)
