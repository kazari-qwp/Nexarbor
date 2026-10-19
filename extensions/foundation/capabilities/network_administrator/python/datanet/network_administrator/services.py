"""官方局部网络管理员：模型只得到可达副本，提交重新验证权限和版本。"""
import asyncio
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import re
import time
from pathlib import Path
from uuid import uuid4
from datanet.core.json_values import thaw
from datanet.core.component_registry import codec_for_node,codecs,active_codecs,resource_roots,resource_paths
from datanet.core.resource_data import read_data,decode_data
from datanet.core.execution import encode_execution
from datanet.core.serialization import _build
from datanet.core.management import validate_management
from datanet.studio.service import read_json,write_json as _write_json
from datanet.studio.network_work import validate_network
from datanet.studio.assembly import assemble_document

def write_json(path,value):
    # Windows读取者或文件扫描器短暂占用时，原子替换允许有限重试。
    for attempt in range(6):
        try:return _write_json(path,value)
        except PermissionError:
            if attempt==5:raise
            time.sleep(.02*(attempt+1))

MODULE='network.administrator'
def fingerprint(value):return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def configuration_version(record):
    value=deepcopy(record)
    for mount in value['modules'].values():mount.pop('state',None)
    # 本次不编辑已有节点参数；只固定文本资源归属，运行数据继续由原节点拥有。
    value['parameters']={k:v for k,v in value['parameters'].items() if k not in ('value','state','collection_id')}
    return fingerprint(value)
def remap(value,schema,ids,external=None):
    if schema.get('format')=='node-id' and isinstance(value,str):return ids.get(value,external(value) if external and value not in ids else value)
    if isinstance(value,list):return [remap(v,schema.get('items',{}),ids,external) for v in value]
    if isinstance(value,dict):return {k:remap(v,schema.get('properties',{}).get(k,schema.get('additionalProperties',{}) if isinstance(schema.get('additionalProperties'),dict) else {}),ids,external) for k,v in value.items()}
    return value

def data_roots(entry):
    codec=codecs()[entry['type']];params=entry['parameters']
    return [(label,params[label],'file') for label in codec.resources]+[(label,params[label],'directory') for label in codec.resource_directories]

