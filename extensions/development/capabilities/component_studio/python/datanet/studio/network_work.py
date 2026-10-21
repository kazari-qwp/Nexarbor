"""网络制作副本只输出当前成品格式，不执行生成的启动代码。"""
import json
from pathlib import Path
from .assembly import assemble_document
from datanet.core.serialization import _build

def runtime_settings(folder,backend,document,workspace=None):
    """Host metadata uses the same runtime shape as portable network exports."""
    file=folder/'runtime.json'
    if (folder/'templates.json').exists():raise ValueError('工作副本的 templates.json 不会成为网络成品；固定模板请写 runtime.json 的 templates，普通文本放 network.json.files')
    value=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {'templates':[]}
    if not isinstance(value,dict) or set(value)!={'templates'}:raise ValueError('runtime.json 只接受 {"templates":[...]}')
    if value['templates']:
        scoped=getattr(backend,'network_administrator',None)
        if scoped and scoped.has(workspace or folder.name):raise ValueError('局部管理员副本不能替换整个项目的宿主模板；请在完整网络制作中配置')
        if not hasattr(backend,'template_definitions'):raise ValueError('当前宿主未加载固定模板能力')
        from datanet.template_instantiation.services import checked_templates
        value={'templates':list(checked_templates(value['templates'],{n['node_id'] for n in document['network']['nodes']}).values())}
    elif not isinstance(value['templates'],list):raise ValueError('templates 必须为列表')
    return dict(components=['capabilities/template_instantiation'] if value['templates'] else [],**value)

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
        if node.signal_type!='text_file' and hasattr(node,'file_path') and not node.file_path.is_relative_to(backend.directory):raise ValueError('文档路径必须在网络工作目录内')
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
            if node.signal_type!='text_file' and not path.is_relative_to(backend.directory):raise ValueError('节点数据必须在网络工作目录内')
    from datanet.core.resource_data import decode_data
    for name,content in document['files'].items():
        if not (backend.directory/name).resolve().is_relative_to(backend.directory):raise ValueError('资源必须在网络目录内')
        decode_data(content)
    return document

def output_file(folder,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or Path(name).is_absolute() or any(part in ('.','..') for part in name.split('/')):raise ValueError('网络产物使用工作副本内的相对 JSON 路径')
    if Path(name).suffix!='.json' or name.split('/')[0].casefold() in ('reference','dependencies','lessons'):raise ValueError('网络产物必须是自有 JSON 文件')
    target=(folder/name).resolve()
    if not target.is_relative_to(folder.resolve()):raise ValueError('网络产物越出工作副本')
    return target

def additional_outputs(folder,backend,library):
    manifest=folder/'outputs.json'
    if not manifest.exists():return []
    value=json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or set(value)!={'outputs'} or not isinstance(value['outputs'],list) or not 1<=len(value['outputs'])<=12:raise ValueError('outputs.json 使用 {"outputs":[{"name":...,"file":...}]}，最多12项')
    outputs=[];names=set();files=set()
    for item in value['outputs']:
        if not isinstance(item,dict) or set(item)-{'name','file','description'} or not {'name','file'}<=set(item):raise ValueError('每项网络产物声明 name/file，可选 description')
        name=item['name'];file=item['file'];description=item.get('description','')
        if not isinstance(name,str) or not name.strip() or len(name)>160 or name in names or not isinstance(description,str) or len(description)>2000:raise ValueError('产物名称须非空且唯一，说明不超过2000字')
        if not isinstance(file,str) or len(file)>200 or file.casefold() in files or file.casefold() in ('network.json','runtime.json','outputs.json'):raise ValueError('附加产物文件须独立且唯一')
        document=validate_network(json.loads(output_file(folder,file).read_text(encoding='utf-8')),backend,library)
        outputs.append(dict(name=name,file=file,description=description,document=document));names.add(name);files.add(file.casefold())
    return outputs

def check_work(folder,backend,library,workspace=None):
    document=json.loads((folder/'network.json').read_text(encoding='utf-8'))
    scoped=getattr(backend,'network_administrator',None)
    if scoped and scoped.has(workspace or folder.name):document=scoped.check(workspace or folder.name,document)
    document=validate_network(document,backend,library)
    runtime=runtime_settings(folder,backend,document,workspace)
    if scoped and scoped.has(workspace or folder.name) and (folder/'outputs.json').exists():raise ValueError('局部管理员提交当前网络；附加零件预设在完整网络制作副本中发布')
    outputs=additional_outputs(folder,backend,library)
    from .placement_checks import reference_warnings
    warnings=reference_warnings(document,backend.components.module_types)
    for item in outputs:warnings.extend(dict(file=item['file'],**warning) for warning in reference_warnings(item['document'],backend.components.module_types))
    return dict(valid=True,nodes=len(document['network']['nodes']),document=document,runtime=runtime,outputs=outputs,warnings=warnings[:8])
