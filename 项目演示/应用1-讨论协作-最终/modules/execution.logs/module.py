"""Query recorded terminal evidence; no result grading or generated evidence."""
import json,os
from pathlib import Path
from datanet.core.module_protocol import ComponentResult

def records(p):
    home=Path(os.environ['DATANET_PROJECT_DIRECTORY'])/'.nexarbor/command-logs'
    rows=[]
    for file in home.glob('*.json'):
        row=json.loads(file.read_text('utf8'))
        if row['actor']!=p['actor'] or row['started_at']<p.get('since',0):continue
        if p.get('ids') is not None and row['id'] not in p['ids']:continue
        rows.append(dict(id=row['id'],actor=row['actor'],started_at=row['started_at'],finished_at=row['finished_at'],path=str(file)))
    return sorted(rows,key=lambda r:r['started_at'])

async def execute(ctx,activation):
    p=activation.parameters
    try:
        rows=records(p)
        if activation.operation=='collect':return ComponentResult(data=rows)
        if p['action']=='list':return ComponentResult(data=dict(total=len(rows),logs=rows[-20:]))
        row=next((r for r in rows if r['id']==p.get('log_id')),None)
        if row is None:raise ValueError('Unknown command log')
        lines=Path(row['path']).read_text('utf8').splitlines()
        # Pretty-print the full original command/result in pages, including any spill references.
        lines=json.dumps(json.loads('\n'.join(lines)),ensure_ascii=False,indent=2).splitlines()
        offset=p.get('offset',0);limit=min(p.get('limit',120),300)
        return ComponentResult(data=dict(id=row['id'],total_lines=len(lines),offset=offset,lines=lines[offset:offset+limit]))
    except Exception as error:return ComponentResult(status='error',error=str(error))