class Administrator:
    def __init__(self,backend):
        self.backend=backend;self.studio=backend.studio;self.home=self.studio.root/'admin-scopes';self.jobs_locks={}
        self.home.mkdir(exist_ok=True)
    def has(self,workspace):
        return bool(isinstance(workspace,str) and re.fullmatch(r'module-[A-Za-z0-9_-]{1,80}',workspace) and (self.home/(workspace+'.json')).is_file())
    def record(self,workspace):
        if not self.has(workspace):raise PermissionError('不是局部管理员的制作副本')
        return read_json(self.home/(workspace+'.json'),{})
    def source(self,workspace):return deepcopy(self.record(workspace)['document'])
    def workspace(self,p):
        if not self.has(p['id']):return None
        r=self.record(p['id']);return dict(scoped=True,allow_component_creation=r['policy']['allow_component_creation'],actor=r['actor'],role=r.get('role','network'))
    def policy(self,actor):
        b=self.backend;instance=b.modules._check((actor,MODULE));grant=thaw(b.modules._access[(actor,MODULE)]);policy=grant.get('extension',{})
        if 'manage' not in policy.get('operations',[]) or not ({actor,'$self'} & set(policy.get('targets',[]))):raise PermissionError('管理员必须显式获得自己的官方管理端口')
        config=thaw(instance.config)
        return dict(strength=grant['strength'],channels=grant['channels'],allow_component_creation=config.get('allow_component_creation',False),max_nodes=config.get('max_nodes',40),timeout_seconds=config.get('timeout_seconds',600),grant=grant)
    def reached(self,actor,policy):return {n.node_id for n,_,_ in self.backend.network.walk_states(actor,strength=policy['strength'],channels=policy['channels'])}
    def raw(self,node):
        return dict(type=node.signal_type,node_id=node.node_id,name=node.name,description=node.description,management_parent_id=node.management_parent_id,divergence=node.divergence,data_kind=node.data_kind,parameters=codec_for_node(node).encode(node,self.backend.directory),connections=dict(interfaces=[asdict(e) for e in node.interfaces]),agent=encode_execution(node,self.backend.directory),modules=deepcopy(node.modules),offered_tools=deepcopy(node.offered_tools),toolboxes=deepcopy(node.toolboxes),expose=list(node.expose),execution=deepcopy(node.execution_binding),inputs=None,context_cursor=None)
    def capture(self,actor,expected=None):
        b=self.backend;policy=self.policy(actor);ids=self.reached(actor,policy)
        if expected is not None and ids!=set(expected):raise PermissionError('管理员可达范围已经变化，请重新制作')
        if len(ids)>policy['max_nodes']:raise ValueError('可达节点超过管理员的单次节点上限')
        aliases={actor:'root',**{n:'scope-'+str(i) for i,n in enumerate(sorted(ids-{actor}),1)}}
        raw={n:self.raw(b.network.nodes[n]) for n in sorted(ids)};doc=[];files={};paths={};outside={}
        def mask(value):
            token='outside-'+sha256(value.encode()).hexdigest()[:20];outside[token]=value;return token
        for n in sorted(ids,key=lambda n:aliases[n]):
            node=deepcopy(raw[n]);node['node_id']=aliases[n];node['management_parent_id']=aliases.get(node['management_parent_id'],'root') if n!=actor else None
            node['connections']['interfaces']=[dict(target_node_id=aliases[e['target_node_id']],metadata=e['metadata']) for e in node['connections']['interfaces'] if e['target_node_id'] in ids]
            node['offered_tools']=[];node['toolboxes']=[];node['expose']=[];node['agent']=None
            node['modules']={name:mount for name,mount in node['modules'].items() if name not in b.components.module_extensions}
            for name,mount in node['modules'].items():
                definition=b.components.module_types[name]
                for field in ('config','state'):mount[field]=remap(mount[field],getattr(definition,field+'_schema'),aliases,mask)
            if n==actor:node.update(type='node',parameters={},modules={},execution=None)
            else:
                source=b.network.nodes[n]
                for label,path,kind in resource_roots(source):
                    if not path.is_relative_to(b.directory.resolve()) or path.is_symlink():raise PermissionError('管理员只能复制网络目录内的节点数据')
                    alias='data/'+aliases[n]+(Path(path).suffix or '.md') if kind=='file' else 'data/'+aliases[n]+'-'+label
                    node['parameters'][label]=alias;paths[alias]=path.relative_to(b.directory).as_posix()
                    for _,_,file in resource_paths(source):
                        if file==path or kind=='directory' and file.is_relative_to(path):
                            name=alias+('/'+file.relative_to(path).as_posix() if kind=='directory' else '')
                            files[name]=read_data(file);paths[name]=file.relative_to(b.directory).as_posix()
            doc.append(node)
        return dict(actor=actor,policy=policy,aliases=aliases,external_aliases=outside,versions={n:configuration_version(v) for n,v in raw.items()},paths=paths,file_versions={a:fingerprint(t) for a,t in files.items()},document=dict(network=dict(version=8,nodes=doc,signals={},delegations=[]),files=files))
    async def inspect(self,actor):
        b=self.backend
        while True:
            ids=self.reached(actor,self.policy(actor))
            async with b.node_locks.access(ids,mutable=False):
                with b._transaction_lock:
                    if ids!=self.reached(actor,self.policy(actor)):continue
                    return self.capture(actor)
    async def host(self,method,p):
        if not hasattr(self.backend,'studio_executor'):raise RuntimeError('当前宿主尚未配置网络制作运行器')
        return await asyncio.to_thread(self.backend.studio_executor.transport.host,'network-admin-'+method,p)
    async def build(self,actor,args):
        async with self.jobs_locks.setdefault(actor,asyncio.Lock()):return await self._build(actor,args)
    async def _build(self,actor,args):
        scope=await self.inspect(actor);keyfile=self.home/('keys-'+sha256(actor.encode()).hexdigest()+'.json');keys=read_json(keyfile,{})
        if args['key'] in keys:
            old=keys[args['key']]
            if old['requirement']!=args['requirement']:raise ValueError('相同制作键不能改变需求')
            if not old.get('task'):raise RuntimeError('上次启动未完成，请换一个制作键')
            return dict(task=old['task'],workspace=old['workspace'],duplicate=True)
        if len(keys)>=200:raise ValueError('管理员已保留200项制作任务，请先整理')
        workspace=self.studio.create(dict(kind='network',sample='blank',name='局部网络 · '+self.backend.network.nodes[actor].name));id=workspace['id'];scope.update(workspace=id,role='network')
        write_json(self.home/(id+'.json'),scope);write_json(self.studio.folder(id)/'network.json',scope['document'])
        text='# 局部管理员制作流程\nroot 是管理员所在节点的锚点，不是全网根节点。先读 network.json。保留已有编号；新节点用新局部编号。\n已有节点只修改名称、说明、可见出边和普通模块配置；保留状态、权限、类型、文件位置、执行绑定。root 只修改名称、说明、出边。\n新增模块和Agent的强度、频道不能超过下列授权。禁止装配外部工具和官方越权模块。文本只属于副本节点。\n测试在副本中进行，模型和外部副作用禁用；完成后由宿主重新检查可达性和版本再提交。\n授权：'+json.dumps(scope['policy'],ensure_ascii=False)
        ref=self.studio.folder(id)/'reference';ref.mkdir(exist_ok=True);(ref/'局部网络说明.md').write_text(text,encoding='utf-8')
        keys[args['key']]=dict(requirement=args['requirement'],workspace=id,task=None);write_json(keyfile,keys)
        try:
            job=await self.host('start',dict(id=id,name='局部网络管理员',requirement=args['requirement'],allow_component_creation=scope['policy']['allow_component_creation'],allow_network_testing=True,auto_publish=False,timeout=scope['policy']['timeout_seconds'],max_steps=90))
            scope['task']=job['id'];write_json(self.home/(id+'.json'),scope);keys[args['key']]['task']=job['id'];write_json(keyfile,keys)
        except BaseException:keys.pop(args['key'],None);write_json(keyfile,keys);raise
        return dict(task=job['id'],workspace=id,status=job['status'],mode='允许制作组件' if scope['policy']['allow_component_creation'] else '仅组装已有组件',duplicate=False)
    def task(self,actor,task):
        for file in self.home.glob('module-*.json'):
            r=read_json(file,{})
            if r.get('task')==task and r['actor']==actor and r.get('role')=='network':return r
        raise PermissionError('任务不属于这个管理员')
    def bind_child(self,p):
        parent=self.record(p['parent'])
        if not parent['policy']['allow_component_creation'] or not self.policy(parent['actor'])['allow_component_creation']:raise PermissionError('当前管理员禁止委托制作组件')
        child=deepcopy(parent);child.update(workspace=p['id'],role='component');child.pop('task',None);write_json(self.home/(p['id']+'.json'),child);return dict(bound=True)
    def check(self,workspace,document):
        scope=self.record(workspace)
        if scope.get('role')!='network':return document
        p=scope['policy'];original={n['node_id']:n for n in scope['document']['network']['nodes']};document=assemble_document(deepcopy(document),self.studio.library,self.backend.components.module_types)
        graph=document.get('network',{});nodes=graph.get('nodes',[]);ids={n['node_id'] for n in nodes}
        if len(ids)!=len(nodes) or len(nodes)>p['max_nodes']:raise ValueError('局部网络节点重复或超过上限')
        if graph.get('signals') or graph.get('delegations'):raise PermissionError('草稿不能带运行信号或全局委托许可')
        if 'root' not in ids:raise PermissionError('不能删除管理员锚点')
        for node in nodes:
            key=node['node_id'];old=original.get(key)
            if any(e['target_node_id'] not in ids for e in node['connections']['interfaces']):raise PermissionError('出边不能指向局部副本之外的节点')
            if old:
                allowed={'name','description','connections'}|({'modules'} if key!='root' else set())
                if any(node.get(k)!=v for k,v in old.items() if k not in allowed):raise PermissionError('已有节点只能调整名称、说明、可见连接和普通模块配置')
                for name,mount in node['modules'].items():
                    prior=old['modules'].get(name)
                    if prior and any(mount[f]!=prior[f] for f in ('state','access')):raise PermissionError('不能覆盖已有组件状态或授权')
            else:
                if key.startswith('outside-'):raise PermissionError('外部引用标记不能用作新增节点编号')
                if node['type'] not in active_codecs() or node.get('agent') or node.get('inputs') or node.get('context_cursor'):raise PermissionError('新增节点不能继承会话、上下文或执行身份')
                embedding=node.get('parameters',{}).get('embedding')
                if embedding and not any(embedding==entry.get('parameters',{}).get('embedding') for entry in original.values()):raise PermissionError('新增节点只能复用可见节点已配置的嵌入模型')
                if node.get('offered_tools') or node.get('toolboxes') or node.get('expose'):raise PermissionError('不能授予外部工具；请使用普通模块携带工具')
                binding=node.get('execution') or {}
                if binding.get('strength',0)>p['strength'] or not set(binding.get('channels',[]))<=set(p['channels']):raise PermissionError('新增Agent执行范围不能扩大授权')
                if node['type']=='pulse' and (node['parameters'].get('strength',0)>p['strength'] or not set(node['parameters'].get('channels',[]))<=set(p['channels'])):raise PermissionError('脉冲不能扩大传播授权')
            for edge in node['connections']['interfaces']:
                if not old or edge not in old['connections']['interfaces']:
                    if not set(edge['metadata']['channels'])<=set(p['channels']):raise PermissionError('新增连接频道超出管理员授权')
            for name,mount in node['modules'].items():
                if name in self.backend.components.module_extensions:raise PermissionError('不能装配官方越权模块')
                if not old or name not in old['modules']:
                    access=mount['access']
                    if access.get('extension') or access['strength']>p['strength'] or not set(access['channels'])<=set(p['channels']):raise PermissionError('新增模块不能扩大授权')
        for name in document.get('files',{}):
            if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or chr(92) in name:raise PermissionError('草稿文本必须使用副本内相对路径')
        roots=[(path,kind) for node in nodes for _,path,kind in data_roots(node)]
        if any(not any(name==path or kind=='directory' and name.startswith(path.rstrip('/')+'/') for path,kind in roots) for name in document['files']):raise PermissionError('不能写入不属于局部节点的文件')
        if any(n['parameters']['file_path'] not in document['files'] for n in nodes if n['node_id'] not in original and 'file_path' in n['parameters']):raise ValueError('新增文本节点和Agent必须提供独立初始正文')
        return document
    async def apply(self,actor,task):
        async with self.jobs_locks.setdefault(actor,asyncio.Lock()):return await self._apply(actor,task)
    async def _apply(self,actor,task):
        scope=self.task(actor,task);receipt=self.backend.extension_state.get('admin_receipts',{}).get(scope['workspace'])
        if receipt:return {**receipt,'duplicate':True}
        job=await self.host('status',dict(task=task))
        if job['status']!='completed':raise ValueError('制作尚未成功完成，不能提交')
        id=scope['workspace'];document=self.check(id,read_json(self.studio.folder(id)/'network.json',{}));document=validate_network(document,self.backend,self.studio.library)
        def validate():
            current=self.capture(actor,scope['aliases'])
            if current['policy']!=scope['policy']:raise PermissionError('管理员授权或模式已变化，请重新制作')
            if current['versions']!=scope['versions']:raise ValueError('局部网络配置已经变化，请重新制作，不能覆盖新配置')
            for path,text in document['files'].items():
                if text!=scope['document']['files'].get(path) and current['file_versions'].get(path)!=scope['file_versions'].get(path):raise ValueError('待修改的节点文本已经变化，请重新制作')
        return await self.backend.node_locks.mutate(list(scope['aliases']),lambda:self.commit(scope,document),validate=validate,timeout=30)
    def commit(self,scope,document):
        b=self.backend;original={n['node_id']:n for n in scope['document']['network']['nodes']};draft={n['node_id']:deepcopy(n) for n in document['network']['nodes']}
        reverse={a:n for n,a in scope['aliases'].items()};fresh={a:'admin-'+uuid4().hex for a in draft if a not in original};ids={**reverse,**fresh,**scope.get('external_aliases',{})};removed={reverse[a] for a in original.keys()-draft.keys()}
        updated=[reverse[a] for a in original.keys()&draft.keys() if original[a]!=draft[a]]
        if scope['actor'] in removed:raise PermissionError('不能删除正在执行本次修改的管理员')
        if any(any(e.target_node_id in removed for e in n.interfaces) or n.management_parent_id in removed for k,n in b.network.nodes.items() if k not in scope['aliases']):raise PermissionError('节点仍被边界外网络引用，不能删除')
        if any(source in removed or set(targets)&removed for source,targets in b.network.delegation_permissions.items()):raise PermissionError('节点仍被委托许可引用，不能删除')
        oldbindings=deepcopy(b.agents)
        before={n:b.network.nodes[n] for n in scope['aliases']};oldattrs={n:dict(name=v.name,description=v.description,interfaces=list(v.interfaces)) for n,v in before.items()};oldmodules={n:deepcopy(v.modules) for n,v in before.items()}
        published=deepcopy(b.modules._published);resources=deepcopy(b.extension_state.get('document_resources',[]));file_images={};changed=set();new_nodes=[];files={}
        for alias,node in draft.items():
            old_path=node['parameters'].get('file_path');node['node_id']=ids[alias]
            node['management_parent_id']=before[ids[alias]].management_parent_id if alias in original else ids.get(node.get('management_parent_id'),scope['actor'])
            for edge in node['connections']['interfaces']:edge['target_node_id']=ids[edge['target_node_id']]
            for name,mount in node['modules'].items():
                definition=b.components.module_types[name]
                for field in ('config','state'):mount[field]=remap(mount[field],getattr(definition,field+'_schema'),ids)
            for label,old_path,kind in data_roots(node):
                owned={path:value for path,value in document['files'].items() if path==old_path or kind=='directory' and path.startswith(old_path.rstrip('/')+'/')}
                if alias in original:
                    for path,value in owned.items():
                        if value!=scope['document']['files'].get(path):files[scope['paths'][old_path]+path[len(old_path):]]=value
                else:
                    path='created/admin/'+node['node_id']+('.md' if label=='file_path' and kind=='file' else '/'+label+('/'+Path(old_path).name if kind=='file' else ''))
                    node['parameters'][label]=path
                    for name,value in owned.items():files[path+name[len(old_path):]]=value
        candidates=[self.raw(n) for n in b.network.nodes.values() if n.node_id not in removed]
        candidates.extend(draft[a] for a in fresh)
        for n in candidates:
            if n['node_id'] in scope['aliases']:
                alias=scope['aliases'][n['node_id']]
                if alias in draft:n['connections']['interfaces']=[*draft[alias]['connections']['interfaces'],*[asdict(e) for e in before[n['node_id']].interfaces if e.target_node_id not in scope['aliases']]]
        candidate=_build(dict(version=8,signals={},delegations=[],nodes=candidates),b.directory)
        for path in files:
            target=(b.directory/path).resolve()
            if not target.is_relative_to(b.directory.resolve()) or target.is_symlink():raise PermissionError('节点文本位置无效')
            previous=target.read_bytes() if target.exists() else None
            if previous!=decode_data(files[path]):
                from datanet.core.component_registry import resource_paths
                if any(Path(resource).resolve()==target for n,node in b.network.nodes.items() if n not in scope['aliases'] for _,_,resource in resource_paths(node)):raise PermissionError('文本仍被范围外节点共享，不能写入')
            file_images[path]=previous
        receipts=b.extension_state.setdefault('admin_receipts',{});prior_receipt=receipts.get(scope['workspace'])
        try:
            for alias in fresh:
                node=candidate.nodes[ids[alias]];mounts=deepcopy(node.modules);node.modules={};b.network.add_node(node);new_nodes.append(node.node_id)
                for name,mount in mounts.items():b.modules.mount(node.node_id,name,mount['config'],mount['state'],access=mount['access'])
            for alias in original.keys()&draft.keys():
                node=before[reverse[alias]];entry=draft[alias];wanted=deepcopy({**entry['modules'],**{k:v for k,v in node.modules.items() if k in b.components.module_extensions}})
                for name,mount in wanted.items():
                    if name in node.modules:mount['state']=deepcopy(node.modules[name]['state'])
                if alias=='root':wanted=oldmodules[node.node_id]
                if wanted!=node.modules:
                    if b.node_locks.leases.get(node.node_id):raise RuntimeError('正在调用链中执行的节点不能重装模块')
                    changed.add(node.node_id)
                    for name in list(node.modules):b.modules.unmount(node.node_id,name)
                    for name,mount in wanted.items():b.modules.mount(node.node_id,name,mount['config'],mount['state'],access=mount['access'])
                node.name=entry['name'];node.description=entry['description'];node.interfaces=list(candidate.nodes[node.node_id].interfaces)
            for node_id in removed:
                if b.node_locks.leases.get(node_id):raise RuntimeError('不能删除调用链中仍在执行的节点')
                changed.add(node_id)
                for name in list(b.network.nodes[node_id].modules):b.modules.unmount(node_id,name)
                b.network.nodes.pop(node_id);b.agents.pop(node_id,None)
            validate_management(b.network);b.write_documents(files)
            result=dict(created=list(fresh.values()),node_ids=fresh,updated=updated,deleted=sorted(removed),duplicate=False);receipts[scope['workspace']]=result;b.dispatch('save',{})
        except BaseException:
            for node_id in new_nodes:
                for name in list(b.network.nodes[node_id].modules):b.modules.unmount(node_id,name)
                b.network.nodes.pop(node_id,None)
            b.network.nodes.update(before);b.agents.clear();b.agents.update(oldbindings)
            for node_id,attrs in oldattrs.items():
                node=before[node_id]
                for key,value in attrs.items():setattr(node,key,value)
                if node_id in changed:
                    for name in list(node.modules):b.modules.unmount(node_id,name)
                    for name,mount in oldmodules[node_id].items():b.modules.mount(node_id,name,mount['config'],mount['state'],access=mount['access'])
            for key in list(b.modules._published):b.network.metadata_registry.unregister('module:'+repr(key))
            b.modules._published.clear();b.modules._published.update(published)
            for key in published:b.network.metadata_registry.register('module:'+repr(key),lambda target,key=key:b.modules._metadata_fields(key,target))
            for path,content in file_images.items():
                target=b.directory/path
                if content is None:target.unlink(missing_ok=True)
                else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
            b.extension_state['document_resources']=resources
            if prior_receipt is None:receipts.pop(scope['workspace'],None)
            else:receipts[scope['workspace']]=prior_receipt
            raise
        scope['applied']=result;write_json(self.home/(scope['workspace']+'.json'),scope);return result
    async def operation(self,actor,operation,args):
        self.policy(actor)
        if self.backend.node_locks.current:raise RuntimeError('管理员制作和拓扑提交应在业务节点事务之外调用')
        if operation=='inspect':
            scope=await self.inspect(actor);return dict(document=scope['document'],strength=scope['policy']['strength'],channels=scope['policy']['channels'],mode='允许制作组件' if scope['policy']['allow_component_creation'] else '仅组装已有组件')
        if operation=='build':return await self.build(actor,args)
        self.task(actor,args['task'])
        if operation=='apply':return await self.apply(actor,args['task'])
        value=await self.host('cancel' if operation=='cancel' else 'status',dict(task=args['task']))
        return {k:value.get(k) for k in ('id','workspace','status','phase','steps','error','validation_log')}

def register(services):
    factory=services.module_types[MODULE]
    async def extended(backend,actor,policy,operation,args):
        if operation!='manage':raise PermissionError('未声明的管理员端口')
        params=dict(args);action=params.pop('operation');return await backend.network_administrator.operation(actor,action,params)
    services.module_extensions[MODULE]=(factory,extended)
    services.initializers.append(lambda b:setattr(b,'network_administrator',Administrator(b)))
    services.rpc('network_admin_workspace',lambda b,p:b.network_administrator.workspace(p))
    services.rpc('network_admin_child',lambda b,p:b.network_administrator.bind_child(p))
