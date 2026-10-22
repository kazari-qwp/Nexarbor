"""制作环境：复制图与受管理文本，在独立进程中运行，禁用模型和外部副作用。"""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json,os,subprocess,sys


def compact_result(value):
    """Keep normal business receipts; long payloads stay in the paged result."""
    if len(json.dumps(value,ensure_ascii=False))<=6000:return value
    def summary(item,depth=0):
        if isinstance(item,dict):
            if depth>=2:return dict(type='object',keys=list(item)[:12],field_count=len(item))
            return {key:summary(part,depth+1) for key,part in list(item.items())[:16]}
        if isinstance(item,list):return dict(type='array',count=len(item),sample=[summary(part,depth+1) for part in item[:3]])
        if isinstance(item,str) and len(item)>300:return dict(type='text',characters=len(item),preview=item[:300])
        return item
    return dict(summary=summary(value),complete_result='test_environment(action=inspect,section=result)')

def sanitized(document):
    result=deepcopy(document);result['network']['signals']={};files={k.replace('\\','/'):v for k,v in result.get('files',{}).items()};copied={};paths={}
    for index,node in enumerate(result['network']['nodes']):
        node['execution']=None;node['context_cursor']=None;node['agent']=None
        node['toolboxes']=[];node['expose']=[]
        if node['type']=='pulse':node['parameters'].pop('state',None)
        parameters=node.get('parameters',{})
        for label in ('file_path','content_path','metadata_path','db_path','directory','storage_path'):
            old=parameters.get(label)
            if not isinstance(old,str):continue
            old=old.replace('\\','/').rstrip('/');new=f'data/{index}/'+Path(old).name;parameters[label]=new;paths[old]=new
            for name,content in files.items():
                if name==old or name.startswith(old+'/'):copied[new+name[len(old):]]=deepcopy(content)
            if label in ('file_path','content_path','metadata_path') and old not in files:copied[new]=''
    for index,(name,content) in enumerate(files.items()):
        if any(name==old or name.startswith(old+'/') for old in paths):continue
        mapped=f'data/documents/{index}/'+Path(name).name;paths[name]=mapped;copied[mapped]=deepcopy(content)
    def relocated(value):
        path=value.replace('\\','/')
        for old,new in sorted(paths.items(),key=lambda item:len(item[0]),reverse=True):
            if path==old or path.startswith(old+'/'):return new+path[len(old):]
        return value
    def rewrite(value):
        if isinstance(value,list):return [rewrite(v) for v in value]
        if isinstance(value,dict):return {key:relocated(item) if isinstance(item,str) and (key in ('file','path','document') or key.endswith('_path')) else rewrite(item) for key,item in value.items()}
        return value
    for node in result['network']['nodes']:node['modules']=rewrite(node['modules'])
    result['files']=copied
    return result

def prepare(studio,p,*,folder=None,activate=True):
    from .service import sources,digest,write_json,read_json
    work=folder or studio.folder(p['id']);metadata=read_json(work/'workspace.json',{})
    current=sources(work);fingerprint=digest(current)
    publications={}
    if p.get('source','current')=='candidate':
        if metadata.get('kind')!='network':raise ValueError('只有网络制作副本可使用候选网络')
        from .network_work import validate_network
        from .network_work import output_file
        document=read_json(output_file(work,p.get('network_file','network.json')),{})
        scoped=getattr(studio.backend,'network_administrator',None)
        if scoped and scoped.has(p['id']):document=scoped.check(p['id'],document)
        document=validate_network(document,studio.backend,studio.library)
    else:
        scoped=getattr(studio.backend,'network_administrator',None)
        snapshot=scoped.source(p['id']) if scoped and scoped.has(p['id']) else studio.backend.snapshot()
        document={key:snapshot[key] for key in ['network','files']};publications=snapshot.get('node_publications',{})
    from .assembly import materialize_document
    document=materialize_document(document,studio.backend.components.module_types)
    executions={node['node_id']:deepcopy(node['execution']) for node in document['network']['nodes'] if node.get('execution')}
    document=sanitized(document)
    home=studio.root/'environments'/p['id']/uuid4().hex;home.mkdir(parents=True)
    write_json(home/'initial.json',document)
    library=deepcopy({name:release for name,release in studio.library.items() if not studio.project_only or release.get('origin')=='project'})
    for name,release in library.items():
        original=studio.root/release['folder'];destination=home/'runtime/studio/releases'/name/release['version']/release['digest']
        release['folder']=str(destination.relative_to(home/'runtime/studio'));release['origin']='environment'
        for relative,content in sources(original).items():
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    if metadata.get('kind')!='network':
        from .contract import manifest
        spec=manifest(work);destination=home/'runtime/studio/releases'/spec['id']/'candidate'
        for relative,content in current.items():
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
        defaults=read_json(work/'example.json',{})
        library[spec['id']]=dict(origin_kind='candidate',id=spec['id'],version=spec['version'],folder=str(destination.relative_to(home/'runtime/studio')),digest=fingerprint,manifest=spec,defaults=defaults.get('config',{}),mount_defaults=defaults)
    write_json(home/'runtime/studio/library.json',library)
    # A missing project module must stay missing, rather than silently using a bundled answer.
    write_json(home/'runtime/studio/removed-modules.json',sorted(set(studio.standard_releases)-set(library)))
    if metadata.get('kind')=='network' and p.get('source','current')=='candidate':
        from .network_work import runtime_settings
        templates=runtime_settings(work,studio.backend,document,p['id'])['templates'] if p.get('network_file','network.json')=='network.json' else []
    else:templates=studio.backend.template_definitions() if hasattr(studio.backend,'template_definitions') else []
    setup=dict(fingerprint=fingerprint,source=p.get('source','current'),external_tools=studio.backend.external_tools.catalog(),port_contracts=deepcopy(getattr(studio.backend,'port_contracts',{})),publications=publications,templates=templates,executions=executions,module=None if metadata.get('kind')=='network' else spec['id'])
    write_json(home/'setup.json',setup)
    if activate:write_json(studio.root/'environments'/p['id']/'active.json',dict(home=str(home)))
    return home

