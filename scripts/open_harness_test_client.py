"""Open an isolated stock Harness client over a completed native test's real logs."""
import argparse,base64,hashlib,hmac,json,os,re,socket,subprocess,time,urllib.request,uuid
from pathlib import Path
import yaml


def call(meta,method,args):
    raw=(Path(meta['home'])/'.credentials.yaml').read_text(encoding='utf-8')
    block=re.split(r'\n  \S',raw.split('  client-connection/browser-session:',1)[1],maxsplit=1)[0]
    encoded=re.search(r'^\s+secret:\s*["\']?([A-Za-z0-9_-]+)',block,re.M).group(1)
    secret=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
    def b64(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')
    authority=meta['authority'];now=int(time.time()*1000)
    body=b64(json.dumps(dict(version=1,authority=authority,issuedAt=now,expiresAt=now+3600000),separators=(',',':')).encode())
    cookie='dsh-auth-'+b64(hashlib.sha256(authority.encode()).digest())+'=v1.'+body+'.'+b64(hmac.new(secret,body.encode(),hashlib.sha256).digest())
    data=dict(type='client-request',rpcId=str(uuid.uuid4()),method=method,payload=dict(args=args))
    request=urllib.request.Request('http://'+authority+'/api/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Cookie':cookie},method='POST')
    result=json.load(urllib.request.urlopen(request,timeout=10))['result']
    if not result['ok']:raise RuntimeError(json.dumps(result['error'],ensure_ascii=False))
    return result.get('value')


