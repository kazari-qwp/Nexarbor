"""最终应用的原生成员循环和明确回合结束协议。"""
from copy import deepcopy
from app.projects.module_tools import install_tools,bind_tools
from domain.core import Module,access

class GroupAccess:
    def __init__(self,module):
        self._access_origin=module._access_origin;self.channels=(module.config['channel'],);self.strength=module.strength;self.module_id=module.config['group_module']

    @access()
    async def call(self,node,operation,parameters):
        group=node.modules.get(self.module_id)
        if group is not None:return await group.execute(operation,**dict(parameters,actor=self._access_origin.info.node_id))


class CollaborationMemberModule(Module):
    signal_channels=('collaboration.work',)
    def __init__(self,agent_run,config=None,state=None,**access_settings):
        super().__init__('collaboration.member',**access_settings)
        self.agent_run=agent_run;self.config=deepcopy(config or {});self.state=deepcopy(state or {});self._specs=install_tools(self,__file__)

    def _bind(self,node):super()._bind(node);bind_tools(self,node,self._specs)

    async def call(self,operation,p=None):
        return next(value for value in (await GroupAccess(self).call(operation,p or {})).values() if value is not None)



    async def on_signal(self,context):return await self.run()
    async def run(self,**parameters):return next(iter((await self._run()).values()))

    @access(channels=())
    async def _run(self,node):
        if self.state.get('running'):self.state['pending']=True;return dict(status='queued')
        self.state.update(running=True,pending=False)
        try:
            data=await self.call('context')
            if data['phase'] not in ('running','review') or data['phase']=='review' and not data['candidate_pending']:return dict(status='idle')
            run_id=data['run_id']
            message=(f"共同目标：{data['task']}\n本次运行：{run_id}。\n你的工作目录：{data['personal_path']}\n成员平等，自主认领并推进；共同成果通过 datanet_team_finish 验收收尾。" if self.state.get('run_id')!=run_id else '请依据当前协作状态和新消息继续推进；有待验收候选时先阅读材料。')
            self.state['run_id']=run_id
            while True:
                result=await self.agent_run(node.info.node_id,message)
                if result.get('status') not in ('completed','ok'):raise RuntimeError(result.get('error') or '成员执行失败')
                current=await self.call('context')
                if current['run_id']!=run_id or current['phase'] not in ('running','review') or current['phase']=='review' and not current['candidate_pending']:break
                message='共同目标尚未收尾。依据当前协作状态继续推进；已有候选时阅读验收材料，有异议指出具体问题，无异议提交批准。'
            return result
        except Exception as error:
            await self.call('member_exit',dict(reason=str(error)));raise
        finally:self.state['running']=False

    async def notify(self,**p):return next(iter((await self._notify(p['text'])).values()))

    @access(channels=())
    async def _notify(self,node,text):
        number=self.state.get('notification',0)+1;self.state['notification']=number
        node.update_inputs(self.module_id,inputs=[dict(id='message-'+str(number),text=text,delivery='steer')]);return dict(delivered=True)

    async def prepare(self,**p):
        data=await self.call('context');names={'ready':'待开始','running':'执行','review':'审核','completed':'完成','stopped':'停止','failed':'失败','interrupted':'中断'}
        text='[协作组]\n阶段：'+names.get(data['phase'],data['phase'])+'。'
        if data['candidate_pending']:text+='\n目前有成果等待审核。'
        return dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=[text]),sources=[],errors=[])

    async def datanet_team_status(self,**p):return await self.call('status',p)
    async def datanet_team_claim(self,**p):return await self.call('claim',p)
    async def datanet_team_note(self,**p):return await self.call('note',p)
    async def datanet_team_send(self,**p):return await self.call('send',p)
    async def datanet_team_workspace(self,**p):return await self.call('workspace',p)
    async def datanet_command_logs(self,**p):return await self.call('command_logs',p)
    async def datanet_team_finish(self,**p):
        data=await self.call('finish',p)
        return dict(format='nexarbor-tool-control/v1',conclude=True,data=data) if data['phase'] in ('review','completed') and p['action'] in ('propose','approve') else data
