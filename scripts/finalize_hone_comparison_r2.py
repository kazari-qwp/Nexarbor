"""Grade frozen saved artifacts; no model calls or artifact repairs."""
import hashlib,json,os,shutil,subprocess,sys,re,importlib.util,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'build/hone-comparison-20261014-r2'
PY=sys.executable
results={}
for arm in ['datanet','free','single','subagents']:
 b=BASE/arm;m=json.loads((b/'meta.json').read_text(encoding='utf-8-sig'));marker=next((b/f for f in ['completion-stop.json','deadline-stop.json'] if (b/f).exists()),None)
 if not marker:continue
 out=b/'comparison-result.json'
 if out.exists():results[arm]=json.loads(out.read_text(encoding='utf-8-sig'));continue
 r=json.loads((b/'client-records.json').read_text(encoding='utf-8-sig'));end=json.loads(marker.read_text(encoding='utf-8-sig'))['at'];timed=marker.name=='deadline-stop.json'
 if arm=='datanet':
  import sqlite3
  db=sqlite3.connect('file:'+str(Path(m['workspace'])/'.datanet/networks'/m['sessionId'].encode().hex()/'checkpoints.sqlite3').replace('\\','/')+'?mode=ro',uri=True);state=json.loads(db.execute('select document from checkpoints order by id desc limit 1').fetchone()[0]);db.close();g=state.get('cooperative_groups',{}).get('hone-exec');source=Path(g['workspace_directory'])/'main' if g else Path(m['workspace'])/'missing-execution';phase=g.get('phase') if g else 'not-started'
 else:source=Path(m['workspace'])/'project';phase='deadline' if timed else 'idle'
 dest=b/'evaluation/frozen';dest.mkdir(parents=True,exist_ok=False)
 head=None;dirty=None
 if (source/'.git').exists():
  try:
   head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
   import tarfile
   archive=b/'evaluation/candidate.tar';subprocess.run(['git','-C',str(source),'archive','--output',str(archive),head],check=True)
   with tarfile.open(archive) as tar:
    for item in tar:
     f=dest/item.name
     if not f.resolve().is_relative_to(dest.resolve()):raise ValueError('Unsafe archive member')
     if item.isdir():f.mkdir(parents=True,exist_ok=True)
     elif item.isfile():
      f.parent.mkdir(parents=True,exist_ok=True)
      with tar.extractfile(item) as inp,f.open('wb') as op:shutil.copyfileobj(inp,op)
  except subprocess.CalledProcessError:head=None
 if not head and source.exists():shutil.copytree(source,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','__pycache__','.venv','node_modules'))
 def load(name):
  spec=importlib.util.spec_from_file_location(arm+'_'+name,b/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 judge=load('judge');judge.REFERENCE=Path((b/'grader-path.txt').read_text(encoding='utf-8-sig'))/'reference';unit=judge.score(dest,'candidate')
 try:cli=load('cli_judge').score(dest)
 except Exception as error:cli={'passed':0,'total':6,'error':str(error)}
 u=[e for e in r if e['type']=='assistant/message' and e['data'].get('usage')];usage={k:sum(e['data']['usage'].get(k,0) for e in u) for k in ['inputTokens','cacheReadTokens','outputTokens','totalTokens']}
 tool_calls=[e for e in r if e['type']=='tool/call'];ref=[]
 for e in tool_calls:
  args=e['data']['arguments'];text=args if isinstance(args,str) else json.dumps(args)
  if e['data']['name'] in ['web_fetch','web_search','read','pwsh'] and ('chamkank/hone' in text or 'hone.hone Hone get_valid_splits' in text):ref.append({'tool':e['data']['name'],'arguments':text})
 root_messages=[e for e in r if e['session']==m['sessionId'] and e['type']=='assistant/message'];final=next(('\n'.join(x.get('text','') for x in e['data']['message']['content'] if x['type']=='text') for e in reversed(root_messages) if any(x['type']=='text' and x.get('text','').strip() for x in e['data']['message']['content'])),'');(b/'root-final.txt').write_text(final,encoding='utf-8')
 final_end=next((e for e in reversed(r) if e['session']==m['sessionId'] and e['type']=='turn/end'),None);elapsed=(final_end['time']-m['startedAt'])/1000 if not timed and final_end else (end-m['startedAt'])/1000
 inputs=[]
 for name,h in json.loads((b/'input-baseline.json').read_text(encoding='utf-8-sig')).items():
  f=Path(m['workspace'])/'task'/name
  if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=h:inputs.append(name)
 passed=sum(s['passed'] for s in unit['suites']);total=sum(s['total'] for s in unit['suites']);children=[{'sessionId':e['session'],'depth':e.get('delegationDepth')} for e in r if e['type']=='session' and e.get('origin')=='subagent'];contexts=[e['data'] for e in r if e['type']=='request/context']
 result=dict(permission=json.loads((b/'permission-change.json').read_text(encoding='utf-8')),arm=arm,phase=phase,timedOut=timed,elapsedSeconds=elapsed,source=str(source),frozen=str(dest),commit=head,dirtyStatus=dirty,modelResponses=len(u),tokenUsage=usage,inputCacheHitRate=usage['cacheReadTokens']/(usage['cacheReadTokens']+usage['inputTokens']) if usage['cacheReadTokens']+usage['inputTokens'] else 0,externalPassed=passed,externalTotal=total,cli=cli,external=unit,publicInputChanges=inputs,referenceAccess=ref,independentImplementationValid=not ref and not inputs,children=children,contextWindows=sorted(set(e.get('contextWindow') for e in contexts)),rootFinal=final,tools=dict(collections.Counter(e['data']['name'] for e in tool_calls)),hasReadme=(dest/'README.md').exists(),testFiles=[str(f.relative_to(dest)) for f in dest.rglob('test*.py')])
 out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');results[arm]=result
 summary={k:result[k] for k in ['arm','phase','timedOut','elapsedSeconds','modelResponses','externalPassed','externalTotal','independentImplementationValid']};summary['cliPassed']=cli['passed'];print(json.dumps(summary,ensure_ascii=False))
(BASE/'comparison-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
