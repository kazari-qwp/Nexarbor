"""制作工作副本、不可变发布与验证任务；沿用原宿主的文件和 Git 协议。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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
from .contract import manifest,frontend_file
from .modules import ProjectModules

PROJECT=Path(__file__).resolve().parents[2]
RESOURCE=PROJECT/'resources/studio'
SKILL_GUIDES=RESOURCE/'skills/make-components/references'
SKILL_LESSONS=[RESOURCE/'skills/nexarbor-basics/references/lessons',SKILL_GUIDES/'lessons',RESOURCE/'skills/make-network/references/lessons']
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
    def __init__(self,backend,library=None,*,agent_run=None,instantiate=None,ports=None,port_contracts=None):
        self.backend=backend;self.root=backend.directory/'studio';self.root.mkdir(exist_ok=True)
        self.work=self.root/'work';self.work.mkdir(exist_ok=True)
        self.agent_run=agent_run;self.instantiate=instantiate;self.ports=ports or {};self.port_contracts=port_contracts or {}
        self.standard_releases={}
        for name,folder in (library or {}).items():
            folder=Path(folder).resolve();spec=manifest(folder);files=sources(folder);defaults=read_json(folder/'example.json',{})
            self.standard_releases[name]=dict(id=name,version=spec['version'],folder=str(folder),digest=digest(files),manifest=spec,defaults=defaults.get('config',{}),mount_defaults=defaults,origin='project')
        self.library={**self.standard_releases,**read_json(self.root/'library.json',{})}
        self.removed=set(read_json(self.root/'removed-modules.json',[]));self.jobs={};self.processes={};self.pool=ThreadPoolExecutor(max_workers=2);self.lock=threading.RLock();self.running=False;self.closed=False
        self.workspace_busy=lambda id:False
        self._load_releases()

    def _load_releases(self):
        self.modules=ProjectModules(self.backend,{name:self.root/release['folder'] for name,release in self.library.items()},agent_run=self.agent_run,instantiate=self.instantiate)

    def persist_library(self):write_json(self.root/'library.json',{name:release for name,release in self.library.items() if release.get('origin')!='project'})

    def catalog(self,p=None):
        library={name:dict(release,available=True,name=release['manifest'].get('name') or name) for name,release in self.library.items()}
        return dict(workspaces=[dict(id=folder.name,**read_json(folder/'workspace.json',{})) for folder in self.work.iterdir() if folder.is_dir()],samples=read_json(RESOURCE/'samples.json',[]),library=library,jobs=list(self.jobs.values()),contract='nexarbor-module/v4')

    def prepare_agent(self,p):self._write_guides(self.folder(p['id']))

    def folder(self,id):
        if not isinstance(id,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',id):raise ValueError('Invalid work copy ID')
        target=(self.work/id).resolve()
        if not target.is_relative_to(self.work.resolve()) or not target.is_dir():raise ValueError('Unknown work copy')
        return target

    def path(self,id,name):
        root=self.folder(id);target=(root/name).resolve()
        if not target.is_relative_to(root) or target.suffix not in TEXT:raise ValueError('File must be source inside the work copy')
        return target

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
            write_json(folder/'network.json',dict(network={'nodes':[]},files={}))
            write_json(folder/'runtime.json',dict(templates=[]))
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
        from .git_baselines import save as baseline
        write_json(self.root/'baselines'/f'{id}.json',baseline(self,id,original))
        write_json(folder/'workspace.json',{'label':p.get('name') or {'module':selected['name'],'tool':'制作工具','network':'制作网络预设'}[kind],'sample':sample,'kind':kind,'display_folder':p.get('display_folder')})
        write_json(self.root/'metadata'/f'{id}.json',{'sample':sample,'kind':kind,'label':selected['name']})
        return self.read(dict(id=id))

    def read(self,p):
        folder=self.folder(p['id']);files=sources(folder);files.pop('workspace.json',None)
        from .git_baselines import read as baseline
        original=baseline(self,read_json(self.root/'baselines'/f'{p["id"]}.json',{}))
        owned,references=split_files(files)
        if (folder/'reference').exists():
            for f in (folder/'reference').rglob('*'):
                if f.is_file() and f.suffix in TEXT:
                    if not f.resolve().is_relative_to(folder.resolve()) or f.stat().st_size>1024*1024:raise ValueError('参考资料越界或超过1MiB')
                    references[f.relative_to(folder).as_posix()]=f.read_text(encoding='utf-8')
        metadata=read_json(folder/'workspace.json',{})
        return dict(id=p['id'],directory=str(folder),files=owned,original=split_files(original)[0],references=references,digest=digest(files),identity=dict(module_id=metadata['branch_module'],immutable=True) if metadata.get('immutable_revision') and metadata.get('branch_module') else None,**{k:metadata.get(k,default) for k,default in [('display_folder',None),('kind','module'),('origin',None)]})

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
            from .discovery import list_files
            return list_files(self.read(p),args)
        if name=='read_file':
            path=self.path(p['id'],args['path'])
            if path.name=='workspace.json':raise PermissionError('宿主制作资料不作为组件文件')
            if path.stat().st_size>1024*1024:raise ValueError('文件超过 1 MiB')
            from .text_pages import text_page
            return dict(path=args['path'],**text_page(path.read_text(encoding='utf-8'),args))
        if name in ('write_file','edit_file'):
            path=self.path(p['id'],args['path']);old=path.read_text(encoding='utf-8') if path.exists() else ''
            content=args['content'] if name=='write_file' else old.replace(args['old'],args['new'],1)
            if name=='edit_file' and (not args['old'] or old.count(args['old'])!=1):raise ValueError('替换文本必须在文件中唯一匹配；先重新读取')
            value=self.save(dict(id=p['id'],file=args['path'],content=content,expected=sha256(old.encode()).hexdigest()))
            return dict(saved=args['path'],digest=value['digest'])
        if name=='catalog_modules':
            from .discovery import catalog_modules
            return catalog_modules(self.catalog()['library'],args,p.get('hidden',[]))
        if name=='catalog_ports':return self.catalog_ports(args,p['id'])
        if name=='network_patch':
            if read_json(folder/'workspace.json',{}).get('kind')!='network':raise ValueError('只有网络制作副本可分批合并网络')
            file=folder/'network.json';old=file.read_text(encoding='utf-8');document=json.loads(old)
            if args.get('replace'):document=dict(network=dict(nodes=[]),files={})
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

    def save(self,p):
        path=self.path(p['id'],p['file'])
        relative=path.relative_to(self.folder(p['id'])).as_posix().casefold()
        if relative in [name.casefold() for name in (*GUIDES,'workspace.json')] or relative.startswith(('reference/','dependencies/','lessons/')):raise PermissionError('规范文件与参考资料只读')
        current=path.read_text(encoding='utf-8') if path.exists() else ''
        if p.get('expected')!=sha256(current.encode()).hexdigest():raise ValueError('File changed outside the editor; reload before saving')
        content=p['content']
        if not isinstance(content,str) or len(content.encode())>1024*1024:raise ValueError('Source exceeds 1 MiB')
        metadata=read_json(self.folder(p['id'])/'workspace.json',{})
        if relative=='module.json' and metadata.get('immutable_revision') and json.loads(content).get('id')!=metadata['branch_module']:
            raise ValueError('宿主已固定修订模块 ID 为 '+metadata['branch_module']+'，请保留此 ID')
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
        for name in GUIDES:(folder/name).write_text((SKILL_GUIDES/name).read_text(encoding='utf-8'),encoding='utf-8')
        for directory in SKILL_LESSONS:shutil.copytree(directory,folder/'lessons',dirs_exist_ok=True)
        shutil.copyfile(RESOURCE/'skills/inspect-network/references/测试环境.md',folder/'lessons/07-environment.md')

    def append_requirement(self,p):
        """Trusted maker host appends requirements; authors retain read-only references."""
        update=p.get('update',{})
        text=update.get('text') if isinstance(update,dict) else None
        if not isinstance(text,str) or not text.strip() or len(text)>16000:raise ValueError('追加要求为1至16000字符')
        if update.get('id')!=sha256(text.encode()).hexdigest():raise ValueError('追加要求摘要不匹配')
        if not isinstance(update.get('source'),str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',update['source']):raise ValueError('追加要求来源无效')
        path=self.path(p['id'],'reference/追加要求.json')
        with self.lock:
            document=read_json(path,dict(format='nexarbor-maker-requirements/v1',updates=[]))
            if document.get('format')!='nexarbor-maker-requirements/v1' or not isinstance(document.get('updates'),list):raise ValueError('追加要求参考文件格式不符')
            if any(row['id']==update['id'] for row in document['updates']):return dict(reference='reference/追加要求.json',duplicate=True)
            if len(document['updates'])>=32:raise ValueError('每个工作副本最多保留32条追加要求')
            document['updates'].append({key:update[key] for key in ['id','source','text','received']})
            if len(json.dumps(document,ensure_ascii=False).encode())>512*1024:raise ValueError('追加要求总计超过512KiB')
            write_json(path,document)
        return dict(reference='reference/追加要求.json',count=len(document['updates']))

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

    def job(self,p):return self.jobs[p['job']].copy()

    def cancel(self,p):
        with self.lock:
            job=self.jobs[p['job']];job['status']='cancelled'
            process=self.processes.get(p['job'])
        if process:self._kill(process)
        return job.copy()

    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        for process in list(self.processes.values()):self._kill(process)
        self.pool.shutdown(wait=True,cancel_futures=True)

    def catalog_ports(self,args,workspace):
        from .discovery import page
        query=args.get('query','').lower();rows=[]
        properties=self.backend.extension_state.get('node_properties',{})
        for ref,definition in self.ports.items():
            if query and query not in (ref+' '+definition.get('description','')).lower():continue
            offers=[dict(node=node,channels=offer['channels']) for node,item in properties.items() for offer in item.get('offered_ports',[]) if offer['ref']==ref]
            row=dict(ref=ref,description=definition.get('description',''),offered_count=len(offers),offers=offers[:12])
            if args.get('details') or query==ref.lower():
                row['parameters']=definition['parameters']
                if ref in self.port_contracts:row['result_contract']=self.port_contracts[ref]
            rows.append(row)
        offset,limit=page(args,30)
        return dict(ports=rows[offset:offset+limit],total=len(rows),next_offset=offset+limit if offset+limit<len(rows) else None,hint='宿主把 offered_ports 装成实际 CallableTool；模块经 access 到达后调用。')

    @staticmethod
    def _kill(proc):
        if proc.poll() is not None:return
        if os.name=='nt':subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
        else:proc.kill()

    def validate(self,p):
        folder=self.folder(p['id']);files=sources(folder)
        id=uuid4().hex;job=dict(id=id,workspace=p['id'],status='running',digest=digest(files),log='',started=time.time())
        self.jobs[id]=job
        snapshot=self.root/'checks'/id;snapshot.mkdir(parents=True)
        for name,content in files.items():
            path=snapshot/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        timeout=p.get('timeout',30)
        if type(timeout) is not int or not 1<=timeout<=86400:raise ValueError('Validation timeout must be 1–86400 seconds')
        def run():
            env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONUTF8='1',PYTHONPATH=str(PROJECT),TEMP=str(self.root/'temp'),TMP=str(self.root/'temp'))
            Path(env['TEMP']).mkdir(exist_ok=True)
            log_path=snapshot/'validation.log'
            try:
                if (snapshot/'presets.json').exists() and read_json(folder/'workspace.json',{}).get('kind')!='network':
                    from .preset_work import check
                    result=check(snapshot,self.library)
                    job.update(status='passed',exit_code=0,log='PASS：复用已发布组件的配置方案、配置Schema；配置数量：'+str(len(result['presets']))+'。行为验证另看独立网络副本。');log_path.write_text(job['log'],encoding='utf-8');return
                kind=read_json(folder/'workspace.json',{}).get('kind','module')
                worker='app.studio.worker'
                if kind=='network':
                    from .network_work import check_work
                    result=check_work(snapshot,self.backend,self.library,workspace=p['id'],port_definitions=self.ports)
                    job['warnings']=result.get('warnings',[])
                    worker='app.studio.network_worker'
                from .environment import prepare
                fixture=prepare(self,dict(id=p['id'],source='candidate' if kind=='network' else 'current'),folder=snapshot,activate=False)
                if kind=='network' and result.get('outputs'):
                    views={item['file']:str(prepare(self,dict(id=p['id'],source='candidate',network_file=item['file']),folder=snapshot,activate=False)) for item in result['outputs']}
                    setup=read_json(fixture/'setup.json',{});setup['views']=views;write_json(fixture/'setup.json',setup)
                    job['outputs']=[dict(name=item['name'],file=item['file'],nodes=len(item['document']['network']['nodes'])) for item in result['outputs']]
                env.update(NEXARBOR_TEST_ENVIRONMENT=str(fixture),NEXARBOR_PROJECT_DIRECTORY=str(fixture/'runtime'))
                with self.lock:
                    if job['status']!='running' or getattr(self,'closed',False):return
                    sample=read_json(self.root/'metadata'/f'{p["id"]}.json',{}).get('sample','blank')
                    test_library=read_json(fixture/'setup.json',{})['modules']
                    env['NEXARBOR_TEST_MODULES']=json.dumps({name:str(fixture/relative) for name,relative in test_library.items()})
                    env['NEXARBOR_MAKER_KIND']=read_json(folder/'workspace.json',{}).get('kind','module')
                    proc=subprocess.Popen([sys.executable,'-m',worker,str(snapshot),sample],cwd=PROJECT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
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
            except Exception as error:
                from .diagnostics import error_message
                job.update(status='failed',log=error_message(error))
            finally:
                self.processes.pop(id,None);job['finished']=time.time()
        self.pool.submit(run);return job.copy()

    def publish(self,p):
        folder=self.folder(p['id']);files=sources(folder);fingerprint=digest(files)
        if not any(j['workspace']==p['id'] and j['status']=='passed' and j['digest']==fingerprint for j in self.jobs.values()):raise ValueError('Test the current source before publishing')
        metadata=read_json(folder/'workspace.json',{})
        if (folder/'presets.json').exists() and metadata.get('kind')!='network':
            from .preset_work import check
            return dict(kind='component-presets',workspace=p['id'],**check(folder,self.library))
        if metadata.get('kind')=='network':
            from .network_work import check_work
            result=check_work(folder,self.backend,self.library,port_definitions=self.ports)
            return dict(kind='network',id=p['id'],document=result['document'],runtime=result['runtime'],outputs=result['outputs'],name=p.get('name') or metadata['label'],display_folder=metadata.get('display_folder'),digest=fingerprint)
        spec=json.loads(files['module.json']);name=spec['id']
        if metadata.get('immutable_revision'):
            if metadata.get('branch_module')!=name:raise ValueError('修改分支的模块ID不可更换，请保留宿主分配的修订ID')
            if name in self.library and self.library[name]['digest']!=fingerprint:raise ValueError('该修订已发布；请从该版本建立新的修改副本')
        if name in ('tool_discovery','context.assembler'):raise PermissionError('官方扩展模块不能发布替代实现')
        if any(node.modules.get(name) is not None for node in self.backend.network):raise ValueError('Unmount active instances before replacing their module')
        if any(dep not in self.library for dep in spec['requires']):raise ValueError('Publish dependencies first')
        destination=self.root/'releases'/name/spec['version']/fingerprint
        from .project_sources import materialize
        materialize(destination,files,self.root)
        old=self.library.copy()
        manifest(destination)
        self.library[name]=dict(id=name,version=spec['version'],folder=str(destination.relative_to(self.root)),digest=fingerprint,manifest=spec,defaults=read_json(destination/'example.json',{}).get('config',{}),mount_defaults=read_json(destination/'example.json',{}),display_folder=metadata.get('display_folder'),origin_kind=metadata.get('kind','module'),origin=metadata.get('origin'))
        try:self._load_releases()
        except BaseException:self.library=old;raise
        self.removed.discard(name);write_json(self.root/'removed-modules.json',sorted(self.removed))
        self.persist_library()
        return self.library[name]
