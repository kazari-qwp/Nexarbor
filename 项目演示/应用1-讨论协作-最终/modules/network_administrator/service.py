"""局部制作任务、原幂等键和状态查询；提交编排独立保存。"""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import time
from app.studio.service import read_json,write_json as _write_json
from app.studio.text_pages import text_page
from domain.core.channel_filters import resolve
from . import scope

MODULE='network.administrator'

def write_json(path,value):
    for attempt in range(6):
        try:return _write_json(path,value)
        except PermissionError:
            if attempt==5:raise
            time.sleep(.02*(attempt+1))

class Administrator:
    def __init__(self,backend):
        self.backend=backend;self.studio=backend.studio;self.home=self.studio.root/'admin-scopes';self.jobs_locks={};self.home.mkdir(exist_ok=True)

    def has(self,workspace):return bool(isinstance(workspace,str) and re.fullmatch(r'module-[A-Za-z0-9_-]{1,80}',workspace) and (self.home/(workspace+'.json')).is_file())

    def record(self,workspace):
        if not self.has(workspace):raise PermissionError('不是局部管理员的制作副本')
        return read_json(self.home/(workspace+'.json'),{})

    def source(self,workspace):return deepcopy(self.record(workspace)['document'])

    def workspace(self,p):
        if not self.has(p['id']):return None
        record=self.record(p['id']);return dict(scoped=True,allow_component_creation=record['policy']['allow_component_creation'],actor=record['actor'],role=record.get('role','network'))

    def module(self,actor):
        node=self.backend.network.get(actor);module=node.modules.get(MODULE) if node is not None else None
        if module is None:raise PermissionError('管理员模块已不在当前节点上')
        return module

    def policy(self,module):
        actor=module._access_origin.info.node_id
        if self.module(actor) is not module:raise PermissionError('管理员实例已被替换')
        channels=resolve(module.channels,module.channel_mode,self.backend.network.channel_names());config=module.config
        return dict(strength=module.strength,channels=list(channels),allow_component_creation=config.get('allow_component_creation',False),max_nodes=config.get('max_nodes',40),timeout_seconds=config.get('timeout_seconds',600))

    def capture(self,module,expected=None):
        policy=self.policy(module);images=module.collect(lambda node:scope.read_node(self,node))
        if expected is not None and set(images)!=set(expected):raise PermissionError('管理员可达范围已经变化，请重新制作')
        return scope.capture(self,module,images,policy)

    async def inspect(self,module):
        while True:
            images=await asyncio.to_thread(module.collect,lambda node:scope.read_node(self,node));ids=set(images)
            async with self.backend.node_locks.access(ids,mutable=False):
                try:return await asyncio.to_thread(self.capture,module,ids)
                except PermissionError as error:
                    if str(error)!='管理员可达范围已经变化，请重新制作':raise

    async def host(self,method,p):
        executor=self.backend.context_port
        if executor is None:raise RuntimeError('当前宿主尚未配置网络制作运行器')
        return await asyncio.to_thread(executor.transport.host,'network-admin-'+method,p)

    def check(self,workspace,document):return scope.check(self,workspace,document)

    async def apply(self,actor,task):
        from .commit import apply
        async with self.jobs_locks.setdefault(actor,asyncio.Lock()):return await apply(self,actor,task)

    async def build(self,actor,args):
        async with self.jobs_locks.setdefault(actor,asyncio.Lock()):return await self._build(actor,args)
    async def _build(self,actor,args):
        scope=await self.inspect(self.module(actor));keyfile=self.home/('keys-'+sha256(actor.encode()).hexdigest()+'.json');keys=read_json(keyfile,{})
        if args['key'] in keys:
            old=keys[args['key']]
            if old['requirement']!=args['requirement']:raise ValueError('相同制作键不能改变需求')
            if not old.get('task'):raise RuntimeError('上次启动未完成，请换一个制作键')
            return dict(task=old['task'],workspace=old['workspace'],duplicate=True)
        if len(keys)>=200:raise ValueError('管理员已保留200项制作任务，请先整理')
        workspace=self.studio.create(dict(kind='network',sample='blank',name='局部网络 · '+self.backend.network.get(actor).info.name));id=workspace['id'];scope.update(workspace=id,role='network')
        write_json(self.home/(id+'.json'),scope);write_json(self.studio.folder(id)/'network.json',scope['document'])
        text='# 局部管理员制作流程\nroot 是管理员所在节点的锚点，不是全网根节点。先读 network.json。保留已有编号；新节点用新局部编号。\n已有节点只修改名称、说明、可见出边和普通模块配置；保留状态、权限、类型、文件位置、执行绑定。root 只修改名称、说明、出边。\n新增模块和Agent的强度、频道不能超过下列授权。新增节点可复用可见节点已提供的工具及其频道；新增且绑定执行器的 Agent 可提供自己的 runtime:agent_run。已有工具授权只读；不能引入其他外部工具或官方越权模块。文本只属于副本节点。\n当前只是运行中局部网络管理：放置预设并接线后查看一次实例即可；不编写测试、不模拟讨论和协作。完成后由宿主检查格式、授权和版本再提交。\n授权：'+json.dumps(scope['policy'],ensure_ascii=False)
        ref=self.studio.folder(id)/'reference';ref.mkdir(exist_ok=True);(ref/'局部网络说明.md').write_text(text,encoding='utf-8')
        keys[args['key']]=dict(requirement=args['requirement'],workspace=id,task=None);write_json(keyfile,keys)
        try:
            job=await self.host('start',dict(id=id,name='局部网络管理员',requirement=args['requirement'],allow_component_creation=scope['policy']['allow_component_creation'],allow_network_testing=True,auto_publish=False,timeout=scope['policy']['timeout_seconds']))
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
        if not parent['policy']['allow_component_creation'] or not self.policy(self.module(parent['actor']))['allow_component_creation']:raise PermissionError('当前管理员禁止委托制作组件')
        child=deepcopy(parent);child.update(workspace=p['id'],role='component');child.pop('task',None);write_json(self.home/(p['id']+'.json'),child);return dict(bound=True)
    async def operation(self,module,operation,args):
        policy=self.policy(module);actor=module._access_origin.info.node_id
        if self.backend.node_locks.current:raise RuntimeError('管理员制作和拓扑提交应在业务节点事务之外调用')
        if operation=='inspect':
            scope=await self.inspect(module);return dict(document=scope['document'],strength=scope['policy']['strength'],channels=scope['policy']['channels'],mode='允许制作组件' if scope['policy']['allow_component_creation'] else '仅组装已有组件')
        if operation=='build':return await self.build(actor,args)
        self.task(actor,args['task'])
        if operation=='apply':return await self.apply(actor,args['task'])
        value=await self.host('cancel' if operation=='cancel' else 'status',dict(task=args['task']))
        if operation=='status':
            wait=args.get('wait_seconds',15)
            if type(wait) not in (int,float) or not 0<=wait<=30:raise ValueError('等待时间为0至30秒')
            deadline=time.monotonic()+wait
            while value.get('status')=='running' and time.monotonic()<deadline:
                await asyncio.sleep(min(1,max(0,deadline-time.monotonic())))
                value=await self.host('status',dict(task=args['task']))
        result={k:value.get(k) for k in ('id','workspace','status','phase','steps')}
        if value.get('error'):result['error']=str(value['error'])[:1200]
        log=str(value.get('validation_log') or '')
        if log:
            count=re.search(r'(?:测试数量：|Ran )(\d+)',log)
            summary=[line for line in log.splitlines() if re.match(r'^(?:ERROR:|FAIL:|Ran |OK$|FAILED |PASS[:：])',line)]
            result['validation']={k:v for k,v in dict(status=value.get('validation_status'),test_count=int(count[1]) if count else None,summary='\n'.join(summary[:6])[:1200]).items() if v is not None}
            if args.get('include_log'):
                page=text_page(log,args,default_lines=60,max_lines=100)
                result['validation_log']=page.pop('text');result['log_page']=page
            else:result['hint']='需要诊断时用 include_log=true 分页读验证日志；运行中可 wait_seconds=30 等待，避免频繁轮询。'
        return result
