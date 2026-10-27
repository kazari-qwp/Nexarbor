"""制作副本复制实际网络和模块；模型与外部副作用默认禁用。"""
from copy import deepcopy
import json
import os,subprocess,sys
from pathlib import Path
from uuid import uuid4
from .service import read_json,write_json,sources,digest

def sanitized(document):
    result=deepcopy(document);files=result.get('files',{});copied={};paths={}
    for index,node in enumerate(result['network']['nodes']):
        if node['type']=='pulse':node.get('parameters',{}).pop('state',None)
        data=node.get('data')
        if not data:continue
        old=data['path'].replace('\\','/').rstrip('/');new=f'data/{index}/'+Path(old).name
        data['path']=new;paths[old]=new
        for name,content in files.items():
            if name==old or name.startswith(old+'/'):copied[new+name[len(old):]]=deepcopy(content)
        if not data.get('directory') and old not in files:copied[new]=''
    for index,(name,content) in enumerate(files.items()):
        if any(name==old or name.startswith(old+'/') for old in paths):continue
        mapped=f'data/documents/{index}/'+Path(name).name;paths[name]=mapped;copied[mapped]=deepcopy(content)
    def relocated(value):
        path=value.replace('\\','/')
        for old,new in sorted(paths.items(),key=lambda item:len(item[0]),reverse=True):
            if path==old or path.startswith(old+'/'):return new+path[len(old):]
        return value
    def rewrite(value):
        if isinstance(value,list):return [rewrite(item) for item in value]
        if isinstance(value,dict):return {key:relocated(item) if isinstance(item,str) and (key in ('file','path','document') or key.endswith('_path')) else rewrite(item) for key,item in value.items()}
        return value
    for node in result['network']['nodes']:
        if 'tables' in node:node['tables']=rewrite(node['tables'])
    result.update(version=1,agents={},signals={},files=copied)
    return result

