"""最终应用的按轮成员发言、记录员汇总和提交结束协议。"""
from copy import deepcopy
import json
from app.projects.module_tools import install_tools,bind_tools
from domain.core import Module,access

class GroupAccess:
    def __init__(self,module):
        self._access_origin=module._access_origin;self.channels=(module.config['channel'],);self.strength=module.strength;self.module_id=module.config['group_module']

    @access()
    async def call(self,node,operation,parameters):
        group=node.modules.get(self.module_id)
        if group is not None:return await group.execute(operation,**dict(parameters,actor=self._access_origin.info.node_id))


class DiscussionMemberModule(Module):
    signal_channels=('discussion.round',)
    def __init__(self,agent_run,config=None,state=None,**access_settings):
        super().__init__('discussion.member',**access_settings)
        self.agent_run=agent_run;self.config=deepcopy(config or {});self.state=deepcopy(state or {});self._specs=install_tools(self,__file__)

    def _bind(self,node):super()._bind(node);bind_tools(self,node,self._specs)

    async def call(self,operation,p=None):return next(value for value in (await GroupAccess(self).call(operation,p or {})).values() if value is not None)



    async def on_signal(self,context):return next(iter((await self._run({},dict(context.signal.content))).values()))
    async def run(self,**p):return next(iter((await self._run(p,None)).values()))

    @access(channels=())
    async def _run(self,node,p,signal):
        if self.state.get('running'):self.state['pending']=True;return dict(status='queued')
        self.state.update(running=True,pending=False)
        try:
            data=await self.call('context')
            if signal is not None:
                if signal['run_id']!=data['run_id'] or node.info.node_id in data['unavailable']:return dict(status='idle')
                final=signal.get('final',False)
                if final and self.config['role']!='recorder' or not final and node.info.node_id in data['submitted']:return dict(status='idle')
                if final:
                    others={n:t for n,t in data['submitted'].items() if n!=node.info.node_id}
                    message=f"本次运行：{data['run_id']}。讨论已结束，请根据本次任务、输出板草稿和历史上下文定稿。最后一轮其他成员发言：\n"+json.dumps(others,ensure_ascii=False,indent=2)+f"\n把最终成果写入 {data['output']}，用 write_output；然后回复完成情况。"
                else:
                    snapshot=await self.call('read_round');others={n:t for n,t in snapshot['previous_submitted'].items() if n!=node.info.node_id}
                    message=(f"项目任务：{data['task']}\n输出板ID：{data['output']}。" if data['round']==1 else '')
                    message+=f"\n本次运行：{data['run_id']}。\n上轮其他成员发言：\n"+json.dumps(others,ensure_ascii=False,indent=2)
                self.state['turn']=dict(final=final)
            else:self.state['turn']=dict(p);message=p['message']
            result=await self.agent_run(node.info.node_id,message)
            if result.get('status') not in ('completed','ok'):raise RuntimeError(result.get('error') or 'Member execution failed')
            if not self.state['turn'].get('final'):
                current=await self.call('context')
                if node.info.node_id not in current['submitted']:raise RuntimeError('本轮未提交或跳过')
            return result
        except Exception as error:
            if signal is not None:await self.call('member_exit',dict(reason=str(error)))
            raise
        finally:self.state['running']=False

    async def notify(self,**p):return next(iter((await self._notify(p['text'])).values()))

    @access(channels=())
    async def _notify(self,node,text):
        number=self.state.get('notification',0)+1;self.state['notification']=number
        node.update_inputs(self.module_id,inputs=[dict(id='message-'+str(number),text=text,delivery='steer')]);return dict(delivered=True)

    async def prepare(self,**p):
        data=await self.call('context');turn=self.state.get('turn',{});stage='讨论已结束；当前阶段：成果汇总。' if turn.get('final') else f"当前轮数：{data['round']}/{data['total']}。"
        tail=['[讨论状态：'+self._access_origin.info.node_id+']\n'+stage+'\n当前请求次数：{{request.count}}/{{request.limit}}。']
        if not turn.get('final'):tail.append('[公共笔记]\n'+data['notebook'])
        return dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=tail),sources=[],errors=[])

    async def read_round(self,**p):return await self.call('read_round',p)
    async def read_output(self,**p):return await self.call('read_output',p)
    async def write_notebook(self,**p):return await self.call('write_notebook',p)
    async def write_output(self,**p):return await self.call('write_output',p)
    async def submit_round(self,**p):return dict(format='nexarbor-tool-control/v1',conclude=True,data=await self.call('submit_round',p))
    async def skip_round(self,**p):return dict(format='nexarbor-tool-control/v1',conclude=True,data=await self.call('skip_round',p))
