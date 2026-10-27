"""最终演示的真实终端日志查询与快照引用；不评分或生成测试证据。"""
from copy import deepcopy
import json
from pathlib import Path
from domain.core import Module,access

class ExecutionLogsModule(Module):
    def __init__(self,directory,config=None,state=None,**access_settings):
        super().__init__('execution.logs',**access_settings)
        self.directory=Path(directory).resolve();self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    def records(self,p):
        rows=[]
        for file in (self.directory/'.nexarbor/command-logs').glob('*.json'):
            row=json.loads(file.read_text('utf8'))
            if row['actor']!=p['actor'] or row['started_at']<p.get('since',0):continue
            if p.get('ids') is not None and row['id'] not in p['ids']:continue
            rows.append(dict(id=row['id'],actor=row['actor'],started_at=row['started_at'],finished_at=row['finished_at'],path=str(file)))
        return sorted(rows,key=lambda r:r['started_at'])

    async def query(self,**parameters):return next(iter((await self._operate('query',parameters)).values()))
    async def collect(self,**parameters):return next(iter((await self._operate('collect',parameters)).values()))

    @access(channels=())
    async def _operate(self,node,op,p):
        rows=self.records(p)
        if op=='collect':return rows
        if p['action']=='list':return dict(total=len(rows),logs=rows[-20:])
        row=next((r for r in rows if r['id']==p.get('log_id')),None)
        if row is None:raise ValueError('Unknown command log')
        lines=json.dumps(json.loads(Path(row['path']).read_text('utf8')),ensure_ascii=False,indent=2).splitlines()
        offset=p.get('offset',0);limit=min(p.get('limit',120),300)
        return dict(id=row['id'],total_lines=len(lines),offset=offset,lines=lines[offset:offset+limit])
