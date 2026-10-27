"""逐提交校验日志，再审计原有小镇业务不变量；不执行模块或模型。"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.persistence.state_journal import apply,checksum

def main():
    parser=argparse.ArgumentParser();parser.add_argument('runtime',type=Path);args=parser.parse_args();runtime=args.runtime.resolve()
    evidence=json.loads((runtime/'verification.json').read_text(encoding='utf-8'));assert evidence['passed'] and evidence['final_tick']==25
    initial=json.loads((runtime/'initial-state.json').read_text(encoding='utf-8'));originals={n['node_id'] for n in initial['network']['nodes'] if n['type']=='agent'}
    sources=[Path(evidence['resume']['directory']),runtime];states={};provenance={}
    for source in sources:
        db=sqlite3.connect((source/'checkpoints.sqlite3').as_uri()+'?mode=ro',uri=True)
        try:
            first=db.execute('SELECT id,document,state_hash FROM checkpoints ORDER BY id LIMIT 1').fetchone();state=json.loads(first[1]);digest=checksum(state);assert digest==first[2];last=first[0]
            def capture(seq):
                pulse_node=next((n for n in state['network']['nodes'] if n['type']=='pulse'),None)
                if pulse_node is None:return
                pulse=pulse_node['parameters']['state']
                tick=pulse.get('sequence',0)
                if 1<=tick<=25 and pulse.get('phase')=='completed' and not pulse.get('active_signal'):
                    signal=state['signals'].get(pulse['last_signal'])
                    if signal and signal['status']=='completed' and signal['signal']['sequence']==tick:
                        states[tick]=deepcopy(state);provenance[tick]={'directory':str(source),'commit':seq,'hash':digest}
            capture(last)
            for seq,parent,expected,delta in db.execute('SELECT id,parent_hash,state_hash,delta FROM commits WHERE id>? ORDER BY id',(last,)):
                assert seq==last+1 and parent==digest;state=apply(state,json.loads(delta));digest=checksum(state);assert digest==expected;last=seq;capture(seq)
        finally:db.close()
    assert sorted(states)==list(range(1,26))
    checks=[];ticks=[]
    def check(name,ok):checks.append({'name':name,'passed':bool(ok)})
    def modules(node):return {m['module_id']:m for m in node['tables']['modules']}
    def locations(node):return [e['target_id'] for e in node['links'] if e.get('attributes',{}).get('relation')=='location']
    out=runtime/'audited-ticks';out.mkdir(exist_ok=True)
    for tick,state in sorted(states.items()):
        nodes=state['network']['nodes'];actors={n['node_id']:n for n in nodes if n['type']=='agent'};byid={n['node_id']:n for n in nodes}
        pulse=next(n for n in nodes if n['type']=='pulse')['parameters']['state'];wave=state['signals'][pulse['last_signal']]
        check(f'{tick}:complete pulse',wave['status']=='completed' and wave['returned']);check(f'{tick}:residents',originals<=set(actors))
        clock=next(modules(n)['world.time'] for n in nodes if 'world.time' in modules(n));check(f'{tick}:clock',clock['state']['tick']==tick)
        deliveries={d['node_id']:d for d in wave['deliveries']}
        for actor,node in actors.items():
            mounts=modules(node)
            if actor in originals:check(f'{tick}:{actor}:processed',deliveries.get(actor,{}).get('status')=='processed')
            if actor in deliveries:
                current=[a for a in mounts['agents.activity']['state']['activities'] if a['key']==pulse['last_signal']]
                check(f'{tick}:{actor}:once',len(current)==1 and current[0]['status']=='completed' and current[0]['completed_count']==1)
            values=mounts['records.store']['state'].get('values',mounts['records.store']['config'].get('initial',{}))
            for key in ('ap','coins'):check(f'{tick}:{actor}:{key}',type(values.get(key,0)) in (int,float) and values.get(key,0)>=0)
            place=mounts['place.info'];location=place['state'].get('location',place['config'].get('location'))
            check(f'{tick}:{actor}:location',location in byid and locations(node)==[location] and [n['node_id'] for n in nodes if actor in locations(n)]==[location])
        checkpoint=next(modules(n)['runtime.periodic_checkpoint'] for n in nodes if 'runtime.periodic_checkpoint' in modules(n))['state']
        check(f'{tick}:periodic checkpoint',checkpoint['count']==tick and checkpoint.get('pending',False) is False)
        ticks.append({'tick':tick,'residents':len(actors),'source':provenance[tick]});(out/(str(tick).zfill(3)+'.json')).write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
    check('same-session cold reopen',evidence['reopened'] and evidence['same_sessions'])
    report={'passed':all(c['passed'] for c in checks),'model_calls':0,'checked_ticks':25,'checks':checks,'failures':[c for c in checks if not c['passed']],'ticks':ticks}
    (runtime/'independent-town-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'checks':len(checks),'failures':len(report['failures']),'ticks':25},ensure_ascii=False))
    if report['failures']:print(json.dumps(report['failures'][:12],ensure_ascii=False));return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
