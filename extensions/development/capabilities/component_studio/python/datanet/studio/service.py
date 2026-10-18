"""Component work copies, immutable tested releases and core node assembly."""
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.text_node import TextFileNode
from datanet.core.pulse_node import PulseNode
from datanet.core.serialization import network_document,_build
from datanet.core.tool_access import invoke_tool
from .contract import factory,manifest,frontend_file
from jsonschema import Draft202012Validator
from .assembly import assemble,assemble_document

PROJECT=Path(__file__).resolve().parents[7]
RESOURCE=Path(__file__).resolve().parents[3]/'resources'
TEXT={'.py','.json','.md','.txt','.toml','.html','.css','.js'}
GUIDES=('AGENTS.md','MODULE_GUIDE.md','FRONTEND_GUIDE.md')
REQUIRED_FILES={'module.py','module.json','example.json'}

def split_files(files):
    """宿主制作资料与组件源码分开呈现；不改变既有发布摘要。"""
    owned={};references={}
    for name,content in files.items():
        relative=name.replace('\\','/')
        destination=references if relative in GUIDES or relative.startswith(('dependencies/','reference/','lessons/')) else owned
        destination[relative]=content
    return owned,references

def read_json(path,default):return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
def sources(folder):
    result={}
    for path in sorted(folder.rglob('*')):
        if '__pycache__' in path.parts or 'reference' in path.relative_to(folder).parts:continue
        if path.suffix not in TEXT or not path.is_file() or path.name=='test-output.txt':continue
        if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('Linked source escapes work copy')
        if path.stat().st_size>1024*1024:raise ValueError('Source file exceeds 1 MiB')
        result[path.relative_to(folder).as_posix()]=path.read_text(encoding='utf-8')
    if sum(len(text.encode()) for text in result.values())>8*1024*1024:raise ValueError('Work copy exceeds 8 MiB')
    return result
