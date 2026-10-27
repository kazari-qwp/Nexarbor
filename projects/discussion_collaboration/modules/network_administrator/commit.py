"""原局部提交：保留边界出边和运行对象，只替换获准的局部配置。"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from app.persistence.resource_data import decode_data,read_bytes
from app.studio.service import read_json
from .scope import OFFICIAL,remap,execution_refs,remap_tools,fingerprint,configuration_version

async def apply(service,actor,task):
    backend=service.backend;scope=service.task(actor,task);receipt=backend.extension_state.get('admin_receipts',{}).get(scope['workspace'])
    if receipt:return {**receipt,'duplicate':True}
    job=await service.host('status',dict(task=task))
    if job['status']!='completed':raise ValueError('制作尚未成功完成，不能提交')
    document=service.check(scope['workspace'],read_json(service.studio.folder(scope['workspace'])/'network.json',{}))
    def validate():
        current=service.capture(service.module(actor),scope['aliases'])
        if current['policy']!=scope['policy']:raise PermissionError('管理员授权或模式已变化，请重新制作')
        if current['versions']!=scope['versions']:raise ValueError('局部网络配置已经变化，请重新制作，不能覆盖新配置')
        for path,text in document['files'].items():
            if text!=scope['document']['files'].get(path) and current['file_versions'].get(path)!=scope['file_versions'].get(path):raise ValueError('待修改的节点文本已经变化，请重新制作')
    return await backend.node_locks.mutate(list(scope['aliases']),lambda:commit(service,scope,document),validate=validate,timeout=30)


def changed_graph(service):
    if service.studio.graph_changed is not None:service.studio.graph_changed()
    elif service.backend.graph_observer is not None:service.backend.graph_observer()


def commit(service,scope,document):
    with service.backend._transaction_lock:return _commit(service,scope,document)


def _commit(service,scope,document):
    backend=service.backend;original={node['node_id']:node for node in scope['document']['network']['nodes']};draft={node['node_id']:deepcopy(node) for node in document['network']['nodes']}
    reverse={alias:node for node,alias in scope['aliases'].items()};fresh={alias:'admin-'+uuid4().hex for alias in draft if alias not in original};ids={**reverse,**fresh,**scope.get('external_aliases',{})};removed={reverse[alias] for alias in original.keys()-draft.keys()}
    updated=[reverse[alias] for alias in original.keys()&draft.keys() if original[alias]!=draft[alias]]
    if scope['actor'] in removed:raise PermissionError('不能删除正在执行本次修改的管理员')
    properties=backend.extension_state.get('node_properties',{})
    for node in backend.network:
        if node.info.node_id in scope['aliases']:continue
        if any(edge.target_id in removed for edge in node.links) or properties.get(node.info.node_id,{}).get('management_parent_id') in removed:raise PermissionError('节点仍被边界外网络引用，不能删除')
    before={node:backend.network.get(node) for node in scope['aliases']}
    snapshots=backend.node_locks.snapshots
    images={key:snapshots._capture(node,snapshots._root(node)) for key,node in before.items()}
    old_extra={key:deepcopy(backend.extension_state.get(key)) for key in ('node_properties','document_resources','admin_receipts')}
    new_properties={};files={};new_nodes=[];new_mounts=[]
    for alias,node in draft.items():
        node['node_id']=ids[alias];node['execution']=execution_refs(node.get('execution'),ids)
        for edge in node['links']:edge['target_id']=ids[edge['target_id']]
        for mount in node['tables']['modules']:
            spec=service.studio.library[mount['module_id']]['manifest']
            for field in ('config','state'):mount[field]=remap(mount.get(field,{}),spec.get(field+'_schema',{}),ids)
        props=deepcopy(document['network'].get('properties',{}).get(alias,{}))
        props['management_parent_id']=deepcopy(properties.get(ids[alias],{}).get('management_parent_id')) if alias in original else ids.get(props.get('management_parent_id'),scope['actor'])
        remap_tools(service.studio,node,alias,props);new_properties[ids[alias]]=props
        data=node.get('data')
        if data:
            old_path=data['path'];directory=data.get('directory',False);owned={path:value for path,value in document['files'].items() if path==old_path or directory and path.startswith(old_path.rstrip('/')+'/')}
            path=scope['paths'][old_path] if alias in original else 'created/admin/'+node['node_id']+('-data' if directory else Path(old_path).suffix or '.md')
            data['path']=path
            for name,value in owned.items():
                if alias not in original or value!=scope['document']['files'].get(name):files[path+name[len(old_path):]]=value
    file_images={}
    for path,content in files.items():
        target=backend._file(path)
        if target.is_symlink():raise PermissionError('节点文本位置无效')
        previous=read_bytes(target);file_images[path]=previous
        if previous!=decode_data(content):
            for node in backend.network:
                if node.info.node_id in scope['aliases'] or not hasattr(node,'saver'):continue
                root=node.saver.path.resolve()
                if target==root or root.is_dir() and target.is_relative_to(root):raise PermissionError('文本仍被范围外节点共享，不能写入')
    try:
        backend.write_documents(files)
        records=backend.saver.document(backend.network,backend.directory)
        records['nodes']=[entry for entry in records['nodes'] if entry['node_id'] not in removed]
        for entry in records['nodes']:
            if entry['node_id'] not in scope['aliases']:continue
            alias=scope['aliases'][entry['node_id']]
            if alias in draft:entry['links']=[*draft[alias]['links'],*[edge for edge in entry['links'] if edge['target_id'] not in scope['aliases']]]
        records['nodes'].extend(draft[alias] for alias in fresh)
        if service.studio.register_properties is not None:service.studio.register_properties(new_properties)
        candidate=backend.saver.build(records,backend.directory)
        for alias in fresh:
            node=candidate.get(ids[alias]);node._resolve=None;backend.network.add(node);new_nodes.append(node.info.node_id)
            if draft[alias].get('execution') is not None:backend.bindings[node.info.node_id]=deepcopy(draft[alias]['execution'])
        for alias in original.keys()&draft.keys():
            node=before[reverse[alias]];entry=draft[alias]
            if alias!='root':
                wanted={mount['module_id']:mount for mount in entry['tables']['modules']};prior={module.module_id:module for module in node.modules}
                remove={name for name in prior if name not in OFFICIAL and name not in wanted}
                replace={name for name in prior.keys()&wanted.keys() if getattr(prior[name],'config',{})!=wanted[name].get('config',{})}
                if (remove or replace) and backend.node_locks.leases.get(node.info.node_id):raise RuntimeError('正在调用链中执行的节点不能重装模块')
                for name in remove|replace:node.remove(name)
                for name,mount in wanted.items():
                    if node.modules.get(name) is not None:continue
                    state=deepcopy(getattr(prior.get(name),'state',mount.get('state',{})))
                    module=service.studio.modules.mount(node,name,mount.get('config'),state,{field:mount[field] for field in ('channels','strength','channel_mode') if field in mount});new_mounts.append(module)
            node.info.name=entry['name'];node.info.description=entry.get('description','');node.links._links[:]=list(candidate.get(node.info.node_id).links)
        for node_id in removed:
            if backend.node_locks.leases.get(node_id):raise RuntimeError('不能删除调用链中仍在执行的节点')
            backend.network._nodes.pop(node_id)._resolve=None;backend.agents.pop(node_id,None);backend.bindings.pop(node_id,None);properties.pop(node_id,None)
        backend.extension_state.setdefault('node_properties',{}).update(new_properties)
        result=dict(created=list(fresh.values()),node_ids=fresh,updated=updated,deleted=sorted(removed),duplicate=False)
        backend.extension_state.setdefault('admin_receipts',{})[scope['workspace']]=result;changed_graph(service);backend.save()
    except BaseException:
        for module in new_mounts:module._unbind()
        for node_id in new_nodes:
            node=backend.network._nodes.pop(node_id,None)
            if node is not None:node._resolve=None
            backend.agents.pop(node_id,None);backend.bindings.pop(node_id,None)
        for node in before.values():node._resolve=None;backend.network.add(node)
        snapshots.restore(images)
        for node in before.values():
            for module in node.modules:module._access_origin=node
        for key,value in old_extra.items():
            if value is None:backend.extension_state.pop(key,None)
            else:backend.extension_state[key]=value
        for name,content in file_images.items():
            target=backend._file(name)
            if content is None:target.unlink(missing_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        changed_graph(service);raise
    from .service import write_json
    scope['applied']=result;write_json(service.home/(scope['workspace']+'.json'),scope);return result
