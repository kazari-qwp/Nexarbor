"""按轮快照、并行成员与记录员定稿；沿用最终演示的讨论协议。"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
from app.runtime.requester import requester_id
from domain.core import Module,access


class DiscussionGroupModule(Module):
    def __init__(self,project_directory,transaction,emit,wait_signal,config=None,state=None,**access_settings):
        super().__init__('discussion.group',**access_settings)
        self.directory=Path(project_directory).resolve();self.transaction=transaction;self.emit=emit;self.wait_signal=wait_signal
        self.config=deepcopy(config or {});self.state=deepcopy(state or {})

    def group(self):
        return self.state.setdefault('group',dict(phase='ready',run_id=None,round=0,busy=False,submitted={},previous_submitted={},unavailable={},archives=[]))

    @access(channels=['discussion'])
    async def _members(self,node):
        module=node.modules.get('discussion.member')
        if module is not None:return dict(id=node.info.node_id,role=module.config['role'])

    async def members(self):return [value for value in (await self._members()).values() if value is not None]

    @access()
    async def _data(self,node,target,content):
        if node.info.node_id!=target:return None
        if node.node_type!='markdown':raise ValueError('讨论文档必须是Markdown数据节点')
        if content is None:return node.dataer.read()
        async with self.transaction([node.info.node_id]):node.dataer.write(content)
        return True

    async def text(self,field):
        result=await self._data(self.config[field],None)
        if self.config[field] not in result:raise ValueError('讨论文档不可达：'+self.config[field])
        return result[self.config[field]]

    async def write(self,field,content):
        result=await self._data(self.config[field],content)
        if self.config[field] not in result:raise ValueError('讨论文档不可达：'+self.config[field])

    def archive(self,name,content):
        path=self.directory/'workspace/discussions'/self.group()['run_id']/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf8');return str(path)

    async def board(self):
        raw=await self.text('board')
        return json.loads(raw) if raw.strip() else dict(round=0,submitted={},previous_submitted={})

    async def save_board(self):
        group=self.group();await self.write('board',json.dumps({key:group[key] for key in ('round','submitted','previous_submitted')},ensure_ascii=False,indent=2))

    async def pulse(self,node,final=False):
        group=self.group()
        receipt=self.emit(node,access_strength=self.strength,channels=['discussion.round'],strength=self.strength,kind='pulse',close_loop=True,sequence=group['round'],content=dict(run_id=group['run_id'],round=group['round'],final=final),timeout_seconds=86400,node_timeout_seconds=86400)
        group['signal']=receipt['signal_id'];report=await self.wait_signal(receipt['signal_id'])
        if not report['returned'] or report['status']!='completed':raise RuntimeError('Discussion pulse did not complete: '+str(report['status']))

    async def _discuss(self,node,p,actor):
        group=self.group()
        if group['phase']=='running':raise ValueError('Discussion is already running')
        if group['phase']=='completed' and not p.get('task'):
            return dict(status='ok',run_id=group['run_id'],output=await self.text('output'),archive_path=group.get('archive_path'))
        task=p.get('task') or group.get('task')
        if not task:raise ValueError('New discussion requires a task')
        if group['phase']=='completed':
            for field in ('notebook','output','board'):await self.write(field,'')
            group.update(run_id=None,round=0,busy=False,submitted={},previous_submitted={},unavailable={},archives=[])
        participants=await self.members();leader=next(item['id'] for item in participants if item['role']=='leader');recorder=next(item['id'] for item in participants if item['role']=='recorder')
        group.update(phase='running',task=task,run_id=group.get('run_id') or uuid4().hex,caller=actor,members=[item['id'] for item in participants],leader=leader,recorder=recorder)
        total=self.config.get('rounds',2)
        try:
            while group['round']<total or group.get('busy'):
                if not group.get('busy'):
                    group['previous_submitted']=dict((await self.board())['submitted']);group['submitted']={};group['round']+=1
                    await self.save_board();group['notebook_snapshot']=await self.text('notebook');group['busy']=True
                await self.pulse(node)
                if any(actor not in group['submitted'] for actor in (leader,recorder)):raise RuntimeError('Leader or Recorder did not submit this round')
                body='\n'.join(f"## 第{group['round']}轮 · {actor}\n{text}\n" for actor,text in group['submitted'].items())
                group['archives'].append(self.archive(f"round_{group['round']:03d}.md",body));group['busy']=False
            group.update(phase='finalizing',final_written=False);await self.pulse(node,final=True)
            if not group['final_written']:raise ValueError('FINAL_OUTPUT_NOT_CONFIRMED: Recorder 本次未保存非空最终成果')
            output=await self.text('output');group['archive_path']=self.archive('result.md',output);group['phase']='completed'
            return dict(status='ok',run_id=group['run_id'],output=output,archive_path=group['archive_path'],unavailable=deepcopy(group['unavailable']))
        except Exception as error:group.update(phase='interrupted',last_error=str(error));raise

    async def execute(self,operation,**parameters):return next(iter((await self._operate(operation,parameters)).values()))
    async def discuss(self,**p):return await self.execute('discuss',**p)
    async def status(self,**p):return await self.execute('status',**p)
    async def context(self,**p):return await self.execute('context',**p)
    async def read_round(self,**p):return await self.execute('read_round',**p)
    async def read_output(self,**p):return await self.execute('read_output',**p)
    async def write_output(self,**p):return await self.execute('write_output',**p)
    async def write_notebook(self,**p):return await self.execute('write_notebook',**p)
    async def submit_round(self,**p):return await self.execute('submit_round',**p)
    async def skip_round(self,**p):return await self.execute('skip_round',**p)
    async def member_exit(self,**p):return await self.execute('member_exit',**p)

    @access(channels=())
    async def _operate(self,node,name,p):
        group=self.group();actor=p.get('actor') or requester_id.get() or node.info.node_id
        if name=='discuss':return await self._discuss(node,p,actor)
        if name=='status':return {key:deepcopy(value) for key,value in group.items() if key not in ('submitted','previous_submitted','notebook_snapshot')}
        if name=='context':return dict(phase=group['phase'],round=group['round'],total=self.config.get('rounds',2),notebook=group.get('notebook_snapshot',''),previous_submitted=(await self.board())['previous_submitted'],submitted=deepcopy(group['submitted']),task=group.get('task'),run_id=group.get('run_id'),output=self.config['output'],unavailable=deepcopy(group['unavailable']))
        if name=='read_round':
            snapshot=await self.board();return dict(round=snapshot['round'],previous_submitted=snapshot['previous_submitted'])
        if name=='member_exit':
            if actor in (group.get('leader'),group.get('recorder')):raise RuntimeError(p['reason'])
            group['unavailable'][actor]=p['reason'];return dict(retired=True)
        if actor not in group.get('members',[]):raise ValueError('Only discussion members may write')
        if name in ('submit_round','skip_round'):
            if group['phase']!='running' or actor in group['submitted'] or actor in group['unavailable']:raise ValueError('not an active member or already submitted')
            content=p.get('reason','') if name=='skip_round' else p.get('content','')
            if name=='submit_round' and not content.strip():raise ValueError('empty submission')
            group['submitted'][actor]=('[跳过] ' if name=='skip_round' else '')+content;await self.save_board()
            return dict(submitted=True,round=group['round'],member=actor)
        if name=='read_output':return dict(content=await self.text('output'))
        if actor!=group.get('recorder'):raise ValueError('Only Recorder may maintain notes/output')
        if name=='write_notebook':
            if len(p['content'])>200:raise ValueError('公共笔记最多200字符，细节请写输出板')
            await self.write('notebook',p['content']);return dict(written=True)
        if name=='write_output':
            if not p['content'].strip():raise ValueError('输出正文不能为空')
            await self.write('output',p['content'])
            if group['phase']=='finalizing':group['final_written']=True
            return dict(written=True)
        raise ValueError('Unknown discussion operation')
