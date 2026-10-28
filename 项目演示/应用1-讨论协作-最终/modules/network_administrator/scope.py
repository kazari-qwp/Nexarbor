"""原管理员副本的别名、资源归属和授权边界。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from app.persistence.resource_data import read_data,resource_files
from app.projects.project import Project
from app.studio.network_work import validate_network
from domain.core import DataNode

OFFICIAL={'network.administrator'}

def fingerprint(value):return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def configuration_version(record,properties):
    value=deepcopy(record);value.pop('agent',None);value['tables'].pop('tools',None)
    for mount in value['tables']['modules']:
        for key in ('state','published','tools'):mount.pop(key,None)
    parameters=value.get('parameters',{})
    for key in ('value','state','collection_id'):parameters.pop(key,None)
    return fingerprint(dict(node=value,properties=properties))

def remap(value,schema,ids,external=None):
    if schema.get('format') in ('node-id','node-reference') and isinstance(value,str):return ids.get(value,external(value) if external and value not in ids else value)
    if isinstance(value,list):return [remap(item,schema.get('items',{}),ids,external) for item in value]
    if isinstance(value,dict):return {key:remap(item,schema.get('properties',{}).get(key,schema.get('additionalProperties',{}) if isinstance(schema.get('additionalProperties'),dict) else {}),ids,external) for key,item in value.items()}
    return value

def execution_refs(binding,ids,external=None):
    if not binding:return binding
    result=deepcopy(binding)
    for entry in result.get('prepare',[]):
        if entry.get('node'):entry['node']=ids.get(entry['node'],external(entry['node']) if external and entry['node'] not in ids else entry['node'])
    return result

def remap_tools(studio,node,old_id,properties):
    host=SimpleNamespace(tool_specs={name:release['manifest'].get('agent_tools',[]) for name,release in studio.library.items()})
    Project.remap_factory_tools(host,node,old_id,properties)

def capture(service,module,images,policy):
    actor=module._access_origin.info.node_id;ids=set(images)
    if len(ids)>policy['max_nodes']:raise ValueError('可达节点超过管理员的单次节点上限')
    aliases={actor:'root',**{node:'scope-'+str(index) for index,node in enumerate(sorted(ids-{actor}),1)}}
    nodes=[];properties={};files={};paths={};outside={}
    def mask(value):
        token='outside-'+sha256(value.encode()).hexdigest()[:20];outside[token]=value;return token
    for original in sorted(ids,key=lambda node:aliases[node]):
        image=images[original];node=deepcopy(image['node']);key=aliases[original];node['node_id']=key
        props=deepcopy(image['properties']);props['management_parent_id']=aliases.get(props.get('management_parent_id'),'root') if original!=actor else None
        node['links']=[dict(edge,target_id=aliases[edge['target_id']]) for edge in node['links'] if edge['target_id'] in ids]
        node['execution']=execution_refs(node.get('execution'),aliases,mask);node.pop('agent',None)
        node['tables']['modules']=[mount for mount in node['tables']['modules'] if mount['module_id'] not in OFFICIAL]
        for mount in node['tables']['modules']:
            spec=service.studio.library[mount['module_id']]['manifest']
            for field in ('config','state'):mount[field]=remap(mount.get(field,{}),spec.get(field+'_schema',{}),aliases,mask)
        if original==actor:
            node['type']='node';node.pop('data',None);node.pop('parameters',None);node['execution']=None;node['tables']={'modules':[],'tools':{'group':0,'members':[{'modules':True}]}}
        elif node.get('data'):
            data=node['data'];source=data['path'];kind='directory' if data.get('directory') else 'file'
            alias='data/'+key+('-data' if kind=='directory' else Path(source).suffix or '.md');data['path']=alias;paths[alias]=source
            for name,value in image['files'].items():
                destination=alias+('/'+name[len(source.rstrip('/'))+1:] if kind=='directory' else '')
                files[destination]=value;paths[destination]=name
        remap_tools(service.studio,node,original,props);nodes.append(node);properties[key]=props
    return dict(actor=actor,policy=policy,aliases=aliases,external_aliases=outside,versions={node:configuration_version(image['node'],image['properties']) for node,image in images.items()},paths=paths,file_versions={name:fingerprint(value) for name,value in files.items()},document=dict(network=dict(nodes=nodes,properties=properties),files=files))

def read_node(service,node):
    backend=service.backend;record=backend.saver._encode_node(node,backend.directory,None,'');record['execution']=deepcopy(backend.bindings.get(node.info.node_id));files={}
    if isinstance(node,DataNode):
        root=node.saver.path.resolve()
        if not root.is_relative_to(backend.directory) or root.is_symlink():raise PermissionError('管理员只能复制网络目录内的节点数据')
        for file in resource_files(root):files[file.relative_to(backend.directory).as_posix()]=read_data(file)
    return dict(node=record,properties=deepcopy(backend.extension_state.get('node_properties',{}).get(node.info.node_id,{})),files=files)

def check_new_offers(node,properties,original,channels):
    grants={}
    for entry in original.values():
        for offer in entry.get('offered_ports',[]):grants.setdefault(offer['ref'],set()).update(offer['channels'])
    for offer in properties.get('offered_ports',[]):
        selected=set(offer['channels'])
        if not selected<=set(channels):raise PermissionError('新增工具频道超出管理员授权')
        if offer['ref']=='runtime:agent_run':
            if node['type']!='agent' or not node.get('execution'):raise PermissionError('自身执行端口需要已绑定执行器的Agent')
        elif not selected<=grants.get(offer['ref'],set()):raise PermissionError('新增节点只能复用可见节点已提供的工具与频道')

def tool_signature(tables,root):
    groups={}
    def index(item):
        if not isinstance(item,dict):return
        if 'group' in item:groups[item['group']]=item
        for child in item.get('members',[]):index(child)
    for mount in tables.get('modules',[]):index(mount.get('tools'))
    index(tables.get('tools'));seen={}
    def normalize(item):
        if not isinstance(item,dict):return item
        key=item.get('group',item.get('group_ref'))
        if key is not None:
            if key in seen:return {'group_ref':seen[key]}
            seen[key]=len(seen);group=groups[key]
            return {'group':seen[key],'members':[normalize(child) for child in group['members']]}
        return deepcopy(item)
    return normalize(root)

def check(service,workspace,document):
    scope=service.record(workspace)
    if scope.get('role')!='network':return document
    policy=scope['policy'];original={node['node_id']:node for node in scope['document']['network']['nodes']};old_properties=scope['document']['network']['properties']
    if 'repeat_unit_count' in document.get('network',{}):
        from app.studio.preset_repetition import expand_snapshot
        expanded=expand_snapshot(dict(**document['network'],files=document['files']),definitions={name:release['manifest'] for name,release in service.studio.library.items()})
        document=dict(network={key:value for key,value in expanded.items() if key!='files'},files=expanded['files'])
    document=validate_network(deepcopy(document),service.backend,service.studio.library,port_definitions=service.studio.ports)
    graph=document['network'];nodes=graph['nodes'];ids={node['node_id'] for node in nodes};properties=graph.get('properties',{})
    if len(ids)!=len(nodes) or len(nodes)>policy['max_nodes']:raise ValueError('局部网络节点重复或超过上限')
    if graph.get('signals') or graph.get('delegations'):raise PermissionError('草稿不能带运行信号或全局委托许可')
    if 'root' not in ids:raise PermissionError('不能删除管理员锚点')
    for node in nodes:
        key=node['node_id'];old=original.get(key)
        if any(edge['target_id'] not in ids for edge in node['links']):raise PermissionError('出边不能指向局部副本之外的节点')
        mounts={mount['module_id']:mount for mount in node['tables']['modules']}
        if old:
            allowed={'name','description','links'}|({'tables'} if key!='root' else set())
            if any(node.get(name)!=value for name,value in old.items() if name not in allowed) or properties.get(key,{})!=old_properties[key]:raise PermissionError('已有节点只能调整名称、说明、可见连接和普通模块配置')
            if tool_signature(node['tables'],node['tables'].get('tools'))!=tool_signature(old['tables'],old['tables'].get('tools')):raise PermissionError('已有工具表与授权只读')
            prior={mount['module_id']:mount for mount in old['tables']['modules']}
            for name,mount in mounts.items():
                previous=prior.get(name)
                if previous and (any(mount.get(field)!=previous.get(field) for field in ('state','channels','strength','channel_mode','modules')) or tool_signature(node['tables'],mount.get('tools'))!=tool_signature(old['tables'],previous.get('tools'))):raise PermissionError('不能覆盖已有组件状态或授权')
        else:
            if key.startswith('outside-'):raise PermissionError('外部引用标记不能用作新增节点编号')
            if node.get('agent',{}).get('inputs'):raise PermissionError('新增节点不能继承会话、上下文或执行身份')
            embedding=node.get('data',{}).get('parameters',{}).get('embedding')
            if embedding and not any(embedding==entry.get('data',{}).get('parameters',{}).get('embedding') for entry in original.values()):raise PermissionError('新增节点只能复用可见节点已配置的嵌入模型')
            check_new_offers(node,properties.get(key,{}),old_properties,policy['channels'])
            binding=node.get('execution') or {}
            if binding.get('strength',0)>policy['strength'] or not set(binding.get('channels',[]))<=set(policy['channels']):raise PermissionError('新增Agent执行范围不能扩大授权')
            if node['type']=='pulse' and (node['parameters'].get('strength',0)>policy['strength'] or not set(node['parameters'].get('channels',[]))<=set(policy['channels'])):raise PermissionError('脉冲不能扩大传播授权')
        for edge in node['links']:
            if (not old or edge not in old['links']) and not set(edge['channels'])<=set(policy['channels']):raise PermissionError('新增连接频道超出管理员授权')
        prior={mount['module_id'] for mount in old['tables']['modules']} if old else set()
        for name,mount in mounts.items():
            if name in OFFICIAL:raise PermissionError('不能装配官方越权模块')
            if name not in prior and (mount['strength']>policy['strength'] or not set(mount['channels'])<=set(policy['channels'])):raise PermissionError('新增模块不能扩大授权')
    for name in document['files']:
        if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or chr(92) in name:raise PermissionError('草稿文本必须使用副本内相对路径')
    roots=[node['data'] for node in nodes if node.get('data')]
    if any(not any(name==data['path'] or data.get('directory') and name.startswith(data['path'].rstrip('/')+'/') for data in roots) for name in document['files']):raise PermissionError('不能写入不属于局部节点的文件')
    if any(not node['data'].get('directory') and node['data']['path'] not in document['files'] for node in nodes if node['node_id'] not in original and node.get('data')):raise ValueError('新增文本节点和Agent必须提供独立初始正文')
    return document
