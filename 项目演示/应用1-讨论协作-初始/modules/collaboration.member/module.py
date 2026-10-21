"""Per-member native execution and compact context, with explicit turn conclusion."""
from datanet.core.module_protocol import ComponentResult

async def target(ctx):
    name=ctx.config['group_module'];channel=ctx.config['channel']
    return next(n for n in await ctx.network.nodes(channels=[channel]) if name in n.modules)

async def call(ctx,operation,parameters=None):
    node=await target(ctx);p=dict(parameters or {});p['actor']=ctx.node_id
    r=await node.call(ctx.config['group_module'],operation,p)
    if r['status']!='ok':raise ValueError(r.get('error') or '小组操作失败')
    return r['data']

def conclude(data):return dict(format='nexarbor-tool-control/v1',conclude=True,data=data)

def packet(tail):
    return dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=tail),sources=[],errors=[])

async def execute(ctx,activation):
    op,p=activation.operation,activation.parameters
    try:
        if activation.kind=='signal' or op=='run':
            if ctx.state.get('running'):
                ctx.state['pending']=True;return ComponentResult(data=dict(status='queued'))
            ctx.state.update(running=True,pending=False)
            try:
                data=await call(ctx,'context')
                if data['phase'] not in ('running','review') or data['phase']=='review' and not data['candidate_pending']:return ComponentResult(data=dict(status='idle'))
                run_id=data['run_id']
                message=(f"共同目标：{data['task']}\n本次运行：{run_id}。\n你的工作目录：{data['personal_path']}\n成员平等，自主认领并推进；共同成果通过 datanet_team_finish 验收收尾。" if ctx.state.get('run_id')!=run_id else '请依据当前协作状态和新消息继续推进；有待验收候选时先阅读材料。')
                ctx.state['run_id']=run_id
                while True:
                    result=await ctx.network.invoke(ctx.node_id,'runtime:agent_run',dict(message=message),channels=['runtime.agent'])
                    if result.get('status') not in ('completed','ok'):raise RuntimeError(result.get('error') or '成员执行失败')
                    current=await call(ctx,'context')
                    if current['run_id']!=run_id or current['phase'] not in ('running','review') or current['phase']=='review' and not current['candidate_pending']:break
                    message='共同目标尚未收尾。依据当前协作状态继续推进；已有候选时阅读验收材料，有异议指出具体问题，无异议提交批准。'
                return ComponentResult(data=result)
            finally:ctx.state['running']=False
        if op=='notify':
            number=ctx.state.get('notification',0)+1;ctx.state['notification']=number
            ctx.update_inputs({'inputs':[dict(id='message-'+str(number),text=p['text'],delivery='steer')]})
            return ComponentResult(data=dict(delivered=True))
        if op=='prepare':
            data=await call(ctx,'context')
            names={'ready':'待开始','running':'执行','review':'审核','completed':'完成','stopped':'停止','failed':'失败','interrupted':'中断'}
            text='[协作组]\n阶段：'+names.get(data['phase'],data['phase'])+'。'
            if data['candidate_pending']:text+='\n目前有成果等待审核。'
            tail=[text]
            return ComponentResult(data=packet(tail))
        mapping={'datanet_team_status':'status','datanet_team_claim':'claim','datanet_team_note':'note','datanet_team_send':'send','datanet_team_workspace':'workspace','datanet_team_finish':'finish','datanet_command_logs':'command_logs'}
        data=await call(ctx,mapping[op],p)
        if op=='datanet_team_finish' and data['phase'] in ('review','completed') and p['action'] in ('propose','approve'):data=conclude(data)
        return ComponentResult(data=data)
    except Exception as error:
        if activation.kind=='signal' or op=='run':await call(ctx,'member_exit',dict(reason=str(error)))
        return ComponentResult(status='error',error=str(error))
