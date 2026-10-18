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
from .contract import factory,manifest
from jsonschema import Draft202012Validator

PROJECT=Path(__file__).resolve().parents[7]
RESOURCE=Path(__file__).resolve().parents[3]/'resources'
TEXT={'.py','.json','.md','.txt','.toml'}

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
        self.library=read_json(self.root/'library.json',{})
        for name,source in getattr(backend.components,'standard_modules',{}).items():
            if name in self.library:continue
            files=sources(source['folder']);fingerprint=digest(files);spec=source['manifest']
            destination=self.root/'releases'/name/spec['version']/fingerprint
            for file,content in files.items():
                path=destination/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
            self.library[name]=dict(id=name,version=spec['version'],folder=str(destination.relative_to(self.root)),digest=fingerprint,manifest=spec,defaults=read_json(destination/'example.json',{}).get('config',{}))
        write_json(self.root/'library.json',self.library)
        self.jobs={};self.processes={};self.pool=ThreadPoolExecutor(max_workers=2)
        self.lock=threading.RLock();self.running=False;self.loop=asyncio.new_event_loop();self.bindings={}
        self.run_state=dict(status='idle',completed=0,requested=0)
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
            spec,create=factory(folder)
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
        return dict(workspaces=[dict(id=p.name,**read_json(p/'workspace.json',{})) for p in self.work.iterdir() if p.is_dir()],
                    samples=samples,library=self.library,jobs=list(self.jobs.values()),contract='nexarbor-module/v2')
    def create(self,p):
        sample=p.get('sample','blank');definitions=read_json(RESOURCE/'samples.json',[])
        selected=next((s for s in definitions if s['id']==sample),None)
        if selected is None:raise ValueError('Unknown sample')
        id='module-'+uuid4().hex[:10];folder=self.work/id;folder.mkdir()
        template=RESOURCE/'templates'/sample
        for name,content in read_json(template.with_suffix('.json'),{}).items():
            path=folder/name
            if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('Invalid template')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        (folder/'AGENTS.md').write_text((RESOURCE/'AGENTS.md').read_text(encoding='utf-8'),encoding='utf-8')
        (folder/'MODULE_GUIDE.md').write_text((RESOURCE/'MODULE_GUIDE.md').read_text(encoding='utf-8'),encoding='utf-8')
        if selected.get('reference'):
            source=PROJECT/selected['reference'];reference=folder/'reference';reference.mkdir()
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
        write_json(folder/'workspace.json',{'label':selected['name'],'sample':sample})
        write_json(self.root/'metadata'/f'{id}.json',{'sample':sample,'label':selected['name']})
        return self.read(dict(id=id))
    def read(self,p):
        folder=self.folder(p['id']);files=sources(folder);files.pop('workspace.json',None)
        original=read_json(self.root/'baselines'/f'{p["id"]}.json',{})
        references={str(f.relative_to(folder)):f.read_text(encoding='utf-8') for f in (folder/'reference').glob('*.py')} if (folder/'reference').exists() else {}
        return dict(id=p['id'],directory=str(folder),files=files,original=original,references=references,digest=digest(files))
    def dependencies(self,p):
        folder=self.folder(p['id']);catalog=read_json(folder/'dependencies/catalog.json',[])
        known={item['id']:item for item in catalog}
        for name in p.get('modules',list(self.library)):
            release=self.library[name];source=self.root/release['folder'];target=folder/'dependencies'/name;target.mkdir(parents=True,exist_ok=True)
            for file in ['module.json','README.md','example.json']:
                if (source/file).exists():shutil.copyfile(source/file,target/file)
            known[name]=dict(id=name,version=release['version'],manifest=f'dependencies/{name}/module.json',guide=f'dependencies/{name}/README.md')
        write_json(folder/'dependencies/catalog.json',list(known.values()));return self.read(p)
    def release_read(self,p):
        release=self.library[p['module']];files=sources(self.root/release['folder']);files.pop('workspace.json',None)
        return dict(id=release['id'],files=files,original=files,references={},readOnly=True,release=release)
    def fork(self,p):
        release=self.release_read(p);workspace=self.create({'sample':'blank'});folder=self.folder(workspace['id'])
        for name,content in release['files'].items():
            if name in ['AGENTS.md','MODULE_GUIDE.md']:continue
            path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        write_json(self.root/'baselines'/f'{workspace["id"]}.json',sources(folder))
        write_json(folder/'workspace.json',{'label':release['id']+' · 修改副本','sample':'blank'})
        return self.read({'id':workspace['id']})
    def save(self,p):
        path=self.path(p['id'],p['file'])
        relative=path.relative_to(self.folder(p['id'])).as_posix().casefold()
        if relative in ['agents.md','module_guide.md','workspace.json'] or relative.startswith(('reference/','dependencies/')):raise PermissionError('Host guide and references are read-only')
        current=path.read_text(encoding='utf-8') if path.exists() else ''
        if p.get('expected')!=sha256(current.encode()).hexdigest():raise ValueError('File changed outside the editor; reload before saving')
        content=p['content']
        if not isinstance(content,str) or len(content.encode())>1024*1024:raise ValueError('Source exceeds 1 MiB')
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(content,encoding='utf-8');temporary.replace(path)
        return self.read(p)
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
                with self.lock:
                    if job['status']!='running' or getattr(self,'closed',False):return
                    sample=read_json(self.root/'metadata'/f'{p["id"]}.json',{}).get('sample','blank')
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
        spec=json.loads(files['module.json']);name=spec['id']
        if any(module==name for _,module in self.backend.modules.instances):raise ValueError('Unmount active instances before replacing their module')
        if any(dep not in self.library for dep in spec['requires']):raise ValueError('Publish dependencies first')
        destination=self.root/'releases'/name/spec['version']/fingerprint
        destination.mkdir(parents=True,exist_ok=True)
        for file,content in files.items():
            path=destination/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
        old=self.library.copy()
        manifest(destination)
        self.library[name]=dict(id=name,version=spec['version'],folder=str(destination.relative_to(self.root)),digest=fingerprint,manifest=spec,defaults=read_json(destination/'example.json',{}).get('config',{}))
        try:self._load_releases()
        except BaseException:self.library=old;raise
        write_json(self.root/'library.json',self.library)
        return self.library[name]
    def mount(self,p):
        if self.running:raise ValueError('Wait until the signal completes')
        module=self.library[p['module']];folder=self.root/module['folder']
        config=p.get('config',read_json(folder/'example.json',{}).get('config',{}))
        self.backend.modules.mount(p['node'],p['module'],config,{},access=p.get('access'))
        self._bind();return self.state()
    def unmount(self,p):
        if self.running:raise ValueError('Wait until the signal completes')
        self.backend.modules.unmount(p['node'],p['module']);self._bind();return self.state()
    def _bind(self):
        from .sdk_services import bind_modules
        bind_modules(self.backend)
    def town(self,p):
        if self.running:raise ValueError('Signal is active')
        if any(id.startswith('town/') for id in self.backend.network.nodes):return self.state()
        document=read_json(RESOURCE/'presets/module_test.json',{})
        self.apply(dict(document=document,base_commit=self.backend.store.head,layout={}))
        return self.state()
    def pulse(self,p):
        if self.running:raise ValueError('Signal is active')
        self.running=True;cycles=p.get('cycles',1)
        self.run_state=dict(status='running',completed=0,requested=cycles)
        try:
            runtime=self.backend.network.signals
            runtime.checkpoint=lambda:self.backend.dispatch('save',{})
            async def completed(pulse,report):self.run_state['completed']+=1
            report=self.loop.run_until_complete(self.backend.network.nodes[p.get('pulse','town/pulse')].run(runtime,cycles=cycles,timeout_seconds=p.get('timeout_seconds',min(3600,300*cycles)),cycle_complete=completed))
            self.run_state['status']='idle' if report['status']=='completed' else 'failed'
            if report['status']!='completed':self.run_state['error']='信号未完成闭环：'+report['status']
            self.running=False
            return dict(report=report,state=self.state())
        except Exception as error:
            self.run_state.update(status='failed',error=str(error));raise
        finally:self.running=False
    def state(self,p=None):
        document=network_document(self.backend.network,self.backend.directory)
        files={**self.backend.document_files(),**{str(n.file_path.relative_to(self.backend.directory)):n.file_path.read_text(encoding='utf-8') if n.file_path.exists() else '' for n in self.backend.network.nodes.values() if hasattr(n,'file_path') and n.file_path.is_relative_to(self.backend.directory)}}
        return dict(mode='组件开发 · Harness后端',live=dict(document=dict(network=document,files=files),commit=self.backend.store.head,sessions={id:dict(name=self.backend.network.nodes[id].name,**value) for id,value in self.backend.agents.items() if id in self.backend.network.nodes}),draft=read_json(self.root/'draft.json',None),
                    job=dict(self.run_state),studio=True)
    def draft(self,p):
        previous=read_json(self.root/'draft.json',{'version':0})
        if p.get('expected_version',0)!=previous['version']:raise ValueError('Draft changed in another window; reload')
        value=dict(document=p['document'],layout=p.get('layout',{}),version=previous['version']+1,base_commit=p.get('base_commit'),applied=False)
        write_json(self.root/'draft.json',value);return value
    def apply(self,p):
        if self.running:raise ValueError('Wait until execution completes')
        if p.get('base_commit')!=self.backend.store.head:raise ValueError('Network changed; reload before applying')
        document=p['document'];candidate=_build(document['network'],self.backend.directory)
        for node in candidate.nodes.values():
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
            candidate=_build(p['document']['network'],self.backend.directory)
            from jsonschema import validate
            for node in candidate.nodes.values():
                for name,spec in node.modules.items():
                    if name not in self.library:raise ValueError('Unknown published module: '+name)
                    definition=self.library[name]['manifest']
                    if node.signal_type not in definition['node_types']:raise ValueError(name+' cannot mount on '+node.signal_type)
                    validate(spec['config'],definition['config_schema'])
            return dict(valid=True,errors=[],warnings=[])
        except Exception as error:return dict(valid=False,errors=[dict(path='network',message=str(error))],warnings=[])
    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        for process in list(self.processes.values()):self._kill(process)
        self.pool.shutdown(wait=True,cancel_futures=True)
        # A Backend can also be hosted by an existing asyncio application.
        # Only drive our private loop when no other loop owns this thread.
        try:asyncio.get_running_loop()
        except RuntimeError:self.loop.run_until_complete(self.backend.network.signals.close())
        # An external async host owns its runtime shutdown. Do not queue a save
        # after Backend.close has already closed the checkpoint database.
        self.loop.close()

def register(services):
    def install(backend):backend.studio=Studio(backend)
    services.initializers.append(install)
    services.finalizers.append(lambda b:b.studio.close())
    services.graph_loaders.append(lambda b:b.studio._bind())
    services.snapshotters.append(lambda b:{'studio_releases':b.studio.library})
    def restore(b,document):
        b.studio.library=document.get('studio_releases',b.studio.library);b.studio._load_releases()
    services.restorers.append(restore)
    methods={'catalog':False,'create':False,'read':False,'dependencies':False,'release_read':False,'fork':False,'save':False,'validate':False,'job':False,'cancel':False,'publish':True,'mount':True,'unmount':True,'town':True,'pulse':True,'state':False,'draft':False,'apply':True,'view':False,'graph_validate':False}
    for name,mutation in methods.items():services.rpc('studio_'+name,lambda b,p,name=name:getattr(b.studio,name)(p),mutation=mutation)
