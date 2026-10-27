"""宿主登记的固定模板；参数不能更改权限，实例键持久幂等。"""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import re
from jsonschema import Draft202012Validator

from app.persistence.resource_data import read_data, write_data

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
        if item['document']['network'].get('signals') or item['document']['network'].get('delegations'):raise ValueError('模板不能包含运行中的信号或委托许可')
        Draft202012Validator.check_schema(item['arguments_schema'])
        if item['arguments_schema'].get('type')!='object':raise ValueError('模板参数 Schema 必须为 object')
        if not isinstance(item['bindings'],list) or not isinstance(item['attachments'],list):raise ValueError('bindings 和 attachments 必须为列表')
        for binding in item['bindings']:
            if set(binding)!={'path','input'} or not re.fullmatch(r'/network/nodes/\d+/(name|description|tables/modules/\d+/config(?:/[^/]+)*)',binding['path']):raise ValueError('模板替换只允许名称、说明和组件配置')
            if binding['input'].strip('/').split('/')[0] not in item['arguments_schema'].get('properties',{}):raise ValueError('替换引用未声明输入')
        internal={n['node_id'] for n in item['document']['network']['nodes']}
        for attachment in item['attachments']:
            if set(attachment)!={'source','target','metadata'} or attachment['source'] not in node_ids:raise ValueError('模板连接起点必须是预登记的现有节点')
            if attachment['target'] not in internal:raise ValueError('模板连接终点必须为模板内部节点')
        pending[item['id']]=deepcopy(item)
    return pending