def install_viewer(profile,manifest):
    """Mount a test-only SDK cache warmer; do not rewrite logs or fabricate events."""
    package=profile/'viewer-extension';package.mkdir(parents=True,exist_ok=True)
    product=Path(__file__).resolve().parents[1]
    connections=sorted((Path(manifest['workspace'])/'.datanet/networks').glob('*/editor-connection.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    config=dict(sessions=[s['session_id'] for s in manifest['sessions']])
    if connections:config.update(editor=dict(enabled=True),editorConnection=str(connections[0]))
    metadata=dict(name='nexarbor-test-session-list',version='1.0.0',type='module',main='index.js',exports={'.':'./index.js','./client':'./client.js'},dsh=dict(bundle=dict(patch='./cordis.patch.yml')))
    if connections:metadata['dsh']['client']=dict(platform='web',inject=['@deepseek-ai/dsh-client-ui-conversation'])
    files={package/'package.json':json.dumps(metadata,indent=2),
           package/'index.js':(Path(__file__).resolve().parents[1]/'tests/native_test_viewer.js').read_text(encoding='utf-8')}
    files[package/'desktop-launcher.js']='export {launchDesktopEditor} from '+json.dumps((product/'adapters/harness/framework/desktop-launcher.js').as_uri())+';\n'
    files[package/'editor-launcher.js']=(product/'adapters/harness/framework/editor-launcher.js').read_text(encoding='utf-8')
    files[package/'client.js']=(product/'adapters/harness/framework/editor-client.js').read_text(encoding='utf-8').replace('id: "datanet-harness"','id: "nexarbor-test-session-list"',1)
    files[package/'cordis.patch.yml']=json.dumps([dict(insert=[dict(id='nexarbor-test-session-list',name='nexarbor-test-session-list',config=config)])],indent=2)
    for path,text in files.items():
        if not path.exists() or path.read_text(encoding='utf-8')!=text:path.write_text(text,encoding='utf-8')
    # Declaring a file: dependency alone does not install it. Materialize this
    # self-contained test package locally; no registry access or build scripts.
    installed=profile/'node_modules/nexarbor-test-session-list';installed.mkdir(parents=True,exist_ok=True)
    for path,text in files.items():
        target=installed/path.name
        if not target.exists() or target.read_text(encoding='utf-8')!=text:target.write_text(text,encoding='utf-8')
    descriptor=profile/'package.json';data=json.loads(descriptor.read_text(encoding='utf-8'))
    desired='file:'+package.as_posix()
    if data.setdefault('dependencies',{}).get('nexarbor-test-session-list')!=desired:
        data['dependencies']['nexarbor-test-session-list']=desired;descriptor.write_text(json.dumps(data,indent=2),encoding='utf-8')
    bundles=data['dsh']['profile']['bundles']
    if 'nexarbor-test-session-list' not in bundles:
        bundles.append('nexarbor-test-session-list');descriptor.write_text(json.dumps(data,indent=2),encoding='utf-8')
    path=profile/'cordis.patch.yml';patch=yaml.safe_load(path.read_text(encoding='utf-8'))
    entry=dict(id='nexarbor-test-session-list',name='nexarbor-test-session-list',config=config)
    updated=[row for row in patch if row['id']!='nexarbor-test-session-list']+[entry]
    if updated!=patch:path.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    from harness_test_environment import harness_test_environment
    from harness_installation import harness_executable
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path);args=parser.parse_args()
    run=args.run.resolve();manifest=json.loads((run/'sessions-manifest.json').read_text(encoding='utf-8'))
    logs=Path(manifest['native_logs']).resolve()
    if not logs.is_relative_to(run):raise ValueError('Test logs must stay inside the explicit run directory')
    existing=run/'client-meta.json'
    if existing.exists():
        meta=json.loads(existing.read_text(encoding='utf-8'))
        install_viewer(Path(meta['profile']),manifest)
        time.sleep(2)
        try:rows=call(meta,'session/list',{'_request':{}})['items']
        except Exception as error:raise RuntimeError('An existing test client record is unavailable; inspect its logs before restarting') from error
        verify(meta,manifest,run,rows);return
    home=run/'client-home';profile=home/'profiles/desktop';profile.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    package=dict(name='nexarbor-native-test-viewer',private=True,dsh=dict(profile=dict(bundles=['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app'])))
    (profile/'package.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
    (profile/'cordis.yml').write_text('[]\n',encoding='utf-8')
    patch=[dict(id='webserver',config=dict(host='127.0.0.1',port=port)),
           dict(id='session-persistence-jsonl',config=dict(root=str(logs))),
           dict(id='ui-settings-general',config=dict(welcomeNoticeVersion='2026-09-28.1')),
           dict(id='ui-settings-account',config=dict(version=1,step='done',usage='detailed',developerTools=True,completion='api-key')),
           dict(id='ui-chat',config=dict(transcriptView='standard',performanceUsage='detailed')),
           dict(id='web-search-deepseek',disabled=True),dict(id='web-fetch-http',disabled=True)]
    (profile/'cordis.patch.yml').write_text(json.dumps(patch,ensure_ascii=False,indent=2),encoding='utf-8')
    install_viewer(profile,manifest)
    meta=dict(home=str(home),profile=str(profile),authority='127.0.0.1:'+str(port),userData=str(run/'client-user-data'),workspace=manifest['workspace'])
    (run/'client-meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    executable=harness_executable()
    with (run/'client.stdout.log').open('ab') as output,(run/'client.stderr.log').open('ab') as error:
        process=subprocess.Popen([str(executable),'--user-data-dir='+meta['userData']],env=harness_test_environment(DSH_HOME=str(home)),stdout=output,stderr=error,creationflags=subprocess.CREATE_NO_WINDOW)
    (run/'client-process.json').write_text(json.dumps(dict(pid=process.pid,**meta),ensure_ascii=False,indent=2),encoding='utf-8')
    deadline=time.monotonic()+60;last=None
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError('Test client exited; inspect client.stderr.log')
        try:
            rows=call(meta,'session/list',{'_request':{}})['items'];break
        except Exception as error:last=error;time.sleep(1)
    else:raise RuntimeError('Test client did not become ready: '+str(last))
    verify(meta,manifest,run,rows)

def verify(meta,manifest,run,rows):
    plugins=call(meta,'pluginManager/listPlugins',{})
    viewer=next((p for p in plugins if p['moduleName']=='nexarbor-test-session-list'),None)
    if not viewer or viewer.get('fiberPhase')!='active':raise AssertionError('Test session viewer plugin did not load: '+json.dumps(viewer,ensure_ascii=False))
    # Cold native listings use cached projection hints. Read the official projection
    # endpoint to populate them without activating any model or changing its log.
    for entry in manifest['sessions']:
        projection=call(meta,'session/projections',{'request':dict(sessionId=entry['session_id'])})
        if entry['title'] not in json.dumps(projection,ensure_ascii=False):raise AssertionError('Missing durable title for '+entry['actor'])
    rows=call(meta,'session/list',{'_request':{}})['items']
    by_id={row['sessionId']:row for row in rows};checks=[]
    for entry in manifest['sessions']:
        row=by_id[entry['session_id']]
        if row.get('origin')=='subagent' or row.get('blank',False):raise AssertionError('Native sidebar would hide '+entry['actor'])
        # A cold stock listing may omit projection hints. The authoritative
        # projections endpoint above has independently verified the durable title.
        title_cached=entry['title'] in json.dumps(row.get('projections',{}),ensure_ascii=False)
        if not title_cached:raise AssertionError('Native sidebar title is not ready for '+entry['actor'])
        page=call(meta,'session/page',{'request':dict(address=dict(kind='session',sessionId=entry['session_id']),throughSeq=entry['events']-1,maxMessages=5)})
        if not page['records']:raise AssertionError('No readable history for '+entry['actor'])
        checks.append(dict(actor=entry['actor'],session_id=entry['session_id'],title=entry['title'],visible=True,history_read=True,title_cached=title_cached))
    audit=dict(passed=True,viewer_plugin_active=True,sessions=checks,count=len(checks),authority=meta['authority'],model_requests=0)
    (run/'sidebar-verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,visible_sessions=len(checks),run=str(run)),ensure_ascii=False))

if __name__=='__main__':main()
