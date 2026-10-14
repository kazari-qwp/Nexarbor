from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datanet.core.application import Component


class Plugin(Component):
    def install(self):
        self.busy, self.lock, self.turns = set(), Lock(), {}
        self.on('network/before-create', self.before_create)
        self.on('network/created', self.created)
        self.on('agent/bound', self.bound)
        self.on('agent/request', self.request)
        self.on('agent/pre-step', self.budget)
        self.on('agent/turn-stopping', self.stopping)
        self.on('tool/after', self.written)
        self.on('discussion/member-start', self.member_start)
        self.tail_bound = False

    def tail(self, e):
        turn = self.turns.get(e['actor'], {})
        if turn.get('active'):
            stage = '讨论已结束；当前阶段：成果汇总。' if turn.get('final') else f"当前轮数：{turn['round']}/{turn['total']}。"
            e['texts'].append('[讨论状态：' + e['actor'] + ']\n' + stage + f"\n当前请求次数：{turn['count']}/10。")
        if turn.get('active') and not turn.get('final'):
            for text in turn.get('resident_snapshot', []):
                label = text.split('\n', 1)[0]
                e['texts'][:] = [text if item.split('\n', 1)[0] == label else item for item in e['texts']]

    def before_create(self, e):
        if e['arguments']['preset'] == 'discussion_group' and e['arguments'].get('with_agents') is not False:
            if self.r.state(e['actor'])['grant']['framework'].get('datanet_create_network', {}).get('scope') != 'descendants':
                raise PermissionError('This preset needs network creation permission with descendants scope')

    def created(self, e):
        if e['arguments']['preset'] == 'discussion_group' and e['arguments'].get('with_agents') is not False:
            self.make_members(e['actor'], e['result'])
            info = self.r.rpc('group_info', group_id=e['result']['group_id'])
            e['result'].update(members=info['members'], leader_id=info['members'][0], recorder_id=info['recorder_id'])

    def make_members(self, parent, group):
        management = self.r.plugins['tools/network_management']
        for actor in group['members']:
            if actor in self.r.states:
                continue
            if not self.r.rpc('check_management', actor=parent, target=actor, scope=self.r.state(parent)['grant']['framework'].get('datanet_create_network', {}).get('scope', 'self'))['allowed']:
                raise PermissionError('Discussion member is outside network creation grant')
            role = 'leader' if actor == group['leader_id'] else 'recorder' if actor == group['recorder_id'] else 'member'
            preset = self.r.presets[role]
            prompt = self.r.resource(preset['owner'], preset['prompt'])
            result = management.create(actor, prompt, parent, self.r.config.get('discussionMaxSignalStrength', 2), self.r.config.get('discussionToolboxes', ['network_access', 'discussion_member']), role)
            self.r.rpc('agent_progress', target=result['node_id'], kind='discussion', group_id=group['group_id'], count=0)
            if result['node_id'] != actor:
                group['members'] = [result['node_id'] if id == actor else id for id in group['members']]
                structure = group['structure']
                for row in structure['nodes']:
                    if row['node_id'] == actor:
                        row['node_id'] = result['node_id']
                for edge in structure['interfaces'] + structure['attachment_interfaces']:
                    for field in ('source_node_id', 'target_node_id'):
                        if edge[field] == actor:
                            edge[field] = result['node_id']

    def bound(self, e):
        if not self.tail_bound:
            self.on('context/tail', self.tail)
            self.tail_bound = True
        actor = e['actor']
        if self.r.backend.agents[actor].get('kind') == 'discussion':
            self.turns[actor] = dict(count=self.r.backend.agents[actor].get('count', 0), active=False, submitted=False, final=False, output_written=False, round=0, total=0)
            self.section(actor, 'datanet:discussion-budget', lambda: '所属节点：' + actor, 90.1)

    def request(self, e):
        turn = self.turns.get(e['actor'])
        if turn and turn['active']:
            if turn['count'] >= 10:
                raise RuntimeError('discussion request budget exhausted')
            turn['count'] += 1
            self.r.rpc('agent_progress', target=e['actor'], count=turn['count'], activity='running')

    def member_start(self, e):
        self.r.load(e['actor'], 'preset:discussion_group:member', self.r.resource(self.id, 'members/AGENTS.md'))

    def budget(self, e):
        turn = self.turns.get(e['actor'])
        if turn and turn['active']:
            self.member_start(e)
        if turn and turn['active'] and turn['count'] >= 10:
            raise RuntimeError('discussion request budget exhausted')

    def stopping(self, e):
        turn = self.turns.get(e['actor'])
        problem = self.r.plugins.get('toolboxes/problem_handling')
        if turn and turn['active'] and not turn['submitted'] and not turn['final'] and turn['count'] < 10 and not (problem and problem.latest(e['actor']) and self.r.backend.agents[e['actor']].get('activity') == 'blocked'):
            self.r.host('steer', actor=e['actor'], text='本轮未完成，请调用 submit_round 或 skip_round。')

    def written(self, e):
        turn = self.turns.get(e['actor'])
        p = e['arguments']
        if turn and turn['final'] and e['name'] == 'node_write' and p.get('target') == turn.get('expected_output') and p.get('key') == 'content' and p.get('mode') != 'append' and isinstance(p.get('value'), str) and p['value'].strip():
            turn['output_written'] = True
            reports = self.r.plugins.get('tools/reports')
            if reports:
                reports.artifact(e['actor'], p['value'])

    def tool_read_round(self, actor, p):
        return self.r.rpc('read_round', actor=actor, group_id=self.r.backend.agents[actor]['group_id'], strength=self.r.state(actor)['strength'])

    def submit(self, actor, p, skip):
        turn = self.turns.get(actor)
        if not turn or not turn['active'] or turn['final']:
            raise ValueError('No active discussion submission')
        content = p.get('reason', '') if skip else p['content']
        group = self.r.backend.agents[actor]['group_id']
        result = self.r.rpc('submit', actor=actor, group_id=group, content=content, skip=skip)
        turn['submitted'] = True
        reports = self.r.plugins.get('tools/reports')
        if reports:
            reports.artifact(actor, dict(group_id=group, content=content, skip=skip), submission=True)
        self.r.host('conclude')
        return result

    def tool_submit_round(self, actor, p):
        return self.submit(actor, p, False)

    def tool_skip_round(self, actor, p):
        return self.submit(actor, p, True)

    def schedule(self, caller, actor, text, reference, info, round=None, final=False):
        turn = self.turns[actor]
        # A restarted in-progress round retains the saved request budget.
        saved = self.r.backend.agents[actor]
        resume = saved.get('activity') == 'interrupted' and info['busy']
        turn.update(count=saved.get('count', 0) if resume else 0, active=True, submitted=False, final=final, round=round, total=info['total'], output_written=False, expected_output=info['output_id'])
        self.r.emit('discussion/member-start', actor=actor, group_id=saved['group_id'], project_ids=info['project_ids'])
        try:
            result = self.r.plugins['tools/network_management'].execute(caller, actor, text, kind='archive' if final else 'discussion_member', parent=reference, round=round)
            if result['status'] == 'blocked':
                raise RuntimeError('AGENT_BLOCKED: ' + actor + ' ' + result['feedback']['error'])
            if not final and not turn['submitted']:
                raise RuntimeError(actor + ' did not submit within budget')
        finally:
            turn['active'] = False

    def notify_loss(self, group_id, caller):
        info = self.r.rpc('group_info', group_id=group_id)
        ordinary = [m for m in info['members'] if m not in (info['leader_id'], info['recorder_id'])]
        lost = info['unavailable']
        if not ordinary or len(lost) * 2 < len(ordinary) or info['loss_notice_sent']:
            return
        self.r.rpc('discussion_loss_notice', group_id=group_id, sent=True)
        manager = self.r.backend.agents[info['leader_id']].get('manager_id') or info.get('owner') or caller
        notice = dict(type='discussion_degraded', group_id=group_id, run_id=info['run_id'],
                      exited_count=len(lost), total_ordinary_members=len(ordinary), unavailable=lost,
                      active_members=info['active_members'], continuing=True,
                      message='本轮至少一半普通成员已退出；Leader、Recorder和剩余成员继续讨论。')
        try:
            self.r.emit('agent/ensure-mounted', target=manager)
            self.r.host('steer', actor=manager, text=json.dumps(notice, ensure_ascii=False))
        except Exception as error:
            self.r.rpc('discussion_loss_notice', group_id=group_id, sent=False)
            self.r.errors.append(dict(component=self.id, error=str(error)))

    def tool_datanet_discuss(self, actor, p):
        group_id = p['group_id']
        if not self.r.rpc('check_access', actor=actor, target=group_id + '/board', direction='write', strength=self.r.state(actor)['strength'])['allowed']:
            raise PermissionError('Target is outside permitted network path')
        self.r.load(actor, 'preset:discussion_group', self.r.resource(self.id, 'AGENTS.md'))
        with self.lock:
            if group_id in self.busy:
                raise RuntimeError('Discussion is already running')
            self.busy.add(group_id)
        reports = self.r.plugins.get('tools/reports')
        reference = None
        try:
            info = self.r.rpc('group_info', group_id=group_id)
            if info['completed'] and 'task' not in p:
                return dict(status='ok', run_id=info['run_id'], archive_path=info['archive_path'], result=self.r.rpc('read', actor=actor, target=info['output_id'], request=dict(method='key', key='content'), strength=self.r.state(actor)['strength']))
            task = p.get('task', info.get('task'))
            if not task:
                raise ValueError('New discussion requires a task')
            if any(member not in self.r.states for member in info['members']):
                raise ValueError('Group members are not mounted in this process')
            info = self.r.rpc('group_begin', group_id=group_id, task=task, caller=actor)
            diagnostics = self.r.plugins.get('tools/execution_records')
            if diagnostics:
                diagnostics.start(actor)
            if reports:
                reference = reports.delegate(actor, group_id, task, kind='discussion')
                reports.archive(info['recorder_id'], reference)
            start = info['round'] - int(info['busy'])
            for _ in range(start, info['total']):
                round = self.r.rpc('start_round', group_id=group_id)
                info = self.r.rpc('group_info', group_id=group_id)
                members = [m for m in info['active_members'] if m not in round.get('submitted', {})]
                for member in members:
                    self.turns[member]['resident_snapshot'] = [round['notebook_snapshot']]
                message = f"项目任务：{task}\n本次运行：{info['run_id']}\n项目资料ID：{'、'.join(info['project_ids'])}；成果ID：{info['output_id']}。项目资料已首次加载，后续按需使用绑定查询工具。公共笔记使用轮初共同快照；Recorder用write_resident_text维护，更新在下一轮可见。个人记忆用datanet_memory_read、datanet_memory_write维护。\n上轮所有成员发言（共同快照）：\n{round['snapshot']}\n通常讨论按需访问资料、维护个人记忆。"
                execution_id = getattr(self.r.local, 'execution_id', None)
                def run(member):
                    self.r.local.execution_id = execution_id
                    return self.schedule(actor, member, message, reference, info, round['round'])
                with ThreadPoolExecutor(max_workers=max(1, len(members))) as pool:
                    futures = {pool.submit(run, member): member for member in members}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as error:
                            member = futures[future]
                            if member in (info['leader_id'], info['recorder_id']):
                                for peer in members:
                                    self.r.host('cancel-agent', actor=peer)
                                raise
                            self.r.rpc('discussion_member_exit', group_id=group_id, target=member, reason=str(error))
                            self.notify_loss(group_id, actor)
                self.r.rpc('finish_round', group_id=group_id)
            final = self.r.rpc('group_info', group_id=group_id)
            message = f"讨论已结束。请根据任务“{task}”和历史上下文，以及以下最后一轮全部成员发言（这是归档后的完整提交，须据此汇总，不能只依据轮初快照）：\n{json.dumps(final['submitted'], ensure_ascii=False, indent=2)}\n本轮已退出的普通成员：{'、'.join(final['unavailable']) or '无'}。\n按当前任务要求归档；需要操作证据时进入 datanet_reports_channel，查询本次讨论委托的报告索引并读取真实报告或工具结果。不要猜测脚本路径、命令或退出码；证据缺失时注明缺失，不补造。把最终成果写入 {info['output_id']}，用node_write、key=content、mode=upsert；然后回复最终结论。"
            self.schedule(actor, info['recorder_id'], message, reference, final, final=True)
            if not self.turns[info['recorder_id']]['output_written']:
                raise RuntimeError('FINAL_OUTPUT_NOT_CONFIRMED: Recorder 本次未成功写入非空最终成果；讨论已完成，请继续收尾，不要重新建组。')
            result = self.r.rpc('read', actor=actor, target=info['output_id'], request=dict(method='key', key='content'), strength=self.r.state(actor)['strength'])
            completed = self.r.rpc('group_complete', group_id=group_id, report_reference=reference)
            self.r.rpc('save')
            if reports:
                reports.end(reference, 'completed')
            return dict(status='ok', output=result['items'], result=result, report_reference=reference,
                        run_id=completed['run_id'], archive_path=completed['archive_path'], unavailable=final['unavailable'])
        except Exception as error:
            self.r.rpc('group_error', group_id=group_id, error=str(error))
            if reports and reference:
                reports.end(reference, 'failed', str(error))
            raise
        finally:
            with self.lock:
                self.busy.remove(group_id)