class TemplateService:
    def __init__(self, host, definitions=()):
        self.host = host
        self.backend = host.backend
        self.templates = checked_templates(list(definitions), {node.info.node_id for node in self.backend.network})

    def configure(self, templates):
        pending = checked_templates(templates, {node.info.node_id for node in self.backend.network})
        self.templates = pending
        self.backend.extension_state.setdefault('runtime',{})['templates'] = self.definitions()
        return {'templates':list(pending)}

    def definitions(self):
        return deepcopy(list(self.templates.values()))

    def _fragment(self, item, arguments, key):
        document = deepcopy(item['document'])
        for binding in item['bindings']:
            parts = binding['path'].strip('/').split('/');target = document
            for part in parts[:-1]:target = target[int(part)] if isinstance(target,list) else target[part.replace('~1','/').replace('~0','~')]
            value = arguments
            for part in binding['input'].strip('/').split('/'):value = value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
            last = int(parts[-1]) if isinstance(target,list) else parts[-1].replace('~1','/').replace('~0','~')
            target[last] = deepcopy(value)
        prefix = 'instance-' + digest(key)[:20]
        ids = {node['node_id']:prefix+'-'+str(index) for index,node in enumerate(document['network']['nodes'])}
        if any(self.backend.network.get(node_id) is not None for node_id in ids.values()):
            raise ValueError('模板实例编号已存在但回执丢失，请核对存档')
        paths = {};files = {}
        for name, content in document['files'].items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('模板文本路径必须为相对路径')
            paths[name] = 'created/templates/'+prefix+'/'+name
            files[paths[name]] = content
        for node in document['network']['nodes']:
            old_id = node['node_id'];node['node_id'] = ids[old_id]
            data = node.get('data')
            if data is not None:
                if data['path'] not in paths:raise ValueError('模板每个记忆/文本文件都须有独立初始正文')
                data['path'] = paths[data['path']]
            if node.get('agent'):node['agent']['inputs'] = {}
            binding = node.get('execution')
            if binding:
                for reference in binding.get('prepare',[]):
                    if 'node' in reference:reference['node'] = ids.get(reference['node'],reference['node'])
            for edge in node.get('links',[]):edge['target_id'] = ids.get(edge['target_id'],edge['target_id'])
            for module in node.get('tables',{}).get('modules',[]):
                schemas = self.host.module_schemas[module['module_id']]
                for field in ('config','state'):
                    if field in module:module[field] = remap(module[field],schemas.get(field+'_schema',{}),ids)
            self.host.remap_factory_tools(node, old_id,document['network'].get('properties',{}).get(old_id,{}))
        properties = {}
        for node_id, value in document['network'].get('properties',{}).items():
            value = deepcopy(value)
            for field in ('management_parent_id','parent_id'):
                if field in value:value[field] = ids.get(value[field],value[field])
            properties[ids.get(node_id,node_id)] = value
        return document['network']['nodes'], files, ids, properties

    async def instantiate(self, actor, *, template, key, arguments):
        backend = self.backend
        Draft202012Validator(DEFINITION['parameters']).validate(dict(template=template,key=key,arguments=arguments))
        if backend.node_locks.current:raise RuntimeError('请在业务事务提交后实例化模板，并用同key重试恢复')
        item = self.templates.get(template)
        if item is None or actor not in item['callers']:raise PermissionError('当前节点未获准实例化该模板')
        Draft202012Validator(item['arguments_schema']).validate(arguments)
        request = digest(dict(actor=actor,template=item,arguments=arguments));identity = actor+':'+key
        sources = sorted({actor, *(attachment['source'] for attachment in item['attachments'])})
        async with backend.node_locks.access(sources):
            with backend._transaction_lock:
                receipts = backend.extension_state.setdefault('template_receipts',{})
                if identity in receipts:
                    old = receipts[identity]
                    if old['request'] != request:raise ValueError('同一实例键不能改变模板或参数')
                    return {**old['result'],'duplicate':True}
                if len(receipts)>=2000:raise ValueError('模板实例回执达到2000项，请先整理')
                backend.node_locks.lifecycle()
                nodes,files,ids,properties = self._fragment(item,arguments,identity)
                self.host.validate_nodes(nodes)
                old_edges = {source:list(backend.network.get(source).links) for source in sources}
                resources = deepcopy(backend.extension_state.get('document_resources',[]))
                old_properties = deepcopy(backend.extension_state.get('node_properties',{}))
                added = [];old_bindings = deepcopy(backend.bindings)
                previous_files = {name:read_data(backend._file(name)) for name in files}
                try:
                    backend.write_documents(files)
                    combined = backend.saver.document(backend.network,backend.directory)
                    combined['nodes'].extend(nodes)
                    for attachment in item['attachments']:
                        source = next(node for node in combined['nodes'] if node['node_id']==attachment['source'])
                        source['links'].append(self.host.link_record(ids[attachment['target']],attachment['metadata']))
                    self.host.register_properties(properties)
                    candidate = backend.saver.build(combined,backend.directory)
                    for node_id in ids.values():
                        node = candidate.get(node_id);node._resolve = None
                        backend.network.add(node);added.append(node_id)
                    for source in sources:backend.network.get(source).links._links[:] = list(candidate.get(source).links)
                    for node in nodes:
                        if node.get('execution') is not None:backend.bindings[node['node_id']] = deepcopy(node['execution'])
                    backend.extension_state.setdefault('node_properties',{}).update(properties)
                    self.host.graph_changed()
                    result = dict(node_ids=ids,duplicate=False);receipts[identity] = dict(request=request,result=result)
                    backend.save()
                    return result
                except BaseException:
                    receipts.pop(identity,None)
                    for source,edges in old_edges.items():backend.network.get(source).links._links[:] = edges
                    for node_id in added:
                        removed = backend.network._nodes.pop(node_id,None)
                        if removed is not None:removed._resolve = None
                        backend.agents.pop(node_id,None)
                    backend.bindings.clear();backend.bindings.update(old_bindings)
                    backend.extension_state['node_properties'] = old_properties
                    backend.extension_state['document_resources'] = resources
                    for name,content in previous_files.items():
                        path = backend._file(name)
                        if content is None:path.unlink(missing_ok=True)
                        else:write_data(path,content)
                    self.host.graph_changed()
                    raise
