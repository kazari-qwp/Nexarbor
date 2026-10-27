"""最终应用的成员认领、固定候选、全体验收和自动归档。"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4
from app.runtime.requester import requester_id
from app.runtime.signal_work import current_work
from domain.core import Module,access
from . import protocol


def active(group):return [node for node in group['members'] if node not in group.get('unavailable',{})]

def append(group,actor,kind,content):
    entry=dict(id=str(uuid4()),run_id=group['run_id'],actor=actor,kind=kind,content=content,at=time.time());group['entries'].append(entry);return deepcopy(entry)


class CollaborationGroupModule(Module):
    def __init__(self,project_directory,emit,config=None,state=None,**access_settings):
        super().__init__('collaboration.group',**access_settings)
        self.directory=Path(project_directory).resolve();self.emit=emit;self.config=deepcopy(config or {});self.state=deepcopy(state or {});self._work=None

    def group(self,node):
        return self.state.setdefault('group',dict(group_id=node.info.node_id,phase='ready',members=[],claims={},entries=[],candidate=None,unavailable={},requests={},jobs={},runs={}))

    async def git(self,node,operation,p=None):return await node.modules.get('git.workspace').execute(operation,**(p or {}))

    @access(channels=['collaboration'])
    async def _members(self,node):
        if node.modules.get('collaboration.member') is not None:return node.info.node_id

    async def members(self):return [value for value in (await self._members()).values() if value is not None]

    @access(channels=['collaboration'])
    async def _notify(self,node,text,sender,target):
        member=node.modules.get('collaboration.member')
        if member is not None and node.info.node_id!=sender and (target is None or node.info.node_id==target):return await member.notify(text=text)

    async def announce(self,node,text,*,sender=None,wake=False,target=None):
        group=self.group(node)
        async def deliver():
            await self._notify(text,sender,target)
            if wake:
                receipt=self.emit(node,access_strength=self.strength,channels=['collaboration.work'],strength=self.strength,content={'run_id':group['run_id']},timeout_seconds=86400,node_timeout_seconds=86400)
                group['signal']=receipt['signal_id']
        work=current_work.get()
        if work is None and self._work and self._work[0]==group.get('run_id') and not self._work[1].closed:work=self._work[1]
        if work is None:await deliver()
        else:work.post(deliver,node.info.node_id+'/collaboration/notify')

    async def _status(self,node,p):
        g=self.group(node);section=p.get('section','all');result=dict(group_id=node.info.node_id,phase=g['phase'])
        fields={'summary':('task','members','unavailable','failure'),'claims':('claims',),'records':('entries',),'candidate':('candidate',)}
        if section=='all':result.update(deepcopy(g));result.update(workspace=g.get('workspace'),repository=await self.git(node,'repository'))
        else:result.update({key:deepcopy(g.get(key)) for key in fields[section]})
        if 'entries' in result:
            query=p.get('query');rows=g['entries'];result['entry_count']=len(rows)
            result['entries']=[r for r in rows if query.casefold() in r['content'].casefold() or query==r['id']] if query else deepcopy(rows[-20:])
        result['active_members']=active(g);return result

    async def execute(self,operation,**parameters):return next(iter((await self._operate(operation,parameters)).values()))
    async def control(self,**p):return await self.execute('control',**p)
    async def status(self,**p):return await self.execute('status',**p)
    async def context(self,**p):return await self.execute('context',**p)
    async def wait(self,**p):return await self.execute('wait',**p)
    async def member_exit(self,**p):return await self.execute('member_exit',**p)
    async def command_logs(self,**p):return await self.execute('command_logs',**p)
    async def claim(self,**p):return await self.execute('claim',**p)
    async def note(self,**p):return await self.execute('note',**p)
    async def send(self,**p):return await self.execute('send',**p)
    async def workspace(self,**p):return await self.execute('workspace',**p)
    async def finish(self,**p):return await self.execute('finish',**p)

    @access(channels=())
    async def _operate(self,node,op,p):
        g=self.group(node);actor=p.get('actor') or requester_id.get() or node.info.node_id
        work=current_work.get()
        if work is not None:self._work=(g.get('run_id'),work)
        if op=='control':
            action=p['action']
            if action=='status':return await self._status(node,p)
            if action=='stop':g.update(phase='stopped',failure='调用者请求停止');await self.announce(node,'协作已停止。');return await self._status(node,{})
            if g['phase'] in ('running','review'):raise ValueError('小组正在执行任务')
            ids=await self.members();prepared=await self.git(node,'prepare',{'members':ids})
            g.update(phase='running',started_at=time.time(),run_id=str(uuid4()),task=p['task'],members=ids,claims={},entries=[],candidate=None,unavailable={},failure=None,caller=actor,notified=False,workspace=prepared['directory'],personal_paths=prepared['members'])
            receipt=self.emit(node,access_strength=self.strength,channels=['collaboration.work'],strength=self.strength,content={'run_id':g['run_id']},timeout_seconds=86400,node_timeout_seconds=86400);g['signal']=receipt['signal_id']
            return dict(status='accepted',group_id=node.info.node_id,run_id=g['run_id'],members=ids)
        if op=='status':return await self._status(node,p)
        if op=='member_exit':
            g['unavailable'][actor]=p['reason']
            for c in g['claims'].values():
                if c['actor']==actor and c['state']=='active':c.update(state='released',evidence='成员退出：'+p['reason'])
            protocol.complete_candidate(g)
            if not active(g):g.update(phase='failed',failure='所有成员均已退出')
            await self.announce(node,'成员 '+actor+' 已退出，未完成认领已释放。请查看状态后继续。',sender=actor)
            return dict(retired=True,phase=g['phase'])
        if op=='wait':
            while g['phase'] in ('running','review'):await asyncio.sleep(.1)
            return await self._status(node,{})
        if op=='context':return dict(phase=g['phase'],candidate_pending=g.get('candidate') is not None and actor not in g['candidate']['approvals'],task=g.get('task'),run_id=g.get('run_id'),personal_path=g.get('personal_paths',{}).get(actor))
        if actor not in active(g):raise ValueError('仅本组有效成员可调用协作工具')
        if op=='command_logs':return await node.modules.get('execution.logs').query(**dict(p,actor=actor,since=g.get('started_at',0)))
        if op=='claim':return protocol.claim(g,dict(p,actor=actor),append)
        if op=='note':
            protocol.live(g)
            if p['kind'] not in ('OBSERVED','FACT','FAIL','PATCH_SUMMARY') or not p['content'].strip():raise ValueError('记录须有有效 kind 和正文')
            return append(g,actor,p['kind'],p['content'])
        if op=='send':
            protocol.live(g);target=p['target']
            if target==actor or target not in active(g):raise ValueError('只能向本组其他有效成员发信')
            await self.announce(node,json.dumps(dict(type='message',from_actor=actor,message_type=p.get('message_type','work_order'),content=p['content']),ensure_ascii=False),sender=actor,target=target)
            return dict(delivered=True,target=target)
        if op=='workspace':
            if p['action']!='inspect' and g['phase']!='running':raise ValueError('仅运行阶段允许修改共同成果')
            return await self.git(node,p['action'],dict(actor=actor,message=p.get('message','Publish contribution')))
        if op=='finish':
            arguments=dict(p,actor=actor);action=p['action']
            if action=='propose' and g['phase']=='running' and not g['candidate'] and not any(c['state']=='active' for c in g['claims'].values()):
                if not p.get('test_scripts') or not p.get('test_results'):raise ValueError('提出验收须同时提交测试脚本和真实测试结果')
                logs=await node.modules.get('execution.logs').collect(**dict(actor=actor,since=g['started_at'],**({'ids':p['log_ids']} if 'log_ids' in p else {})))
                arguments['review']=await self.git(node,'proposal',dict(actor=actor,test_scripts=p.get('test_scripts',[]),test_results=p.get('test_results',[]),logs=logs))
            result=protocol.finish(g,arguments,append)
            if result['phase']=='review' and action=='propose':await self.announce(node,'本组已提出成果候选：'+result['candidate']['id']+'。读取候选与验收材料，无异议批准，有异议指出证据。',sender=actor,wake=True)
            elif action=='reject':await self.announce(node,'成果候选被否决：'+p['evidence']+'。请继续修正。',sender=actor,wake=True)
            if g['phase']=='completed':
                home=self.directory/'workspace/cooperation-archives'/g['run_id'];home.mkdir(parents=True,exist_ok=True)
                (home/'result.md').write_text(g['candidate']['content'],encoding='utf8');(home/'run.json').write_text(json.dumps(g,ensure_ascii=False,indent=2),encoding='utf8');g['archive_path']=str(home)
                await self.announce(node,'共同成果已获本轮剩余成员验收，协作结束。请停止当前工作。')
            return dict(phase=g['phase'],candidate=deepcopy(g['candidate']),workspace=g['workspace'])
        raise ValueError('Unknown collaboration operation')
