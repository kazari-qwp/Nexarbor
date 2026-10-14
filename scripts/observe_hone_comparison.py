"""Read existing client logs only; compact three-arm progress."""
import collections,json,subprocess,os,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/hone-comparison-20261014-r1'
EXE=r'C:\Users\Dried Fish\AppData\Local\Programs\DeepSeek Harness\DeepSeek Harness.exe'
results={}
for arm in ['datanet','single','subagents']:
 b=BASE/arm;subprocess.run([EXE,str(b/'monitor.cjs')],env={**os.environ,'ELECTRON_RUN_AS_NODE':'1'},stdout=subprocess.DEVNULL,check=True)
 m=json.loads((b/'meta.json').read_text());r=json.loads((b/'client-records.json').read_text());usage=[e for e in r if e['type']=='assistant/message' and e['data'].get('usage')];tools=collections.Counter(e['data']['name'] for e in r if e['type']=='tool/call');done=next((json.loads((b/f).read_text()) for f in ['completion-stop.json','deadline-stop.json'] if (b/f).exists()),None)
 calls={(e['session'],e['data']['callId']):e['data']['name'] for e in r if e['type']=='tool/call'}
 errors=[{'tool':calls.get((e['session'],e['data']['message'].get('toolCallId'))),'text':str(e['data']['message']['content'])[:160]} for e in r if e['type']=='tool/result' and e['data']['message'].get('isError')]
 result=dict(elapsedSeconds=round(((done['at'] if done else time.time()*1000)-m['startedAt'])/1000),stopped=bool(done),modelResponses=len(usage),usage={key:sum(e['data']['usage'].get(key,0) for e in usage) for key in ['inputTokens','cacheReadTokens','outputTokens','totalTokens']},tools=dict(tools),fatalErrors=[str(e['data'])[:200] for e in r if e['type']=='agent/error'],toolErrors=errors)
 if arm=='datanet':
  subprocess.run([sys.executable,str(b/'state.py')],stdout=subprocess.DEVNULL,check=True);state=json.loads((b/'state.json').read_text());result['discussion']=state['discussion'];result['execution']=[{'phase':g['phase'],'candidate':g.get('candidate'),'failure':g['failure']} for g in state['cooperation']]
  actors={e['session']:e['data']['title'].split(' · ')[-1] for e in r if e['type']=='session/title'};texts=[]
  for e in r:
   if e['type']=='datanet/request-tail' and actors.get(e['session'],'').startswith('hone-plan/'):
    texts.extend(b.get('text','') for msg in e['data']['messages'] for b in msg.get('content',[]) if b['type']=='text')
  result['discussionTailMax']=max(map(len,texts),default=0)
 else:result['childSessions']=[{'id':e['session'],'depth':e.get('delegationDepth'),'origin':e.get('origin')} for e in r if e['type']=='session' and (e.get('delegationDepth') or e.get('origin')=='subagent')]
 results[arm]=result
(BASE/'progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for arm,d in results.items():print(arm,json.dumps({k:v for k,v in d.items() if k not in ['usage','tools','toolErrors','execution']},ensure_ascii=False));print('execution',[(g['phase'],bool(g['candidate']),g['failure']) for g in d.get('execution',[])])
