"""Prepare a fresh native-route hone retest using the fixed public inputs."""
import hashlib,json,re,shutil,socket,sys,tarfile,uuid
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'build/hone-fixed-20261014-r6'
VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
BASE=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'build'/('hone-native-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
if not BASE.is_relative_to(ROOT/'build'):raise ValueError('Test directory must be inside product build')
BASE.mkdir(exist_ok=False);HOME=BASE/'home';PROFILE=HOME/'profiles/desktop';WORK=BASE/'workspace'
PROFILE.mkdir(parents=True);WORK.mkdir()
for name in ['client_api.py','monitor.cjs','state.py','judge.py','cli_judge.py','finalize.py','materials.json','grader-path.txt']:
    shutil.copy2(OLD/name,BASE/name)
shutil.copytree(OLD/'workspace/task',WORK/'task',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
public=(OLD/'project-source.txt').read_text(encoding='utf-8')
public=re.sub(r'E:[\\/]DataNet-模块化成品[\\/]build[\\/]hone-fixed-[^\\/\s]+[\\/]workspace[\\/]task',lambda _m:str(WORK/'task'),public)
(BASE/'project-source.txt').write_text(public,encoding='utf-8')
(BASE/'input-baseline.json').write_text(json.dumps({str(p.relative_to(WORK/'task')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (WORK/'task').rglob('*') if p.is_file()},ensure_ascii=False,indent=2),encoding='utf-8')
sid='session-'+str(uuid.uuid4())
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
cfg=json.loads((OLD/'test-config.json').read_text(encoding='utf-8-sig'))
cfg.update(workspace=str(WORK),storage=str(WORK/'.datanet'),modelRoute={'provider':'deepseek-official','model':'deepseek-flash','reasoningEffort':'high','maxTokens':50000})
(BASE/'test-config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
# Keep the shipped provider/default model patch; override only the test workspace and UI port.
patch='''- id: webserver
  config:
    host: 127.0.0.1
    port: PORT
- id: ui-settings-general
  config:
    welcomeNoticeVersion: 2026-09-28.1
- id: ui-settings-account
  config:
    version: 1
    step: done
    usage: detailed
    developerTools: true
    completion: api-key
- id: ui-chat
  config:
    transcriptView: standard
    performanceUsage: detailed
- id: datanet-harness
  config: CONFIG
  disabled: false
- id: datanet-agent-loop
  disabled: false
'''.replace('PORT',str(port)).replace('CONFIG',json.dumps(cfg,ensure_ascii=False))
(PROFILE/'cordis.patch.yml').write_text(patch,encoding='utf-8')
archive_path=ROOT/'build'/('datanet-harness-'+VERSION+'.tgz')
pkg=json.loads((OLD/'home/profiles/desktop/package.json').read_text(encoding='utf-8'))
pkg['dependencies']['datanet-harness']='file:'+str(archive_path).replace('\\','/')
(PROFILE/'package.json').write_text(json.dumps(pkg,ensure_ascii=False,indent=2),encoding='utf-8')
dest=PROFILE/'node_modules/datanet-harness';dest.mkdir(parents=True)
with tarfile.open(archive_path,'r:gz') as archive:
    for member in archive:
        relative=Path(member.name).relative_to('package');target=dest/relative
        if not target.resolve().is_relative_to(dest.resolve()):raise ValueError('Archive path escapes package')
        if member.isdir():target.mkdir(parents=True,exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as src,target.open('wb') as out:shutil.copyfileobj(src,out)
shutil.copytree(OLD/'home/profiles/desktop/node_modules/zod',PROFILE/'node_modules/zod')
# Credentials remain local to the isolated test home; never print their contents.
shutil.copy2(OLD/'home/.credentials.yaml',HOME/'.credentials.yaml')
meta=dict(base=str(BASE),home=str(HOME),workspace=str(WORK),profile=str(PROFILE),authority=f'127.0.0.1:{port}',provider='deepseek-official',model='deepseek-flash',reasoningEffort='high',contextWindow=500000,maxTokens=50000,version=VERSION,sessionId=sid,title='hone 原生缓存机制端到端 · '+VERSION,totalMinutes=30,cooperativeRequestLimit=300,baseline=str(OLD))
(BASE/'meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
task=(OLD/'root-task.txt').read_text(encoding='utf-8').replace(str(OLD).replace('\\','/'),str(BASE).replace('\\','/'))
(BASE/'root-task.txt').write_text(task,encoding='utf-8')
runner=(OLD/'run_client.py').read_text(encoding='utf-8')
a=runner.index("while time.time()*1000<meta['deadlineAt']:");b=runner.index("items=call('session/list'",a)
runner=runner[:a]+'''while time.time()*1000<meta['deadlineAt']:
    time.sleep(min(5,max(0,(meta['deadlineAt']-time.time()*1000)/1000)))
    items=call('session/list',{'_request':{}}).get('items',[])
    if time.time()*1000-meta['startedAt']>10000 and not any(item.get('running') for item in items):
        save('completion-stop.json',{'at':int(time.time()*1000),'stopped':[]})
        print('All client sessions idle; test observation ended.',flush=True)
        raise SystemExit(0)
'''+runner[b:]
(BASE/'run_client.py').write_text(runner,encoding='utf-8')
sys.path.insert(0,str(ROOT/'tests'))
from test_components import Rpc
b=Rpc(WORK/'.datanet/networks'/sid.encode().hex(),binary=True)
try:
    b.result('load_root_network',package='project_root',entry_point='root')
    result=b.result('write',actor='root',target='root/project',key='content',value=public,strength=100)
    if result['status']!='ok':raise RuntimeError(result)
    b.result('save')
finally:b.close()
print(json.dumps(dict(base=str(BASE),sessionId=sid,authority=meta['authority'],version=VERSION,totalMinutes=30),ensure_ascii=False))
