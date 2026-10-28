"""验证当前节点记录的制作产物、附加预设和运行模板。"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from app.runtime.execution_binding import validate_execution_binding
from .assembly import assemble_document

def validate_network(document,backend,library,*,allow_missing=False,port_definitions=None):
    if not isinstance(document,dict) or set(document)!={'network','files'}:raise ValueError('预设使用 {network, files} 成品格式')
    document=assemble_document(document,backend,library,port_definitions=port_definitions,allow_missing=allow_missing)
    definitions={name:release['manifest'] for name,release in library.items()}
    nodes={node['node_id']:node for node in document['network']['nodes']}
    for node in nodes.values():
        if node.get('execution') and node['execution'].get('executor')!='harness':raise ValueError('此制作宿主只支持 executor=harness')
        validate_execution_binding(node,nodes,definitions,allow_missing=allow_missing)
        for item in node.get('tables',{}).get('modules',[]):
            definition=definitions.get(item['module_id'])
            if not allow_missing:
                if definition is None:raise ValueError('模块不可用：'+item['module_id'])
                for field in ('config','state'):Draft202012Validator(definition[field+'_schema']).validate(item.get(field,{}))
    return document

def runtime_settings(folder,backend,document,workspace=None):
    """Host metadata uses the same runtime shape as portable network exports."""
    file=folder/'runtime.json'
    if (folder/'templates.json').exists():raise ValueError('工作副本的 templates.json 不会成为网络成品；固定模板请写 runtime.json 的 templates，普通文本放 network.json.files')
    value=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {'templates':[]}
    if not isinstance(value,dict) or set(value)!={'templates'}:raise ValueError('runtime.json 只接受 {"templates":[...]}')
    if value['templates']:
        scoped=getattr(backend,'network_administrator',None)
        if scoped and scoped.has(workspace or folder.name):raise ValueError('局部管理员副本不能替换整个项目的宿主模板；请在完整网络制作中配置')
        from app.templates.service import checked_templates
        value={'templates':list(checked_templates(value['templates'],{n['node_id'] for n in document['network']['nodes']}).values())}
    elif not isinstance(value['templates'],list):raise ValueError('templates 必须为列表')
    return value

def output_file(folder,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or Path(name).is_absolute() or any(part in ('.','..') for part in name.split('/')):raise ValueError('网络产物使用工作副本内的相对 JSON 路径')
    if Path(name).suffix!='.json' or name.split('/')[0].casefold() in ('reference','dependencies','lessons'):raise ValueError('网络产物必须是自有 JSON 文件')
    target=(folder/name).resolve()
    if not target.is_relative_to(folder.resolve()):raise ValueError('网络产物越出工作副本')
    return target

def additional_outputs(folder,backend,library,*,port_definitions=None):
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
        document=validate_network(json.loads(output_file(folder,file).read_text(encoding='utf-8')),backend,library,port_definitions=port_definitions)
        outputs.append(dict(name=name,file=file,description=description,document=document));names.add(name);files.add(file.casefold())
    return outputs

def check_work(folder,backend,library,workspace=None,*,port_definitions=None):
    document=json.loads((folder/'network.json').read_text(encoding='utf-8'))
    scoped=getattr(backend,'network_administrator',None)
    if scoped and scoped.has(workspace or folder.name):document=scoped.check(workspace or folder.name,document)
    document=validate_network(document,backend,library,port_definitions=port_definitions)
    runtime=runtime_settings(folder,backend,document,workspace)
    if scoped and scoped.has(workspace or folder.name) and (folder/'outputs.json').exists():raise ValueError('局部管理员提交当前网络；附加零件预设在完整网络制作副本中发布')
    outputs=additional_outputs(folder,backend,library,port_definitions=port_definitions)
    from .placement_checks import reference_warnings
    warnings=reference_warnings(document,{name:release['manifest'] for name,release in library.items()})
    for item in outputs:warnings.extend(dict(file=item['file'],**warning) for warning in reference_warnings(item['document'],{name:release['manifest'] for name,release in library.items()}))
    return dict(valid=True,nodes=len(document['network']['nodes']),document=document,runtime=runtime,outputs=outputs,warnings=warnings[:8])