def digest(files):return sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class Studio:
    def __init__(self,backend):
        self.backend=backend;self.root=backend.directory/'studio';self.root.mkdir(exist_ok=True)
        self.work=self.root/'work';self.work.mkdir(exist_ok=True)
        self.removed=set(read_json(self.root/'removed-modules.json',[]))
        self.library={name:release for name,release in read_json(self.root/'library.json',{}).items() if name not in self.removed}
        for name,source in getattr(backend.components,'standard_modules',{}).items():
            if name in self.library or name in self.removed:continue
            files=sources(source['folder']);fingerprint=digest(files);spec=source['manifest']
            destination=self.root/'releases'/name/spec['version']/fingerprint
            for file,content in files.items():
                path=destination/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
            self.library[name]=dict(id=name,version=spec['version'],folder=str(destination.relative_to(self.root)),digest=fingerprint,manifest=spec,defaults=read_json(destination/'example.json',{}).get('config',{}),mount_defaults=read_json(destination/'example.json',{}))
        write_json(self.root/'library.json',self.library)
        for name in self.removed:
            backend.components.module_types.pop(name,None);backend.components.module_owners.pop(name,None)
        self.jobs={};self.processes={};self.pool=ThreadPoolExecutor(max_workers=2)
        self.lock=threading.RLock();self.running=False;self.bindings={}
        self.run_state=dict(status='idle',completed=0,requested=0)
        self.workspace_busy=lambda id:False
        self._load_releases()
    def _load_releases(self):
        visiting=set();done=set();factories={}
        def load(name):
            if name in done:return
            if name in visiting:raise ValueError('Module dependency cycle')
            visiting.add(name);release=self.library[name]
            folder=self.root/release['folder']
            if digest(sources(folder))!=release['digest']:raise ValueError('Published module changed: '+name)
            spec=manifest(folder)
            for dependency in spec['requires']:
                if dependency not in self.library:raise ValueError('Missing module dependency: '+dependency)
                load(dependency)
            reserved=getattr(self.backend.components,'module_extensions',{}).get(name)
            if reserved:
                official=self.backend.components.standard_modules.get(name)
                if not official or digest(sources(official['folder']))!=self.library[name]['digest']:raise PermissionError('官方扩展模块不能由制作产物替换：'+name)
                create=reserved[0]
            else:spec,create=factory(folder)
            factories[name]=create
            visiting.remove(name);done.add(name)
        for name in self.library:load(name)
        for name,create in factories.items():
            self.backend.components.module_types[name]=create
            self.backend.components.module_owners[name]='capabilities/component_studio'
    def folder(self,id):
        if not isinstance(id,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',id):raise ValueError('Invalid work copy ID')
        target=(self.work/id).resolve()
        if not target.is_relative_to(self.work.resolve()) or not target.is_dir():raise ValueError('Unknown work copy')
        return target
    def path(self,id,name):
        root=self.folder(id);target=(root/name).resolve()
        if not target.is_relative_to(root) or target.suffix not in TEXT:raise ValueError('File must be source inside the work copy')
        return target
    def catalog(self,p=None):
        samples=read_json(RESOURCE/'samples.json',[])
        library={name:dict(release,name=release['manifest'].get('name') or getattr(self.backend.components,'standard_modules',{}).get(name,{}).get('manifest',{}).get('name') or release['manifest'].get('frontend',{}).get('title') or name) for name,release in self.library.items()}
        return dict(workspaces=[dict(id=p.name,**read_json(p/'workspace.json',{})) for p in self.work.iterdir() if p.is_dir()],
                    samples=samples,library=library,jobs=list(self.jobs.values()),contract='nexarbor-module/v3')
    def create(self,p):
        kind=p.get('kind','module')
        if kind not in ('module','tool','network'):raise ValueError('制作类型必须是模块、工具或网络预设')
        sample=p.get('sample','blank');definitions=read_json(RESOURCE/'samples.json',[])
        selected=next((s for s in definitions if s['id']==sample),None)
        if selected is None:raise ValueError('Unknown sample')
        id='module-'+uuid4().hex[:10];folder=self.work/id;folder.mkdir()
        template=RESOURCE/'templates'/sample
        for name,content in read_json(template.with_suffix('.json'),{}).items():
            path=folder/name
            if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('Invalid template')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        if kind=='network':
            for path in folder.iterdir():
                if path.is_file():path.unlink()
            from datanet.core.network import Network
            graph=Network();graph.add_node(AgentNode('root','入口',file_path=folder/'data/root.md'))
            write_json(folder/'network.json',dict(network=network_document(graph,folder),files={'data/root.md':'你是这个网络的入口。'}))
            (folder/'README.md').write_text('# 网络预设\n\n说明网络用途、配置和使用步骤。\n',encoding='utf-8')
        elif kind=='tool':
            spec=read_json(folder/'module.json',{});spec['agent_tools']=[dict(id='increment',name='计数',description='增加计数并返回结果。',operation='increment')]
            write_json(folder/'module.json',spec)
        self._write_guides(folder)
        references=p.get('reference_files',{})
        if not isinstance(references,dict) or sum(len(v.encode('utf-8')) for v in references.values() if isinstance(v,str))>1024*1024:raise ValueError('参考资料必须为总计不超过1MiB的文本字典')
        for name,content in references.items():
            target=(folder/'reference'/name).resolve()
            if not isinstance(content,str) or not target.is_relative_to((folder/'reference').resolve()) or target.suffix not in TEXT:raise ValueError('参考资料路径或格式无效')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
        if selected.get('reference'):
            source=PROJECT/selected['reference'];reference=folder/'reference';reference.mkdir(exist_ok=True)
            shutil.copyfile(source,reference/'legacy.py')
        available=[]
        for name in p.get('dependencies',list(self.library)):
            release=self.library[name];source=self.root/release['folder'];destination=folder/'dependencies'/name;destination.mkdir(parents=True)
            for file in ['module.json','README.md','example.json']:
                if (source/file).exists():shutil.copyfile(source/file,destination/file)
            available.append(dict(id=name,version=release['version'],manifest=f'dependencies/{name}/module.json',guide=f'dependencies/{name}/README.md'))
        if available:write_json(folder/'dependencies/catalog.json',available)
        original=sources(folder)
        write_json(self.root/'baselines'/f'{id}.json',original)
        write_json(folder/'workspace.json',{'label':p.get('name') or {'module':selected['name'],'tool':'制作工具','network':'制作网络预设'}[kind],'sample':sample,'kind':kind,'display_folder':p.get('display_folder')})
        write_json(self.root/'metadata'/f'{id}.json',{'sample':sample,'kind':kind,'label':selected['name']})
        return self.read(dict(id=id))
    def read(self,p):
        folder=self.folder(p['id']);files=sources(folder);files.pop('workspace.json',None)
        original=read_json(self.root/'baselines'/f'{p["id"]}.json',{})
        owned,references=split_files(files)
        if (folder/'reference').exists():
            for f in (folder/'reference').rglob('*'):
                if f.is_file() and f.suffix in TEXT:
                    if not f.resolve().is_relative_to(folder.resolve()) or f.stat().st_size>1024*1024:raise ValueError('参考资料越界或超过1MiB')
                    references[f.relative_to(folder).as_posix()]=f.read_text(encoding='utf-8')
        return dict(id=p['id'],directory=str(folder),files=owned,original=split_files(original)[0],references=references,digest=digest(files),**{k:read_json(folder/'workspace.json',{}).get(k,default) for k,default in [('display_folder',None),('kind','module')]})
    def dependencies(self,p):
        folder=self.folder(p['id']);catalog=read_json(folder/'dependencies/catalog.json',[])
        known={item['id']:item for item in catalog}
        for name in p.get('modules',list(self.library)):
            release=self.library[name];source=self.root/release['folder'];target=folder/'dependencies'/name;target.mkdir(parents=True,exist_ok=True)
            for file in ['module.json','README.md','example.json']:
                if (source/file).exists():shutil.copyfile(source/file,target/file)
            known[name]=dict(id=name,version=release['version'],manifest=f'dependencies/{name}/module.json',guide=f'dependencies/{name}/README.md')
        write_json(folder/'dependencies/catalog.json',list(known.values()));return self.read(p)
    def maker_scope(self,p):
        scoped=getattr(self.backend,"network_administrator",None)
        return scoped.workspace(p) if scoped else None
    def maker_tool(self,p):
        """制作模型的文件能力只指向当前副本，不提供终端或任意路径。"""
        folder=self.folder(p['id']);name=p['tool'];args=p.get('arguments',{})
        if name=='list_files':
            data=self.read(p);return dict(files=list(data['files']),references=list(data['references']))
        if name=='read_file':
            path=self.path(p['id'],args['path'])
            if path.name=='workspace.json':raise PermissionError('宿主制作资料不作为组件文件')
            if path.stat().st_size>1024*1024:raise ValueError('文件超过 1 MiB')
            text=path.read_text(encoding='utf-8');lines=text.splitlines();start=max(0,args.get('start_line',1)-1);count=min(400,max(1,args.get('line_count',200)))
            return dict(path=args['path'],total_lines=len(lines),text='\n'.join(lines[start:start+count]))
        if name in ('write_file','edit_file'):
            path=self.path(p['id'],args['path']);old=path.read_text(encoding='utf-8') if path.exists() else ''
            content=args['content'] if name=='write_file' else old.replace(args['old'],args['new'],1)
            if name=='edit_file' and (not args['old'] or old.count(args['old'])!=1):raise ValueError('替换文本必须在文件中唯一匹配；先重新读取')
            value=self.save(dict(id=p['id'],file=args['path'],content=content,expected=sha256(old.encode()).hexdigest()))
            return dict(saved=args['path'],digest=value['digest'])
        if name=='catalog_modules':
            query=args.get('query','').lower();hidden=set(p.get('hidden',[]));result=[]
            for id,release in self.catalog()['library'].items():
                spec=release['manifest']
                if id in hidden or query and query not in json.dumps(spec,ensure_ascii=False).lower():continue
                details=dict(config_schema=spec['config_schema'],state_schema=spec['state_schema']) if args.get('details') or query==id.lower() else {}
                result.append(dict(id=id,name=release['name'],description=spec.get('description',''),node_types=spec['node_types'],requires=spec['requires'],operations=spec['operations'],agent_tools=spec.get('agent_tools',[]),defaults=release.get('mount_defaults',{}),frontend=bool(spec.get('frontend')),**details))
            return dict(modules=result[:30],total=len(result))
        if name=='network_patch':
            if read_json(folder/'workspace.json',{}).get('kind')!='network':raise ValueError('只有网络制作副本可分批合并网络')
            file=folder/'network.json';old=file.read_text(encoding='utf-8');document=json.loads(old)
            if args.get('replace'):document=dict(network=dict(version=8,nodes=[],signals={},delegations=[]),files={})
            nodes={n['node_id']:n for n in document['network']['nodes']}
            for id in args.get('remove_nodes',[]):nodes.pop(id,None)
            for node in args['nodes']:
                if not isinstance(node,dict) or not isinstance(node.get('node_id'),str):raise ValueError('每个节点必须声明node_id')
                nodes[node['node_id']]=node
            document['network']['nodes']=list(nodes.values());document['files'].update(args.get('files',{}))
            self.save(dict(id=p['id'],file='network.json',content=json.dumps(document,ensure_ascii=False,indent=2),expected=sha256(old.encode()).hexdigest()))
            return dict(saved='network.json',nodes=len(nodes),files=len(document['files']))
        raise ValueError('未知制作工具：'+name)
    def release_read(self,p):
        release=self.library[p['module']];files=sources(self.root/release['folder']);files.pop('workspace.json',None)
        owned,references=split_files(files)
        return dict(id=release['id'],files=owned,original=owned,references=references,readOnly=True,release=release)
    def environment(self,p):
        from .environment import operate
        return operate(self,p)
    def copy_current(self,p):
        folder=self.folder(p['id'])
        if read_json(folder/'workspace.json',{}).get('kind')!='network':raise ValueError('仅网络制作副本可以复制当前配置')
        scoped=getattr(self.backend,'network_administrator',None)
        snapshot=scoped.source(p['id']) if scoped and scoped.has(p['id']) else self.backend.snapshot()
        document={key:snapshot[key] for key in ['network','files']};document['network']['signals']={};document['files']={k.replace('\\','/'):v or '' for k,v in document['files'].items()}
        for node in document['network']['nodes']:
            node['context_cursor']=None
            if node['type']=='pulse':node['parameters'].pop('state',None)
        from .network_work import validate_network
        validate_network(document,self.backend,self.library)
        old=(folder/'network.json').read_text(encoding='utf-8')
        self.save(dict(id=p['id'],file='network.json',content=json.dumps(document,ensure_ascii=False,indent=2),expected=sha256(old.encode()).hexdigest()))
        return dict(copied=True,file='network.json',nodes=len(document['network']['nodes']))
    def fork(self,p):
        release=self.release_read(p);workspace=self.create({'sample':'blank'});folder=self.folder(workspace['id'])
        for name,content in release['files'].items():
            if name in GUIDES:continue
            path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        write_json(self.root/'baselines'/f'{workspace["id"]}.json',sources(folder))
        write_json(folder/'workspace.json',{'label':release['id']+' · 修改副本','sample':'blank','display_folder':release['release'].get('display_folder')})
        return self.read({'id':workspace['id']})
    def save(self,p):
        path=self.path(p['id'],p['file'])
        relative=path.relative_to(self.folder(p['id'])).as_posix().casefold()
        if relative in [name.casefold() for name in (*GUIDES,'workspace.json')] or relative.startswith(('reference/','dependencies/','lessons/')):raise PermissionError('规范文件与参考资料只读')
        current=path.read_text(encoding='utf-8') if path.exists() else ''
        if p.get('expected')!=sha256(current.encode()).hexdigest():raise ValueError('File changed outside the editor; reload before saving')
        content=p['content']
        if not isinstance(content,str) or len(content.encode())>1024*1024:raise ValueError('Source exceeds 1 MiB')
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(content,encoding='utf-8');temporary.replace(path)
        return self.read(p)
    def _idle_work(self,id):
        if self.workspace_busy(id) or any(j['workspace']==id and j['status']=='running' for j in self.jobs.values()):
            raise ValueError('请先停止此工作副本的制作或验证任务')
        return self.folder(id)
    def delete_file(self,p):
        folder=self._idle_work(p['id']);path=self.path(p['id'],p['file'])
        relative=path.relative_to(folder).as_posix()
        if relative.casefold() in {n.casefold() for n in (*GUIDES,*REQUIRED_FILES,'workspace.json','network.json')} or relative.startswith(('reference/','dependencies/','lessons/')):
            raise PermissionError('组件必要文件和制作资料不能删除')
        current=path.read_text(encoding='utf-8')
        if p.get('expected')!=sha256(current.encode()).hexdigest():raise ValueError('文件已变化，请重新读取后再删除')
        target=self.root/'trash/files'/uuid4().hex/relative;target.parent.mkdir(parents=True)
        if not target.resolve().is_relative_to(self.root.resolve()):raise ValueError('回收站路径越出工作区')
        path.rename(target)
        return self.read(p)
    def delete_workspace(self,p):
        folder=self._idle_work(p['id'])
        if p.get('expected')!=self.read(p)['digest']:raise ValueError('工作副本已变化，请重新读取后再删除')
        archive=self.root/'trash/workspaces'/f'{p["id"]}-{uuid4().hex}'
        archive.parent.mkdir(parents=True,exist_ok=True)
        if not archive.resolve().is_relative_to(self.root.resolve()):raise ValueError('回收站路径越出工作区')
        folder.rename(archive)
        return dict(deleted=p['id'],archived=True)
    def _write_guides(self,folder):
        for name in GUIDES:(folder/name).write_text((RESOURCE/name).read_text(encoding='utf-8'),encoding='utf-8')
        if (RESOURCE/'lessons').is_dir():shutil.copytree(RESOURCE/'lessons',folder/'lessons',dirs_exist_ok=True)
    def prepare_agent(self,p):
        """新任务使用当前规范；历史指纹由原生会话适配器核对。"""
        self._write_guides(self.folder(p['id']))
    def frontend(self,p):
        if p.get('id'):
            folder=self.folder(p['id'])
        else:
            release=self.library[p['module']];folder=self.root/release['folder']
            if digest(sources(folder))!=release['digest']:raise ValueError('已发布模块源码发生变化，请重新验证发布')
        spec=manifest(folder);page=frontend_file(folder,spec)
        if page is None:return None
        return dict(html=page.read_text(encoding='utf-8'),title=spec['frontend'].get('title',spec['id']),
                    height=spec['frontend'].get('height',320),module=spec['id'])
    def validate(self,p):
        folder=self.folder(p['id']);files=sources(folder)
        id=uuid4().hex;job=dict(id=id,workspace=p['id'],status='running',digest=digest(files),log='',started=time.time())
        self.jobs[id]=job
        snapshot=self.root/'checks'/id;snapshot.mkdir(parents=True)
        for name,content in files.items():
            path=snapshot/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        timeout=p.get('timeout',30)
        if type(timeout) is not int or not 1<=timeout<=60:raise ValueError('Validation timeout must be 1–60 seconds')
        def run():
            env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONUTF8='1',PYTHONPATH=os.pathsep.join([str(PROJECT/'python'),str(Path(__file__).resolve().parents[2]),str(PROJECT/'extensions/foundation/capabilities/module_sdk/python')]),TEMP=str(self.root/'temp'),TMP=str(self.root/'temp'))
            Path(env['TEMP']).mkdir(exist_ok=True)
            log_path=snapshot/'validation.log'
            try:
                if (snapshot/'presets.json').exists() and read_json(folder/'workspace.json',{}).get('kind')!='network':
                    from .preset_work import check
                    result=check(snapshot,self.library)
                    job.update(status='passed',exit_code=0,log='PASS：复用已发布组件的配置方案、配置Schema；配置数量：'+str(len(result['presets']))+'。行为验证另看独立网络副本。');log_path.write_text(job['log'],encoding='utf-8');return
                if read_json(folder/'workspace.json',{}).get('kind')=='network':
                    from .network_work import check_work
                    result=check_work(snapshot,self.backend,self.library,workspace=p['id'])
                    job.update(status='passed',exit_code=0,log='PASS：当前成品格式、路径、节点、递归依赖、工具引用、配置与状态；节点数：'+str(result['nodes']))
                    log_path.write_text(job['log'],encoding='utf-8');return
                with self.lock:
                    if job['status']!='running' or getattr(self,'closed',False):return
                    sample=read_json(self.root/'metadata'/f'{p["id"]}.json',{}).get('sample','blank')
                    env['DATANET_TEST_MODULES']=json.dumps({name:str(self.root/release['folder']) for name,release in self.library.items()})
                    env['DATANET_MAKER_KIND']=read_json(folder/'workspace.json',{}).get('kind','module')
                    proc=subprocess.Popen([sys.executable,'-m','datanet.studio.worker',str(snapshot),sample],cwd=PROJECT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    self.processes[id]=proc
                tail=bytearray()
                def collect():
                    try:
                        while chunk:=proc.stdout.read(4096):
                            tail.extend(chunk)
                            if len(tail)>100000:del tail[:-100000]
                    except (OSError,ValueError):pass
                    finally:proc.stdout.close()
                reader=threading.Thread(target=collect,daemon=True);reader.start()
                try:code=proc.wait(timeout)
                except subprocess.TimeoutExpired:
                    self._kill(proc);job['status']='timeout';code=-1
                reader.join(1)
                job['log']=bytes(tail).decode('utf-8',errors='replace');log_path.write_text(job['log'],encoding='utf-8')
                if job['status']=='running':job['status']='passed' if code==0 else 'failed'
                job['exit_code']=code
            except Exception as error:job.update(status='failed',log=str(error))
            finally:
                self.processes.pop(id,None);job['finished']=time.time()
        self.pool.submit(run);return job.copy()
    @staticmethod
    def _kill(proc):
        if proc.poll() is not None:return
        if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
        else:proc.kill()
        proc.wait(timeout=10)
    def job(self,p):return self.jobs[p['job']].copy()
    def cancel(self,p):
        with self.lock:
            job=self.jobs[p['job']];job['status']='cancelled'
            process=self.processes.get(p['job'])
        if process:self._kill(process)
        return job.copy()
    def publish(self,p):
        folder=self.folder(p['id']);files=sources(folder);fingerprint=digest(files)
        if not any(j['workspace']==p['id'] and j['status']=='passed' and j['digest']==fingerprint for j in self.jobs.values()):raise ValueError('Test the current source before publishing')
        metadata=read_json(folder/'workspace.json',{})
        if (folder/'presets.json').exists() and metadata.get('kind')!='network':
            from .preset_work import check
            return dict(kind='component-presets',workspace=p['id'],**check(folder,self.library))
        if metadata.get('kind')=='network':
            from .network_work import check_work
            return dict(kind='network',id=p['id'],document=check_work(folder,self.backend,self.library)['document'],name=p.get('name') or metadata['label'],display_folder=metadata.get('display_folder'),digest=fingerprint)
        spec=json.loads(files['module.json']);name=spec['id']
        if name in getattr(self.backend.components,'module_extensions',{}):raise PermissionError('官方扩展模块不能发布替代实现')
        if any(module==name for _,module in self.backend.modules.instances):raise ValueError('Unmount active instances before replacing their module')
        if any(dep not in self.library for dep in spec['requires']):raise ValueError('Publish dependencies first')
        destination=self.root/'releases'/name/spec['version']/fingerprint
        destination.mkdir(parents=True,exist_ok=True)
        for file,content in files.items():
            path=destination/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        old=self.library.copy()
        manifest(destination)
        self.library[name]=dict(id=name,version=spec['version'],folder=str(destination.relative_to(self.root)),digest=fingerprint,manifest=spec,defaults=read_json(destination/'example.json',{}).get('config',{}),mount_defaults=read_json(destination/'example.json',{}),display_folder=metadata.get('display_folder'),origin_kind=metadata.get('kind','module'))
        try:self._load_releases()
        except BaseException:self.library=old;raise
        self.removed.discard(name);write_json(self.root/'removed-modules.json',sorted(self.removed))
        write_json(self.root/'library.json',self.library)
        return self.library[name]
    def mount(self,p):
        if self.running:raise ValueError('Wait until the signal completes')
        module=self.library[p['module']];folder=self.root/module['folder']
        config=p.get('config',read_json(folder/'example.json',{}).get('config',{}))
        defaults=read_json(folder/'example.json',{})
        node=self.backend.network.nodes[p['node']]
        proposed=dict(node.modules);proposed.setdefault(p['module'],dict(config=config,state=defaults.get('state',{}),access=p.get('access',defaults.get('access',dict(strength=0,channels=[])))))
        expanded=assemble(dict(type=node.signal_type,modules=proposed),self.library,self.backend.components.module_types)
        for name,spec in expanded.items():
            definition=self.backend.components.module_types[name];definition.validate(spec['config'],definition.config_schema);definition.validate(spec['state'],definition.state_schema)
        added=[]
        try:
            for name,spec in expanded.items():
                if name in node.modules:continue
                self.backend.modules.mount(p['node'],name,spec['config'],spec['state'],access=spec['access']);added.append(name)
        except BaseException:
            for name in reversed(added):self.backend.modules.unmount(p['node'],name)
            raise
        self._bind();return self.state()
    def release_delete_info(self,p):
        """只检查本工作区发布目录；永远不接受来自页面的文件路径。"""
        name=p.get('module');release=self.library.get(name)
        if release is None:raise ValueError('组件已不在发布库中')
        root=(self.root/'releases').resolve();target=(root/name).resolve()
        if target==root or not target.is_relative_to(root) or not target.is_dir():raise ValueError('组件文件不属于本工作区发布目录')
        registered=(self.root/release['folder']).resolve()
        if not registered.is_relative_to(target):raise ValueError('组件登记目录与组件编号不一致')
        files=[]
        for file in target.rglob('*'):
            if not file.resolve().is_relative_to(target):raise ValueError('组件发布目录含外部链接，不能删除')
            if file.is_file():files.append(str(file.relative_to(self.root)))
        blockers=[]
        if name in getattr(self.backend.components,'module_extensions',{}):blockers.append('官方扩展模块，只可归档，不能删除')
        for node in getattr(self.backend.network,'nodes',{}).values():
            if name in node.modules:blockers.append('运行节点：'+node.node_id)
        draft=read_json(self.root/'draft.json',{})
        if not draft.get('applied',False):
            for node in draft.get('document',{}).get('network',{}).get('nodes',[]):
                if name in node.get('modules',{}):blockers.append('待应用草稿：'+node['node_id'])
        for id,other in self.library.items():
            if id!=name and name in other['manifest']['requires']:blockers.append('依赖模块：'+id)
        if self.running or self.backend.modules.executing or self.backend.network.signals._active:blockers.append('网络中仍有组件或信号执行')
        return dict(canDelete=not blockers,reason='；'.join(blockers),blockers=blockers,ownership='workspace-release',path=str(target),files=files,
                    scope='删除本工作区此模块的全部发布版本；独立工作副本和项目共享源码保留。')
    def delete_release(self,p):
        self.backend.node_locks.lifecycle()
        name=p.get('module')
        if p.get('confirm')!=name:raise ValueError('组件删除确认不匹配')
        with self.lock:
            info=self.release_delete_info(p)
            if not info['canDelete']:raise ValueError(info['reason'])
            target=Path(info['path']);root=(self.root/'releases').resolve();temporary=(root/('.deleting-'+uuid4().hex)).resolve()
            if not target.is_relative_to(root) or not temporary.is_relative_to(root):raise ValueError('删除目标越出工作区')
            target.rename(temporary);old=self.library.copy();removed=self.removed.copy()
            try:
                self.library.pop(name);self.removed.add(name)
                write_json(self.root/'removed-modules.json',sorted(self.removed));write_json(self.root/'library.json',self.library)
            except BaseException:
                self.library=old;self.removed=removed
                write_json(self.root/'removed-modules.json',sorted(removed));write_json(self.root/'library.json',old);temporary.rename(target);raise
            self.backend.components.module_types.pop(name,None);self.backend.components.module_owners.pop(name,None)
            # 两个绝对路径均已核实在本工作区 releases 内；不删除共享扩展或工作副本。
            shutil.rmtree(temporary)
            return dict(deleted=name,filesDeleted=len(info['files']))
    def unmount(self,p):
        if self.running:raise ValueError('Wait until the signal completes')
        dependants=[name for name in self.backend.network.nodes[p['node']].modules if p['module'] in self.library.get(name,{}).get('manifest',{}).get('requires',[])]
        if dependants:raise ValueError('模块仍被以下实例依赖，请先卸载：'+ '、'.join(dependants))
        self.backend.modules.unmount(p['node'],p['module']);self._bind();return self.state()
    def _bind(self):
        from .sdk_services import bind_modules
        for node in self.backend.network.nodes.values():
            for name,spec in assemble(dict(type=node.signal_type,modules=node.modules),self.library,self.backend.components.module_types).items():
                if name not in node.modules:self.backend.modules.mount(node.node_id,name,spec['config'],spec['state'],access=spec['access'])
        bind_modules(self.backend)
    def town(self,p):
        raise ValueError('The previous town preset has not been migrated to component v3')
    def pulse(self,p):
        if self.running:raise ValueError('Signal is active')
        self.running=True;cycles=p.get('cycles',1)
        self.run_state=dict(status='running',completed=0,requested=cycles)
        try:
            runtime=self.backend.signals
            async def completed(pulse,report):self.run_state['completed']+=1
            deadline=p.get('timeout_seconds',min(3600,300*cycles))
            report=self.backend.runtime.run(self.backend.network.nodes[p.get('pulse','town/pulse')].run(runtime,cycles=cycles,timeout_seconds=deadline,cycle_complete=completed),timeout=deadline+10)
            self.run_state['status']='idle' if report['status']=='completed' else 'failed'
            if report['status']!='completed':self.run_state['error']='信号未完成闭环：'+report['status']
            self.running=False
            return dict(report=report,state=self.state())
        except Exception as error:
            self.run_state.update(status='failed',error=str(error));raise
        finally:self.running=False
    def reconcile(self,p):
        if self.running or self.backend.modules.executing or self.backend.network.signals._active:raise ValueError('请等待当前执行彻底停止后再核对中断轮次')
        pulse=self.backend.network.nodes[p['pulse']]
        if pulse.signal_type!='pulse':raise ValueError('请选择脉冲节点')
        pulse.reconcile(p['reason']);return self.state()
    def state(self,p=None):
        snapshot=self.backend.snapshot();document=snapshot['network']
        files={name:content if content is not None else '' for name,content in snapshot['files'].items()}
        names={entry['node_id']:entry['name'] for entry in document['nodes']}
        return dict(mode='组件开发 · Harness后端',live=dict(document=dict(network=document,files=files),commit=self.backend.store.head,sessions={id:dict(name=names[id],**value) for id,value in snapshot['agents'].items() if id in names}),draft=read_json(self.root/'draft.json',None),
                    job=dict(self.run_state),studio=True)
    def draft(self,p):
        previous=read_json(self.root/'draft.json',{'version':0})
        if p.get('expected_version',0)!=previous['version']:raise ValueError('Draft changed in another window; reload')
        value=dict(document=p['document'],layout=p.get('layout',{}),version=previous['version']+1,base_commit=p.get('base_commit'),applied=False)
        write_json(self.root/'draft.json',value);return value
    def apply(self,p):
        self.backend.node_locks.lifecycle()
        if self.running or self.backend.modules.executing or self.backend.network.signals._active:
            raise ValueError('Wait until component access and detached signals complete before replacing the graph')
        if p.get('base_commit')!=self.backend.store.head:raise ValueError('Network changed; reload before applying')
        from .network_work import validate_network
        document=validate_network(p['document'],self.backend,self.library);candidate=_build(document['network'],self.backend.directory)
        for node in candidate.nodes.values():
            self.backend.external_tools.validate_node(node)
            if hasattr(node,'file_path') and not node.file_path.is_relative_to(self.backend.directory):raise ValueError('Data files must stay in the network directory')
        for name,content in document.get('files',{}).items():
            if not (self.backend.directory/name).resolve().is_relative_to(self.backend.directory.resolve()) or not isinstance(content,str):raise ValueError('Invalid network document path')
        old=self.backend.snapshot()
        try:
            self.backend.modules.clear();self.backend.network=candidate;candidate.use_metadata_registry(self.backend.metadata_registry)
            self.backend.root=candidate.nodes['root'];self.backend.modules.restore();self._bind()
            self.backend.write_documents(document.get('files',{}))
        except BaseException:
            self.backend.restore(old);self._bind();raise
        draft=read_json(self.root/'draft.json',{'version':0})
        draft.update(document=document,layout=p.get('layout',{}),applied=True)
        write_json(self.root/'draft.json',draft)
        return dict(valid=True,document=document,draft=draft,commit=self.backend.store.head)
    def view(self,p):
        actor=p['actor'];strength=p.get('strength',2);paths={}
        channels={channel for n in self.backend.network.nodes.values() for edge in n.interfaces for channel in edge.metadata.channels}
        for channel in channels:
            paths[channel]=[dict(id=n.node_id,path=path,remaining=remaining,channels=[channel]) for n,path,remaining in self.backend.network.walk_states(actor,channels=[channel],strength=strength)]
        tools=[]
        from datanet.core.tool_access import list_tools
        for target in self.backend.network.nodes:tools.extend(list_tools(self.backend.network,actor,target,strength=strength).items)
        return dict(actor=actor,paths=paths,tools=tools)
    def graph_validate(self,p):
        try:
            from .network_work import validate_network
            validate_network(p['document'],self.backend,self.library)
            return dict(valid=True,errors=[],warnings=[])
        except Exception as error:return dict(valid=False,errors=[dict(path='network',message=str(error))],warnings=[])
    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        for process in list(self.processes.values()):self._kill(process)
        self.pool.shutdown(wait=True,cancel_futures=True)
        # A Backend can also be hosted by an existing asyncio application.

def register(services):
    def install(backend):backend.studio=Studio(backend)
    services.initializers.append(install)
    services.finalizers.append(lambda b:b.studio.close())
    services.graph_loaders.append(lambda b:b.studio._bind())
    services.snapshotters.append(lambda b:{'studio_releases':b.studio.library})
    def restore(b,document):
        installed={name:release for name,release in b.studio.library.items() if name in getattr(b.components,'standard_modules',{})}
        b.studio.library={name:release for name,release in {**installed,**document.get('studio_releases',b.studio.library)}.items() if name not in b.studio.removed}
        b.studio._load_releases()
    services.restorers.append(restore)
    methods={'catalog':False,'prepare_agent':False,'create':False,'read':False,'dependencies':False,'maker_tool':False,'maker_scope':False,'environment':False,'copy_current':False,'release_read':False,'fork':False,'save':False,'delete_file':False,'delete_workspace':False,'release_delete_info':False,'delete_release':True,'frontend':False,'validate':False,'job':False,'cancel':False,'publish':True,'mount':True,'unmount':True,'town':True,'pulse':True,'reconcile':True,'state':False,'draft':False,'apply':True,'view':False,'graph_validate':False}
    for name,mutation in methods.items():services.rpc('studio_'+name,lambda b,p,name=name:getattr(b.studio,name)(p),mutation=mutation)