def prepare(studio,p,*,folder=None,activate=True):
    work=folder or studio.folder(p['id']);metadata=read_json(studio.folder(p['id'])/'workspace.json',{})
    if p.get('source','current')=='candidate':
        from .network_work import validate_network
        document=validate_network(read_json(work/p.get('network_file','network.json'),{}),studio.backend,studio.library,port_definitions=studio.ports)
        from .preset_repetition import expand_snapshot
        network=document['network']
        expanded=expand_snapshot({**network,'files':document['files']},definitions={name:release['manifest'] for name,release in studio.library.items()})
        document=dict(network={key:value for key,value in expanded.items() if key not in ('files','positions')},files=expanded['files'])
        document.update(runtime=read_json(work/'runtime.json',{'templates':[]}),node_properties=document['network'].get('properties',{}))
    else:
        scoped=getattr(studio.backend,'network_administrator',None)
        document=scoped.source(p['id']) if scoped and scoped.has(p['id']) else studio.backend.snapshot()
    home=studio.root/'environments'/p['id']/uuid4().hex;home.mkdir(parents=True)
    write_json(home/'initial.json',sanitized(document))
    library={name:studio.root/release['folder'] for name,release in studio.library.items()}
    if metadata.get('kind')!='network':
        from .contract import manifest
        spec=manifest(work);library[spec['id']]=work
    used={item['module_id'] for node in document['network']['nodes'] for item in node.get('tables',{}).get('modules',[])}
    for name,relative in [('tool_discovery','modules/tool_discovery'),('context.assembler','modules/context_assembler')]:
        if name in used and name not in library:library[name]=Path(__file__).resolve().parents[2]/relative
    modules={}
    for name,source in library.items():
        relative='modules/'+name;modules[name]=relative
        for file,content in sources(source).items():
            target=home/relative/file;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    setup=dict(modules=modules,port_definitions=studio.ports,port_contracts=studio.port_contracts,fingerprint=digest(sources(work)),source=p.get('source','current'),module=None if metadata.get('kind')=='network' else spec['id'])
    for label in ('node_types','agent_node_types'):
        setup[label]={kind:cls.__module__+':'+cls.__name__ for kind,cls in getattr(studio.backend.saver,label).items()}
    write_json(home/'setup.json',setup)
    if activate:write_json(studio.root/'environments'/p['id']/'active.json',{'home':str(home)})
    return home


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
    env=dict(os.environ,PYTHONPATH=str(PROJECT),NEXARBOR_PROJECT_DIRECTORY=str(home/'runtime'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(temporary),TMP=str(temporary))
    request={k:v for k,v in p.items() if k!='id'}
    try:
        completed=subprocess.run([sys.executable,'-m','app.studio.environment',str(home)],input=json.dumps(request),text=True,encoding='utf-8',capture_output=True,timeout=86460,cwd=PROJECT,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired:
        return dict(ok=False,error='测试操作超过 86460 秒，已停止本次进程；正式项目未执行该操作。',error_type='TimeoutError',hint='检查是否存在递归等待、过大的检索范围或跨节点锁等待；缩小场景定位，不要重复原样重试。')
    if completed.returncode:raise ValueError('测试环境执行失败：'+completed.stderr[-5000:])
    value=json.loads(completed.stdout);value['directory']=str(home);value['source_hash']=setup['fingerprint'];return value

def open_backend(home):
    from .network_testing import NetworkHarness
    return NetworkHarness(home,_persistent=True)


def json_value(value):
    from collections.abc import Mapping
    from dataclasses import asdict,is_dataclass
    from domain.core import Tools
    if isinstance(value,Tools):return [dict(name=tool.name,description=tool.description,parameters=tool.parameters) for tool in value]
    if is_dataclass(value):return asdict(value)
    if isinstance(value,Mapping):return dict(value)
    raise TypeError('测试结果不是可序列化数据：'+type(value).__name__)


async def worker(home,request):
    h=open_backend(home);setup=read_json(home/'setup.json',{})
    try:
        action=request.get('action','inspect');result=None
        if action=='inspect' and request.get('section')=='result':
            previous=read_json(home/'last-result.json',None)
            if previous is None:raise ValueError('还没有可读取的操作结果')
            from .text_pages import text_page
            return dict(ok=True,**text_page(json.dumps(previous,ensure_ascii=False,indent=2),request,default_lines=120,max_lines=200))
        if action=='mount':
            node=h.network.get(request['node']);name=request.get('module') or setup['module'];current=node.modules.get(name)
            if current is not None and any(key in request for key in ('config','state','access')):node.uninstall(current)
            h.mount(node.info.node_id,module=name,**{key:request[key] for key in ('config','state','access') if key in request})
            result=dict(mounted=name,node=node.info.node_id)
        elif action=='call':
            result=await h.call(request['actor'],request['node'],request.get('module') or setup['module'],request['operation'],request.get('arguments',{}),strength=request.get('strength',2),channels=request.get('channels',[]))
        elif action=='signal':
            from app.runtime.requester import as_requester
            from app.runtime.signal_authority import signal_authority
            from domain.signals import Signal
            strength=request.get('strength',2);actor=request['actor']
            with as_requester(actor),signal_authority(actor,strength):
                receipt=h.backend.signals.emit(Signal(actor,request['channels'],strength,content=request.get('arguments',{}),max_deliveries=1000,timeout_seconds=20,node_timeout_seconds=5))
            result=await h.backend.signals.wait(receipt['signal_id'])
        h.backend.save()
        document=h.backend.snapshot();graph=document['network']
        if action=='snapshot':return dict(ok=True,document=dict(network={**graph,'properties':document.get('node_properties',{})},files=document['files']))
        result=json.loads(json.dumps(result,ensure_ascii=False,default=json_value))
        summary=[dict(id=node['node_id'],name=node['name'],type=node['type'],modules=node['tables']['modules'] if request.get('node')==node['node_id'] else [item['module_id'] for item in node['tables']['modules']],edges=node['links']) for node in graph['nodes'] if not request.get('node') or request['node']==node['node_id']]
        detailed=dict(ok=True,result=result,nodes=summary,source=setup['source'])
        if action!='inspect':write_json(home/'last-result.json',detailed)
        if action=='signal' and isinstance(result,dict):
            wave=result;result={key:wave[key] for key in ('status','returned','error') if key in wave}
            deliveries=wave.get('deliveries',[])
            result.update(delivery_count=len(deliveries),layer_count=len(wave.get('layers',[])),errors=[{key:item[key] for key in ('node_id','status','error') if key in item} for item in deliveries if item.get('status') in ('failed','timed_out')][:8])
        value=dict(ok=True,result=compact_result(result),counts=dict(nodes=len(graph['nodes']),edges=sum(len(node['links']) for node in graph['nodes'])),source=setup['source'])
        if action=='inspect' and request.get('node'):value['nodes']=summary
        value['hint']='配置、状态和连线用网络查看工具 source=environment 按需查询；完整操作结果用 test_environment(action=inspect,section=result) 按行读取。'
        return value
    finally:await h.close()


if __name__=='__main__':
    import asyncio
    try:print(json.dumps(asyncio.run(worker(Path(sys.argv[1]),json.loads(sys.stdin.read()))),ensure_ascii=False))
    except Exception as error:print(json.dumps(dict(ok=False,error=str(error),error_type=type(error).__name__),ensure_ascii=False))

