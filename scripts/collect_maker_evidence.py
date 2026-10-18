"""汇总新增会话事件，按session+seq去重；不读取账户授权或推算人民币账单。"""
import json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
folders=[ROOT/'build'/n for n in ['applications-v8','network-maker-apps','makers-wish-lab','shop-wish-lab']]
folders.extend((ROOT/'build').glob('maker-paid-*'))
jobs={};events={};groups=[]
for folder in folders:
    collected=[]
    for file in (folder/'studio/maker-evidence').glob('*.json'):
        j=json.loads(file.read_text(encoding='utf-8'));jobs[j['id']]=j;collected.append(j)
        for e in j.get('usage_events',[]):events[(j['session_id'],e['seq'])]=e['usage']
    if collected:groups.append(dict(directory=folder.name,jobs=len(collected),statuses=dict(Counter(j['status'] for j in collected)),recorded_steps=sum(j.get('requests',0) or 0 for j in collected)))
usage=Counter()
for event in events.values():usage.update({k:v for k,v in event.items() if isinstance(v,(int,float))})
report=dict(scope='制作器事件用量；不含NPC/讨论/知识应用真实运行。早期未记录的Token不能据此补算。',steps_note='步骤数包含被上限拒绝等失败步骤，不能把它直接当账单请求数。',groups=groups,jobs=len(jobs),recorded_steps=sum(j.get('requests',0) or 0 for j in jobs.values()),recorded_usage_events=len(events),usage=dict(usage),cache_note='当前SDK的inputTokens是未命中部分，cacheReadTokens单列；分叉仅统计种子之后的事件。',forks=[dict(task=j['id'],session=j['session_id'],source=j.get('source_session'),workspace=j['workspace'],recorded_steps=j.get('requests')) for j in jobs.values() if j.get('source_session')],jobs_summary=[{k:j.get(k) for k in ['id','workspace','kind','status','session_id','source_session','requests','validation_attempts','environment_attempts','repairs','children']} for j in jobs.values()])
file=ROOT/'docs/reports/MAKER_USAGE.json';file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:report[k] for k in ['jobs','recorded_steps','recorded_usage_events','usage']},ensure_ascii=False))
