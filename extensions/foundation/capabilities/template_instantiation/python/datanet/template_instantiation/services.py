"""固定模板由应用宿主登记；业务组件不能上传模板或任意代码。"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,re
from jsonschema import Draft202012Validator

DEFINITION=dict(name='instantiate',description='实例化宿主预登记的固定节点模板；参数不会授予其他网络权限。',parameters={'type':'object','properties':{'template':{'type':'string'},'key':{'type':'string','minLength':1,'maxLength':120},'arguments':{'type':'object'}},'required':['template','key','arguments'],'additionalProperties':False})
def digest(value):return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def remap(value,schema,ids):
    if schema.get('format')=='node-id' and isinstance(value,str):return ids.get(value,value)
    if isinstance(value,list):return [remap(v,schema.get('items',{}),ids) for v in value]
    if isinstance(value,dict):return {k:remap(v,schema.get('properties',{}).get(k,schema.get('additionalProperties',{}) if isinstance(schema.get('additionalProperties'),dict) else {}),ids) for k,v in value.items()}
    return value

def checked_templates(items,node_ids):
    """Validate the declaration without mutating a live template registry."""
    if not isinstance(items,list):raise ValueError('templates 必须为列表')
    pending={}
    for item in items:
        if not isinstance(item,dict) or set(item)!={'id','callers','document','arguments_schema','bindings','attachments'}:raise ValueError('模板字段不完整')
        if not re.fullmatch('[a-zA-Z0-9_.-]{1,80}',item['id']) or item['id'] in pending:raise ValueError('模板编号无效或重复')
        if not isinstance(item['callers'],list) or not item['callers'] or any(not isinstance(c,str) or c not in node_ids for c in item['callers']):raise ValueError('模板调用节点必须为已存在节点的非空列表')
        if not isinstance(item['document'],dict) or set(item['document'])!={'network','files'}:raise ValueError('模板 document 必须为 {network,files}')
        if not isinstance(item['document']['network'].get('nodes'),list):raise ValueError('模板 nodes 必须为列表')
        if not 1<=len(item['document']['network']['nodes'])<=16:raise ValueError('模板节点数为1–16')
        if item['document']['network']['signals'] or item['document']['network']['delegations']:raise ValueError('模板不能包含运行中的信号或委托许可')
        Draft202012Validator.check_schema(item['arguments_schema'])
        if item['arguments_schema'].get('type')!='object':raise ValueError('模板参数 Schema 必须为 object')
        if not isinstance(item['bindings'],list) or not isinstance(item['attachments'],list):raise ValueError('bindings 和 attachments 必须为列表')
        for binding in item['bindings']:
            if set(binding)!={'path','input'} or not re.fullmatch(r'/network/nodes/\d+/(name|description|modules/[^/]+/config(?:/[^/]+)*)',binding['path']):raise ValueError('模板替换只允许名称、说明和组件配置')
            if binding['input'].strip('/').split('/')[0] not in item['arguments_schema'].get('properties',{}):raise ValueError('替换引用未声明输入')
        internal={n['node_id'] for n in item['document']['network']['nodes']}
        for attachment in item['attachments']:
            if set(attachment)!={'source','target','metadata'} or attachment['source'] not in node_ids:raise ValueError('模板连接起点必须是预登记的现有节点')
            if attachment['target'] not in internal:raise ValueError('模板连接终点必须为模板内部节点')
        pending[item['id']]=deepcopy(item)
    return pending

def register(services):
    def install(backend):
        templates={}
        def configure(p):
            pending=checked_templates(p['templates'],set(backend.network.nodes))
            templates.clear();templates.update(pending);return dict(templates=list(templates))
        backend.configure_templates=configure
        backend.template_definitions=lambda:deepcopy(list(templates.values()))
        async def execute(actor,name,args):
            if backend.node_locks.current:raise RuntimeError('请在业务事务提交后实例化模板，并用同key重试恢复')
            item=templates.get(args['template'])
            if item is None or actor not in item['callers']:raise PermissionError('当前节点未获准实例化该模板')
            Draft202012Validator(item['arguments_schema']).validate(args['arguments'])
            request=digest(dict(actor=actor,template=item,arguments=args['arguments']));key=actor+':'+args['key']
            sources=sorted({actor,*(a['source'] for a in item['attachments'])})
            async with backend.node_locks.access(sources):
                with backend._transaction_lock:
                    receipts=backend.extension_state.setdefault('template_receipts',{})
                    if key in receipts:
                        old=receipts[key]
                        if old['request']!=request:raise ValueError('同一实例键不能改变模板或参数')
                        return {**old['result'],'duplicate':True}
                    if len(receipts)>=2000:raise ValueError('模板实例回执达到2000项，请先整理')
                    backend.node_locks.lifecycle()
                    document=deepcopy(item['document'])
                    for binding in item['bindings']:
                        parts=binding['path'].strip('/').split('/');target=document
                        for part in parts[:-1]:target=target[int(part)] if isinstance(target,list) else target[part.replace('~1','/').replace('~0','~')]
                        value=args['arguments']
                        for part in binding['input'].strip('/').split('/'):value=value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
                        last=int(parts[-1]) if isinstance(target,list) else parts[-1].replace('~1','/').replace('~0','~');target[last]=deepcopy(value)
                    prefix='instance-'+digest(key)[:20];ids={n['node_id']:prefix+'-'+str(i) for i,n in enumerate(document['network']['nodes'])}
                    if set(ids.values())&backend.network.nodes.keys():raise ValueError('模板实例编号已存在但回执丢失，请核对存档')
                    files={};paths={}
                    for old,text in document['files'].items():
                        if Path(old).is_absolute() or '..' in Path(old).parts:raise ValueError('模板文本路径必须为相对路径')
                        paths[old]='created/templates/'+prefix+'/'+old;files[paths[old]]=text
                    for node in document['network']['nodes']:
                        node['node_id']=ids[node['node_id']];node['context_cursor']=None;node['inputs']=None
                        if node['type']=='subnode':node['parameters']['parent_id']=ids.get(node['parameters'].get('parent_id'),node['parameters'].get('parent_id'))
                        if (node.get('execution') or {}).get('tool_sources'):node['execution']['tool_sources']=[ids.get(id,id) for id in node['execution']['tool_sources']]
                        parent=node.get('management_parent_id');node['management_parent_id']=ids.get(parent,parent)
                        if 'file_path' in node['parameters']:
                            old=node['parameters']['file_path']
                            if old not in paths:raise ValueError('模板每个记忆/文本文件都须有独立初始正文')
                            node['parameters']['file_path']=paths[old]
                        for reference in (node.get('execution') or {}).get('prepare',[]):
                            if 'node' in reference:reference['node']=ids.get(reference['node'],reference['node'])
                        for edge in node['connections']['interfaces']:edge['target_node_id']=ids.get(edge['target_node_id'],edge['target_node_id'])
                        for module,mount in node['modules'].items():
                            spec=backend.studio.library[module]['manifest']
                            for field in ['config','state']:mount[field]=remap(mount[field],spec[field+'_schema'],ids)
                    from datanet.core.serialization import network_document,_build
                    from datanet.studio.network_work import validate_network
                    combined=dict(network=network_document(backend.network,backend.directory),files=files)
                    combined['network']['nodes'].extend(document['network']['nodes'])
                    for attachment in item['attachments']:
                        source=next(n for n in combined['network']['nodes'] if n['node_id']==attachment['source'])
                        if attachment['target'] not in ids:raise ValueError('模板连接终点必须为模板内部节点')
                        source['connections']['interfaces'].append(dict(target_node_id=ids[attachment['target']],metadata=attachment['metadata']))
                    combined=validate_network(combined,backend,backend.studio.library);candidate=_build(combined['network'],backend.directory)
                    old_edges={source:list(backend.network.nodes[source].interfaces) for source in sources};resources=deepcopy(backend.extension_state.get('document_resources',[]));added=[]
                    try:
                        for node_id in ids.values():backend.network.add_node(candidate.nodes[node_id]);added.append(node_id)
                        for source in sources:backend.network.nodes[source].interfaces=list(candidate.nodes[source].interfaces)
                        for node_id in added:
                            node=backend.network.nodes[node_id];mounts=list(node.modules.items());node.modules={}
                            for module,mount in mounts:backend.modules.mount(node_id,module,mount['config'],mount['state'],access=mount['access'])
                        backend.write_documents(files)
                        result=dict(node_ids=ids,duplicate=False);receipts[key]=dict(request=request,result=result)
                        backend.dispatch('save',{});return result
                    except BaseException:
                        receipts.pop(key,None)
                        for source,edges in old_edges.items():backend.network.nodes[source].interfaces=edges
                        for node_id in added:
                            for module in list(backend.network.nodes[node_id].modules):
                                if (node_id,module) in backend.modules.instances:backend.modules.unmount(node_id,module)
                            backend.network.nodes.pop(node_id,None)
                        backend.extension_state['document_resources']=resources
                        raise
        backend.external_tools.register('templates',[DEFINITION],execute)
    services.initializers.append(install)
    services.rpc('templates_register',lambda b,p:b.configure_templates(p))
    services.rpc('templates_catalog',lambda b,p:[dict(**d,channels=['runtime.template']) for d in b.external_tools.catalog() if d['provider']=='templates'])
