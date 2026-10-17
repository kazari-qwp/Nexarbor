"""Attach to an installed Harness's authenticated native Session Remote API.

Credentials stay on the backend. No model loop, shell tools or transcripts are
implemented here: the existing Harness owns them and its workspace permissions.
"""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from uuid import uuid4
import yaml

def b64(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')

class HarnessRemote:
    def __init__(self,studio):
        self.studio=studio;self.authority=None;self.home=None;self.jobs={};self.closed=False
    def status(self,p=None):
        return dict(connected=bool(self.authority),authority=self.authority,jobs=[dict(j) for j in self.jobs.values()])
    def rpc(self,method,args,timeout=8):
        credential=yaml.safe_load((self.home/'.credentials.yaml').read_text(encoding='utf-8'))
        secret=credential['records']['client-connection/browser-session']['payload']['secret']
        key=base64.urlsafe_b64decode(secret+'='*(-len(secret)%4))
        now=int(time.time()*1000)
        body=b64(json.dumps(dict(version=1,authority=self.authority,issuedAt=now,expiresAt=now+60000),separators=(',',':')).encode())
        cookie='dsh-auth-'+b64(hashlib.sha256(self.authority.encode()).digest())+'=v1.'+body+'.'+b64(hmac.new(key,body.encode(),hashlib.sha256).digest())
        message=dict(type='client-request',rpcId=str(uuid4()),method=method,payload=dict(args=args))
        request=urllib.request.Request('http://'+self.authority+'/api/'+method,data=json.dumps(message).encode(),headers={'Content-Type':'application/json','Cookie':cookie},method='POST')
        result=json.load(urllib.request.urlopen(request,timeout=timeout))['result']
        if not result['ok']:raise RuntimeError(str(result.get('error','Harness request failed')))
        return result.get('value')
    def connect(self,p):
        saved=self.studio.root/'harness-connection.json'
        if not p.get('home') and not p.get('authority') and saved.is_file():
            try:return self.connect(json.loads(saved.read_text(encoding='utf-8')))
            except (OSError,ValueError,KeyError,RuntimeError):pass
        if not p.get('home') and not p.get('authority') and os.environ.get('DSH_HOME'):
            try:return self.connect(dict(home=os.environ['DSH_HOME']))
            except (OSError,ValueError,KeyError,RuntimeError):pass
        if not p.get('home') and not p.get('authority'):
            build=Path(__file__).resolve().parents[3]/'build'
            records=list(build.glob('*/client-meta.json'))+list(build.glob('*/*/client-meta.json'))
            for record in sorted(records,key=lambda path:path.stat().st_mtime,reverse=True):
                try:
                    meta=json.loads(record.read_text(encoding='utf-8'))
                    return self.connect(dict(home=meta['home'],authority=meta['authority']))
                except (OSError,ValueError,KeyError,RuntimeError):continue
        home=Path(p.get('home') or Path.home()/'.dsh').resolve()
        if not (home/'.credentials.yaml').is_file():raise ValueError('Choose the home directory used by your running Harness')
        if p.get('authority'):
            if not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}',p['authority']):raise ValueError('Only a loopback Harness is supported')
            candidates=[p['authority']]
        elif os.name=='nt':
            tasks=subprocess.check_output(['tasklist.exe','/FO','CSV','/NH','/FI','IMAGENAME eq DeepSeek Harness.exe'],encoding='utf-8',errors='replace')
            import csv,io
            pids={row[1] for row in csv.reader(io.StringIO(tasks)) if len(row)>1 and row[0].lower()=='deepseek harness.exe'}
            net=subprocess.check_output(['netstat.exe','-ano','-p','tcp'],encoding='utf-8',errors='replace')
            candidates=[]
            for line in net.splitlines():
                row=line.split()
                if len(row)==5 and row[-1] in pids and row[3]=='LISTENING' and row[1].startswith('127.0.0.1:'):candidates.append(row[1])
        else:raise ValueError('Enter the running Harness loopback address')
        self.home=home
        for address in dict.fromkeys(candidates):
            self.authority=address
            try:
                self.rpc('session/list',{'_request':{}},timeout=1)
                saved.write_text(json.dumps(dict(authority=address,home=str(home)),ensure_ascii=False),encoding='utf-8')
                return dict(connected=True,authority=address,home=str(home))
            except (OSError,ValueError,KeyError,RuntimeError):continue
        self.authority=None
        raise RuntimeError('No matching running Harness found; start Harness or enter its address and home')
    def read(self,p):
        job=self.jobs[p['task']]
        baseline=self.rpc('session/projections',{'request':{'sessionId':job['session_id']}})
        job['usage']=baseline.get('values',{}).get('tokenUsage',{})
        page=self.rpc('session/page',{'request':dict(address={'kind':'session','sessionId':job['session_id']},throughSeq=baseline['asOfSeq'],maxMessages=100)})
        events=[item['event'] for item in page['records'] if item.get('type')=='event']
        messages=[]
        for event in events:
            data=event.get('data',{})
            if isinstance(data.get('message'),dict):messages.append(data['message'])
        if job['status']=='running' and job['phase']=='coding':
            endings=[e for e in events if e.get('type')=='turn/end' and e.get('seq',-1)>job.get('after',-1)]
            if endings:job.update(native_finished=True,native_reason=endings[-1].get('data',{}).get('reason',{}).get('kind'),native_error=endings[-1].get('data',{}).get('reason',{}).get('error'))
        return dict(**job,messages=messages,events=events[-40:])
    def start(self,p):
        if not self.authority:raise ValueError('Connect Harness first')
        folder=self.studio.folder(p['id'])
        if any(j['workspace']==p['id'] and j['status']=='running' for j in self.jobs.values()):raise ValueError('This work copy already has a running Agent')
        seconds=p.get('timeout',180)
        if type(seconds) is not int or not 10<=seconds<=600:raise ValueError('Agent time limit must be 10–600 seconds')
        requirement=p.get('requirement','').strip()
        if not requirement or len(requirement)>16000:raise ValueError('Describe the requested change (maximum 16000 characters)')
        session=self.rpc('session/create',{'request':dict(cwd=str(folder),agentPreset='standard')})['sessionId']
        self.rpc('session/rename',{'request':dict(sessionId=session,title='组件制作 · '+folder.name)})
        prompt=(folder/'AGENTS.md').read_text(encoding='utf-8')+'\n\n用户需求：\n'+requirement
        if p.get('validation'):
            validation=self.studio.job({'job':p['validation']})
            if validation['workspace']!=p['id']:raise ValueError('Validation belongs to another work copy')
            prompt+='\n\n宿主验证日志（供你修正，不允许修改宿主检查）：\n'+validation['log'][-18000:]
        id=uuid4().hex
        job=dict(id=id,workspace=p['id'],session_id=session,status='running',phase='coding',deadline=time.time()+seconds,after=-1,repairs=0)
        self.jobs[id]=job
        self.rpc('session/prompt',{'request':dict(requestId='studio-'+id,sessionId=session,mode='queue',content=[dict(type='text',text=prompt)],clientTimeZone='Asia/Shanghai')})
        def watch():
            while not self.closed and job['status']=='running':
                if time.time()>=job['deadline']:
                    try:self.cancel(dict(task=id))
                    finally:job['status']='timeout'
                    return
                try:
                    current=self.read(dict(task=id))
                    if job.get('native_finished'):
                        if job['native_reason']!='completed':job.update(status='failed',phase='harness_error');return
                        job['phase']='validating'
                        check=self.studio.validate(dict(id=p['id'],timeout=min(30,max(1,int(job['deadline']-time.time())))))
                        job['validation']=check['id']
                        while check['status']=='running' and job['status']=='running' and time.time()<job['deadline']:
                            time.sleep(.3);check=self.studio.job(dict(job=check['id']))
                        if job['status']!='running':return
                        if time.time()>=job['deadline']:
                            self.cancel(dict(task=id));job['status']='timeout';return
                        if check['status']=='passed':job.update(status='completed',phase='verified');return
                        if job['repairs']>=2:job.update(status='failed',phase='validation_failed',validation_log=check['log']);return
                        job['repairs']+=1;job['after']=max((e.get('seq',-1) for e in current['events']),default=-1)
                        job.update(phase='coding',native_finished=False)
                        self.rpc('session/prompt',{'request':dict(requestId='studio-repair-'+uuid4().hex,sessionId=session,mode='queue',content=[dict(type='text',text='宿主验证失败，请修正工作副本，不修改宿主检查。\n'+check['log'][-18000:])],clientTimeZone='Asia/Shanghai')})
                except Exception as error:job['connection_error']=str(error)
                time.sleep(2)
        threading.Thread(target=watch,daemon=True).start()
        return job.copy()
    def cancel(self,p):
        job=self.jobs[p['task']]
        job['status']='cancelled'
        self.rpc('session/cancel',{'request':{'sessionId':job['session_id']}})
        if job.get('validation') and self.studio.job({'job':job['validation']})['status']=='running':self.studio.cancel({'job':job['validation']})
        return job.copy()
    def close(self):
        self.closed=True
        for id,job in self.jobs.items():
            if job['status']=='running':
                try:self.cancel(dict(task=id))
                except Exception:pass