def operate(studio,p):
    from .service import sources,digest,read_json,PROJECT
    action=p.get('action','inspect')
    if action not in ('reset','inspect','mount','call','signal','snapshot'):raise ValueError('未知测试环境操作')
    index=studio.root/'environments'/p['id']/'active.json'
    if action=='reset':home=prepare(studio,p)
    elif not index.exists():raise ValueError('请先 reset，复制当前网络或候选网络')
    else:home=Path(read_json(index,{})['home'])
    if not home.resolve().is_relative_to((studio.root/'environments'/p['id']).resolve()):raise ValueError('测试目录越界')
    setup=read_json(home/'setup.json',{})
    if setup['fingerprint']!=digest(sources(studio.folder(p['id']))):raise ValueError('源码已修改，请 reset 创建新测试环境；原测试副本保留')
    temporary=home/'temp';temporary.mkdir(exist_ok=True)
    env=dict(os.environ,DATANET_PROJECT_RESOURCES_ONLY='0',DATANET_PROJECT_DIRECTORY=str(home/'runtime'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(temporary),TMP=str(temporary))
    request={k:v for k,v in p.items() if k!='id'}
    try:
        completed=subprocess.run([sys.executable,'-m','datanet.studio.environment',str(home)],input=json.dumps(request),text=True,encoding='utf-8',capture_output=True,timeout=86460,cwd=PROJECT,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired:
        return dict(ok=False,error='测试操作超过 35 秒，已停止本次进程；正式项目未执行该操作。',error_type='TimeoutError',hint='检查是否存在递归等待、过大的检索范围或跨节点锁等待；缩小场景定位，不要重复原样重试。')
    if completed.returncode:raise ValueError('测试环境执行失败：'+completed.stderr[-5000:])
    value=json.loads(completed.stdout);value['directory']=str(home);value['source_hash']=setup['fingerprint'];return value

def open_backend(home):
    """The interactive environment and author tests use the same isolated runtime."""
    from .service import read_json,write_json
    from datanet.core.backend import Backend
    setup=read_json(home/'setup.json',{});backend=Backend(home/'runtime',initial_document=read_json(home/'initial.json',{}))
    backend.port_contracts=setup.get('port_contracts',{})
    if setup.get('templates'):
        if not hasattr(backend,'configure_templates'):raise ValueError('测试宿主没有加载固定模板端口')
        backend.configure_templates(dict(templates=setup['templates']))
    if not (home/'seeded.json').exists():
        for node,modules in setup.get('publications',{}).items():
            for module,fields in modules.items():
                key=(node,module)
                if key in backend.modules.instances:
                    backend.modules._published[key]=deepcopy(fields)
                    backend.network.metadata_registry.register('module:'+repr(key),lambda target,key=key:backend.modules._metadata_fields(key,target))
        write_json(home/'seeded.json',{'seeded':True})
    async def denied(actor,name,args):raise PermissionError('测试环境禁用模型、外部工具及不可逆副作用')
    groups={}
    for item in setup['external_tools']:groups.setdefault(item['provider'],[]).append({key:item[key] for key in ['name','description','parameters']})
    for provider,definitions in groups.items():
        # Instantiation mutates only this isolated graph and uses the production service.
        if provider=='templates' and hasattr(backend,'template_definitions'):continue
        async def execute(actor,name,args,provider=provider):
            if provider=='runtime' and name=='read_text':
                from datanet.runtime_ports.services import read_text
                # All file reads stay in the isolated project; external roots are not copied.
                return read_text(home/'runtime',dict(path=args['path']))
            if provider=='runtime' and name=='checkpoint':
                from datanet.runtime_ports.services import checkpoint
                return checkpoint(backend,args)
            return await denied(actor,name,args)
        backend.external_tools.register(provider,definitions,execute)
    return backend

def worker(home,request):
    from .service import read_json,write_json
    from datanet.core.serialization import network_document
    from .assembly import assemble
    setup=read_json(home/'setup.json',{});backend=open_backend(home)
    try:
        action=request.get('action','inspect');result=None
        if action=='inspect' and request.get('section')=='result':
            previous=read_json(home/'last-result.json',None)
            if previous is None:raise ValueError('还没有可读取的操作结果')
            from .text_pages import text_page
            return dict(ok=True,**text_page(json.dumps(previous,ensure_ascii=False,indent=2),request,default_lines=120,max_lines=200))
        if action=='mount':
            node=backend.network.nodes[request['node']];name=request.get('module') or setup['module'];release=backend.studio.library[name]
            defaults=release.get('mount_defaults',{});mount={key:deepcopy(request.get(key,defaults.get(key,{} if key!='access' else dict(strength=0,channels=[])))) for key in ['config','state','access']}
            modules=assemble(dict(type=node.signal_type,modules={**node.modules,name:mount}),backend.studio.library,backend.components.module_types)
            for module,spec in modules.items():
                if module==name or module not in node.modules:
                    if module in node.modules:backend.modules.unmount(node.node_id,module)
                    backend.modules.mount(node.node_id,module,spec['config'],spec['state'],access=spec['access'])
            result=dict(mounted=name,node=node.node_id)
        elif action=='call':
            result=backend.runtime.run(backend.modules.access(request['actor'],request['node'],request.get('module') or setup['module'],request['operation'],request.get('arguments',{}),strength=request.get('strength',2),channels=request.get('channels',[])))
        elif action=='signal':
            from datanet.core.signals import Signal
            result=backend.runtime.run(backend.signals.propagate(Signal(request['actor'],request['channels'],request.get('strength',2),content=request.get('arguments',{}),max_deliveries=1000,timeout_seconds=20,node_timeout_seconds=5)))
        backend.dispatch('save',{})
        graph=network_document(backend.network,backend.directory)
        if action=='snapshot':
            document=backend.snapshot()
            return dict(ok=True,document={key:document[key] for key in ('network','files')})
        summary=[dict(id=n['node_id'],name=n['name'],type=n['type'],modules=n['modules'] if request.get('node')==n['node_id'] else list(n['modules']),edges=n['connections']['interfaces']) for n in graph['nodes'] if not request.get('node') or request['node']==n['node_id']]
        detailed=dict(ok=True,result=result,nodes=summary,source=setup['source'])
        if action!='inspect':write_json(home/'last-result.json',detailed)
        if action=='signal' and isinstance(result,dict):
            result={key:result[key] for key in ('status','returned','error') if key in result}
            deliveries=detailed['result'].get('deliveries',[])
            result.update(delivery_count=len(deliveries),layer_count=len(detailed['result'].get('layers',[])),errors=[{key:item[key] for key in ('node_id','status','error') if key in item} for item in deliveries if item.get('status') in ('failed','timed_out')][:8])
        value=dict(ok=True,result=compact_result(result),counts=dict(nodes=len(graph['nodes']),edges=sum(len(n['connections']['interfaces']) for n in graph['nodes'])),source=setup['source'])
        if action=='inspect' and request.get('node'):value['nodes']=summary
        value['hint']='配置、状态和连线用网络查看工具 source=environment 按需查询；完整操作结果用 test_environment(action=inspect,section=result) 按行读取。'
        return value
    finally:backend.close()

if __name__=='__main__':
    try:print(json.dumps(worker(Path(sys.argv[1]),json.loads(sys.stdin.read())),ensure_ascii=False))
    except Exception as error:print(json.dumps(dict(ok=False,error=str(error),error_type=type(error).__name__),ensure_ascii=False))
