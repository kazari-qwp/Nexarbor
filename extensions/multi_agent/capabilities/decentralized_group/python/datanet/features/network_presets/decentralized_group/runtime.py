"""Optional peer collaboration policy on native events and persistent delegations."""
from threading import RLock, Timer
from time import time, monotonic, sleep
import json
import hashlib
from pathlib import Path
from datanet.core.application import Component
from datanet.workspace.git import Workspace


class Plugin(Component):
    def install(self):
        self.lock, self.timers, self.closed, self.starting = RLock(), {}, False, set()
        self.on('network/before-create', self.before_create)
        self.on('network/created', self.created)
        self.on('agent/bound', self.bound)
        self.on('agent/pre-step', self.pre_step)
        self.on('agent/request', self.request)
        self.on('agent/error', self.native_error)
        self.on('agent/turn-stopping', self.stopping)
        self.on('context/tail', self.tail)
        self.on('delegation/delivery', self.delivery)
        self.on('delegation/settled', self.settled)
        self.on('tool/available', self.available)
        # An uncertain native operation is retained for inspection, never replayed.
        queue = self.r.plugins['capabilities/agent_delegation']
        for group in self.r.backend.cooperative_groups.values():
            if group['phase'] in ('running', 'review') and any(queue.jobs.get(id, {}).get('status') == 'interrupted' for id in group['jobs'].values()):
                self.r.rpc('cooperative_update', group_id=group['group_id'], phase='interrupted', failure='客户端关闭时成员尚未完成，请检查保存的工作区、认领与报告。')
                for id in group['jobs'].values():
                    if id in queue.jobs:
                        queue.cancel(id)

    def group_for(self, actor):
        with self.r.backend._transaction_lock:
            binding = self.r.backend.agents.get(actor, {})
            current = self.r.backend.cooperative_groups.get(binding.get('cooperative_group_id'))
            if current and actor in current['members'] and current['entry_points']['board'] in self.r.backend.network.nodes:
                return current
            return next((g for g in self.r.backend.cooperative_groups.values() if actor in g['members'] and g['entry_points']['board'] in self.r.backend.network.nodes), None)

    def call(self, method, actor, group, **params):
        result = self.r.rpc('cooperative_' + method, actor=actor, group_id=group['group_id'], strength=self.r.state(actor)['strength'], **params)
        if method == 'status':
            result['repository'] = self.workspace(group).repository()
            result['member_runtime'] = {}
            for member in group['members']:
                try:
                    native = self.r.host('inspect', actor=member)
                    result['member_runtime'][member] = dict(status=native['status'], pending_approvals=native.get('pending_approvals', []))
                except Exception:
                    result['member_runtime'][member] = dict(status='unmounted', pending_approvals=[])
        return result

    def before_create(self, e):
        if e['arguments']['preset'] != 'decentralized_group' or e['arguments'].get('with_agents') is False:
            return
        state = self.r.state(e['actor'])
        if state['grant']['framework'].get('datanet_create_network', {}).get('scope') != 'descendants':
            raise PermissionError('此预设需要 descendants 范围的网络创建权限')
        self.r.resolve(self.r.presets['cooperative_worker']['toolboxes'], self.r.allowed, 'cooperative_worker')
        if state['strength'] < 2:
            raise PermissionError('创建者信号上限须至少为2')

    def created(self, e):
        if e['arguments']['preset'] != 'decentralized_group' or e['arguments'].get('with_agents') is False:
            return
        group = self.r.backend.cooperative_groups[e['result']['group_id']]
        manager = self.r.plugins['capabilities/agent_runtime']
        preset = self.r.presets['cooperative_worker']
        for old in list(group['members']):
            result = manager.create(old, self.r.resource(preset['owner'], preset['prompt']), e['actor'],
                                    preset['max_signal_strength'], preset['toolboxes'], 'cooperative_worker')
            new = result['node_id']
            if new != old:
                group['members'] = [new if id == old else id for id in group['members']]
                structure = e['result']['structure']
                for row in structure['nodes']:
                    if row['node_id'] == old:
                        row['node_id'] = new
                for edge in structure['interfaces'] + structure['attachment_interfaces']:
                    for field in ('source_node_id', 'target_node_id'):
                        if edge[field] == old:
                            edge[field] = new
            self.r.rpc('agent_progress', target=new, cooperative_group_id=group['group_id'])
            self.r.refresh(new)
        e['result']['members'] = list(group['members'])
        self.r.rpc('cooperative_update', group_id=group['group_id'], workspace_directory=str(self.workspace(group).directory))

    def bound(self, e):
        if e['actor'] == 'root':
            for group in list(self.r.backend.cooperative_groups.values()):
                if group['phase'] in ('running', 'review'):
                    self.arm(group)

    def available(self, e):
        if e['name'].startswith('datanet_team_') and self.group_for(e['actor']) is None:
            e['allowed'] = False

    def workspace(self, group):
        if group.get('workspace_directory'):
            return Workspace(Path(group['workspace_directory']), group['members'])
        # Keep process working directories short; Windows CreateProcess has a separate cwd limit.
        root_key = hashlib.sha256(str(self.r.directory).encode()).hexdigest()[:16]
        group_key = hashlib.sha256(group['group_id'].encode()).hexdigest()[:16]
        base = Path(self.r.config.get('workspace') or self.r.directory)
        return Workspace(base / '.datanet' / 'workspaces' / root_key / group_key, group['members'])

    def group(self, actor):
        group = self.group_for(actor)
        if not group:
            raise PermissionError('节点不是协作小组成员')
        return group

    def guide(self, actor, member=False):
        document = 'preset:decentralized_group' + (':member' if member else '')
        path = 'members/AGENTS.md' if member else 'AGENTS.md'
        self.r.load(actor, document, self.r.resource(self.id, path))

    def pre_step(self, e):
        if e['actor'] == 'root':
            for saved in self.r.backend.cooperative_groups.values():
                if saved.get('caller') and not saved.get('notified') and saved['phase'] not in ('ready', 'running', 'review'):
                    self.notify(saved)
        group = self.group_for(e['actor'])
        if not group:
            return
        self.guide(e['actor'], member=True)
        if e['actor'] in group.get('unavailable', {}):
            raise RuntimeError('成员已退出本轮协作')
        if group['phase'] in ('running', 'review'):
            if time() >= group['deadline']:
                self.stop_group(group, 'budget_exhausted', '达到运行时间预算')
                raise RuntimeError('协作时间预算已结束')
            if group['requests'].get(e['actor'], 0) >= self.r.config.get('cooperativeRequestLimit', 100):
                self.retire(group, e['actor'], '成员达到模型请求预算', 'budget_exhausted', cancel=True)
                raise RuntimeError('成员请求预算已结束')

    def native_error(self, e):
        group = self.group_for(e['actor'])
        if group and group['phase'] in ('running', 'review'):
            with self.lock:
                failure = e.get('failure') or {}
                reason = (str(failure['code']) + ': ' if failure.get('code') else '') + str(failure.get('message') or e['error'])
                self.retire(group, e['actor'], reason)

    def request(self, e):
        group = self.group_for(e['actor'])
        if group and group['phase'] in ('running', 'review'):
            if e['actor'] in group.get('unavailable', {}):
                raise RuntimeError('成员已退出本轮协作')
            if group['requests'].get(e['actor'], 0) >= self.r.config.get('cooperativeRequestLimit', 100):
                self.retire(group, e['actor'], '成员达到模型请求预算', 'budget_exhausted', cancel=True)
                raise RuntimeError('成员请求预算已结束')
            with self.r.backend._transaction_lock:
                group['requests'][e['actor']] = group['requests'].get(e['actor'], 0) + 1
                self.r.rpc('save')

    def stopping(self, e):
        group = self.group_for(e['actor'])
        if group and group['phase'] in ('running', 'review') and e['actor'] not in group.get('unavailable', {}):
            candidate = group.get('candidate')
            if candidate and e['actor'] in candidate['approvals']:
                return
            self.r.host('steer', actor=e['actor'], text='共同目标尚未收尾。依据当前协作状态继续推进；已有候选时阅读验收材料，有异议指出具体问题，无异议提交批准。')

    def tail(self, e):
        group = self.group_for(e['actor'])
        if group:
            with self.r.backend._transaction_lock:
                phase = {'ready': '待开始', 'running': '执行', 'review': '审核', 'completed': '完成', 'stopped': '停止', 'failed': '失败', 'interrupted': '中断', 'budget_exhausted': '预算结束'}.get(group['phase'], group['phase'])
                text = '[协作组：' + group['group_id'] + ']\n阶段：' + phase + '。'
                candidate = group.get('candidate')
                if group['phase'] == 'review' and candidate and e['actor'] not in candidate['approvals']:
                    text += '\n目前有成果等待审核。'
            e['texts'].append(text)

    def arm(self, group):
        with self.lock:
            if self.closed:
                return
            old = self.timers.pop(group['group_id'], None)
            if old:
                old.cancel()
            timer = Timer(max(.01, group['deadline'] - time()), self.expire, args=(group['group_id'], group['run_id']))
            timer.daemon = True
            self.timers[group['group_id']] = timer
            timer.start()

    def expire(self, id, run_id=None):
        try:
            with self.lock:
                group = self.r.backend.cooperative_groups[id]
                if not self.closed and (run_id is None or group['run_id'] == run_id):
                    self.stop_group(group, 'budget_exhausted', '达到运行时间预算')
        except Exception as error:
            self.r.errors.append(dict(component=self.id, error=str(error)))

    def broadcast(self, group, sender, text):
        for actor in group['members']:
            if actor == sender or actor in group.get('unavailable', {}):
                continue
            self.r.emit('agent/ensure-mounted', target=actor)
            self.r.host('steer', actor=actor, text=text)

    def notify(self, group):
        if self.closed or group.get('notified') or group['phase'] in ('ready', 'running', 'review'):
            return
        # Reserve before steering: waking the caller may immediately re-enter events.
        with self.lock:
            if group.get('notified'):
                return
            self.r.rpc('cooperative_update', group_id=group['group_id'], notified=True)
            caller, reference, run_id = group['caller'], group.get('report_reference'), group['run_id']
            workspace = self.workspace(group)
            result = dict(type='cooperation_result', group_id=group['group_id'], run_id=run_id, status=group['phase'],
                          output_id=group['entry_points']['output'], workspace=str(self.workspace(group).main), failure=group.get('failure'),
                          active_members=self.active_members(group), unavailable=group.get('unavailable', {}),
                          report_reference=reference, repository=workspace.repository(), archive_path=str(self.r.directory / group['archive_path']) if group.get('archive_path') else None)
            timer = self.timers.pop(group['group_id'], None)
            if timer:
                timer.cancel()
        self.r.emit('agent/ensure-mounted', target=caller)
        try:
            self.r.host('steer', actor=caller, text=json.dumps(result, ensure_ascii=False))
        except Exception:
            if group['run_id'] == run_id:
                self.r.rpc('cooperative_update', group_id=group['group_id'], notified=False)
            raise
        reports = self.r.plugins.get('capabilities/reports')
        if reports and reference:
            reports.end(reference, 'completed' if result['status'] == 'completed' else 'failed', result['failure'])

    def stop_group(self, group, phase, reason):
        with self.lock:
            if group['phase'] not in ('running', 'review'):
                return
            self.r.rpc('cooperative_stop', actor=group['caller'], group_id=group['group_id'], strength=self.r.state(group['caller'])['strength'], phase=phase, failure=reason)
            queue = self.r.plugins['capabilities/agent_delegation']
            for id in list(group['jobs'].values()):
                queue.cancel(id)
            for actor in group['members']:
                if actor in self.r.states and self.r.host('inspect', actor=actor)['status'] != 'idle':
                    self.r.host('cancel-agent', actor=actor)
            self.notify(group)

    def delivery(self, e):
        id = e['job'].get('context', {}).get('cooperative_group_id')
        if id:
            e['delivery']['handled'] = True

    def settled(self, e):
        group = self.group_for(e['actor'])
        if not group:
            return
        with self.lock:
            queue = self.r.plugins['capabilities/agent_delegation']
            job = queue.jobs.get(e['delegation_id'])
            if e['delegation_id'] not in group['jobs'].values() or (job and job.get('context', {}).get('cooperative_run_id', group['run_id']) != group['run_id']):
                return
            if job and job['status'] in ('failed', 'blocked', 'interrupted', 'cancelled') and group['phase'] in ('running', 'review'):
                self.retire(group, e['actor'], json.dumps(job.get('result'), ensure_ascii=False), job['status'])
            self.notify(group)

    def active_members(self, group):
        return [member for member in group['members'] if member not in group.get('unavailable', {})]

    def notify_loss(self, group):
        lost = group.get('unavailable', {})
        if len(lost) * 2 < len(group['members']) or group.get('loss_notice_sent'):
            return
        self.r.rpc('cooperative_update', group_id=group['group_id'], loss_notice_sent=True)
        # Follow the group's current management binding; terminal delivery reaches the caller.
        manager = self.r.backend.agents[group['members'][0]].get('manager_id') or group['owner']
        active = self.active_members(group)
        if not active and manager == group['caller']:
            return
        notice = dict(type='cooperation_degraded', group_id=group['group_id'], run_id=group['run_id'],
                      exited_count=len(lost), total_members=len(group['members']), active_members=active,
                      unavailable=lost, continuing=bool(active), message='本轮至少一半成员已退出；剩余成员继续工作。' if active else '本轮全部成员已退出，小组无法继续。')
        try:
            self.r.emit('agent/ensure-mounted', target=manager)
            self.r.host('steer', actor=manager, text=json.dumps(notice, ensure_ascii=False))
        except Exception as error:
            self.r.rpc('cooperative_update', group_id=group['group_id'], loss_notice_sent=False)
            self.r.errors.append(dict(component=self.id, error=str(error)))

    def retire(self, group, actor, reason, status='failed', cancel=False):
        if group['phase'] not in ('running', 'review') or actor in group.get('unavailable', {}):
            return
        self.r.rpc('cooperative_member_exit', actor=group['caller'], group_id=group['group_id'], target=actor, reason=reason, status=status)
        if cancel:
            id = group['jobs'].get(actor)
            if id:
                self.r.plugins['capabilities/agent_delegation'].cancel(id)
            self.r.host('cancel-agent', actor=actor)
        self.notify_loss(group)
        if not self.active_members(group):
            self.stop_group(group, 'failed', json.dumps(dict(message='本轮全部成员无法继续', members=group['unavailable']), ensure_ascii=False))
            return
        message = '共同成果已获本轮剩余成员验收，协作结束。请停止当前工作并简短回复。' if group['phase'] == 'completed' else '成员 ' + actor + ' 已退出本轮，其未完成认领已释放。用 datanet_team_status 查看退出原因、认领和工作区，继续推进共同目标。'
        self.broadcast(group, actor, message)
        self.notify(group)

    def tool_datanet_cooperate(self, actor, p):
        self.guide(actor)
        group = self.r.backend.cooperative_groups.get(p['group_id'])
        if not group:
            raise ValueError('未知去中心化小组')
        if p['action'] == 'status':
            return self.call('status', actor, group)
        # Control requires write reachability as well as read reachability.
        if not self.r.rpc('check_access', actor=actor, target=group['entry_points']['board'], direction='write', strength=self.r.state(actor)['strength'])['allowed']:
            raise PermissionError('小组不在调用者写入范围内')
        if p['action'] == 'stop':
            self.call('status', actor, group)
            if actor in group['members']:
                raise PermissionError('由网络调用者停止小组')
            self.stop_group(group, 'stopped', '调用者请求停止')
            return self.call('status', actor, group)
        if p['action'] != 'start':
            raise ValueError('未知协作操作')
        if actor in group['members']:
            raise PermissionError('由网络调用者启动小组')
        if any(member not in self.r.states for member in group['members']):
            raise ValueError('协作成员尚未装配')
        with self.lock:
            if group['phase'] in ('running', 'review') or group['group_id'] in self.starting:
                raise ValueError('小组正在执行任务，使用 status 查看或 stop 收尾')
            self.starting.add(group['group_id'])
        try:
            return self.start_group(actor, p, group)
        finally:
            with self.lock:
                self.starting.discard(group['group_id'])

    def settle_previous(self, group):
        queue = self.r.plugins['capabilities/agent_delegation']
        deadline = monotonic() + 30
        for id in list(group['jobs'].values()):
            job = queue.jobs.get(id)
            if job and job['status'] in ('queued', 'running'):
                queue.cancel(id)
        for actor in group['members']:
            if self.r.host('inspect', actor=actor)['status'] != 'idle':
                self.r.host('cancel-agent', actor=actor)
        while True:
            with queue.lock:
                pending = any(queue.jobs.get(id, {}).get('status') in ('queued', 'running') for id in group['jobs'].values())
            idle = all(self.r.host('inspect', actor=actor)['status'] == 'idle' for actor in group['members'])
            if not pending and idle:
                return
            if monotonic() >= deadline:
                raise RuntimeError('上一轮成员循环尚未停止，请稍后重新启动')
            sleep(.01)

    def start_group(self, actor, p, group):
        self.settle_previous(group)
        if group.get('run_id') and not group.get('notified'):
            self.notify(group)
        # Prepare resources before accepting a running task.
        workspace = self.workspace(group)
        workspace.prepare()
        self.r.rpc('cooperative_update', group_id=group['group_id'], workspace_directory=str(workspace.directory))
        self.call('start', actor, group, **{k: p[k] for k in ('task', 'budget_minutes') if k in p})
        try:
            reports = self.r.plugins.get('capabilities/reports')
            parent = reports.delegate(actor, group['group_id'], p['task'], kind='cooperation') if reports else None
            self.r.rpc('cooperative_update', group_id=group['group_id'], report_reference=parent)
            self.arm(group)
            for member in group['members']:
                if group['phase'] not in ('running', 'review'):
                    break
                self.guide(member, member=True)
                project = self.r.rpc('query_text', actor=member, target=group['entry_points']['project'], strength=self.r.state(member)['strength'])
                self.r.load(member, 'cooperation:project:' + group['group_id'], project['text'])
                task = f"共同目标：{p['task']}\n协作小组：{group['group_id']}；本次运行：{group['run_id']}。\n你的工作目录：{self.workspace(group).personal(member)}\n成员平等，自主认领并推进；完成局部工作后继续寻找有价值的工作，共同成果通过 datanet_team_finish 验收收尾。"
                receipt = self.r.plugins['capabilities/agent_delegation'].submit(actor, member, task, context={'cooperative_group_id': group['group_id'], 'cooperative_run_id': group['run_id']}, parent=parent, timeout_ms=max(1000, int((group['deadline'] - time()) * 1000)))
                jobs = {**group['jobs'], member: receipt['delegation_id']}
                self.r.rpc('cooperative_update', group_id=group['group_id'], jobs=jobs)
                # A fast native failure may settle before its receipt is registered.
                self.settled(dict(actor=member, delegation_id=receipt['delegation_id']))
            return dict(status='accepted', group_id=group['group_id'], run_id=group['run_id'], members=group['members'], report_reference=parent)
        except Exception as error:
            self.stop_group(group, 'failed', str(error))
            raise

    def tool_datanet_team_status(self, actor, p):
        group = self.group(actor)
        section = p.get('section', 'all')
        if section == 'all':
            return self.call('status', actor, group, **p)
        state = self.r.rpc('cooperative_status', actor=actor, group_id=group['group_id'], strength=self.r.state(actor)['strength'], **p)
        fields = {'summary': ('task', 'members', 'active_members', 'unavailable', 'requests', 'failure'), 'claims': ('claims',), 'records': ('entries', 'entry_count'), 'candidate': ('candidate',)}
        return dict(group_id=state['group_id'], phase=state['phase'], **{key: state[key] for key in fields[section]})

    def tool_datanet_team_claim(self, actor, p):
        return self.call('claim', actor, self.group(actor), **p)

    def tool_datanet_team_note(self, actor, p):
        return self.call('note', actor, self.group(actor), **p)

    def tool_datanet_team_send(self, actor, p):
        group = self.group(actor)
        if group['phase'] not in ('running', 'review') or p['target'] not in self.active_members(group) or actor not in self.active_members(group) or p['target'] == actor:
            raise PermissionError('只能向运行中的本组其他成员发信')
        return self.r.plugins['capabilities/agent_messaging'].deliver(actor, p['target'], p['content'], message_type=p.get('message_type', 'work_order'))

    def tool_datanet_team_workspace(self, actor, p):
        group = self.group(actor)
        if p['action'] != 'inspect' and (group['phase'] != 'running' or actor in group.get('unavailable', {})):
            raise ValueError('仅运行阶段允许修改共同成果')
        with self.lock:
            result = self.workspace(group).invoke(actor, p['action'], p.get('message', 'Publish contribution'))
            logs = self.r.plugins.get('capabilities/command_logs')
            if logs:
                result['artifacts_path'] = str(logs.directory(actor))
            return result

    def tool_datanet_team_finish(self, actor, p):
        group = self.group(actor)
        with self.lock:
            arguments = dict(p)
            if p['action'] == 'propose' and group['phase'] == 'running' and not group['candidate'] and not any(c['state'] == 'active' for c in group['claims'].values()):
                logs = self.r.plugins.get('capabilities/command_logs')
                records = logs.logs(actor, p.get('log_ids'), since=group.get('started_at', 0)) if logs else []
                artifacts = logs.directory(actor) if logs else self.workspace(group).directory / 'artifacts'
                arguments['review'] = self.workspace(group).proposal(actor, p.get('test_scripts', []), p.get('test_results', []), records, artifacts)
            for field in ('test_scripts', 'test_results', 'log_ids'):
                arguments.pop(field, None)
            result = self.call('finish', actor, group, **arguments)
            if result['phase'] == 'review' and p['action'] == 'propose':
                self.broadcast(group, actor, '本组已提出成果候选：' + result['candidate']['id'] + '。读取 datanet_team_status 中的验收材料，审阅测试脚本、命令、结果和已知问题；无异议批准，有疑问指出具体问题再补测。')
            elif p['action'] == 'reject':
                self.broadcast(group, actor, '成果候选被否决：' + p['evidence'] + '。小组恢复工作，请协商认领并修正。')
            if result['phase'] == 'completed':
                reports = self.r.plugins.get('capabilities/reports')
                if reports:
                    reports.artifact(actor, result['candidate']['content'])
                self.broadcast(group, actor, '共同成果已获本轮剩余成员验收，协作结束。请停止当前工作并简短回复。')
                self.notify(group)
                self.r.host('conclude')
            elif result['phase'] == 'review' and actor in result['candidate']['approvals']:
                self.r.host('conclude')
            return dict(phase=result['phase'], candidate=result['candidate'], output_id=result['entry_points']['output'])

    def close(self):
        self.closed = True
        for timer in self.timers.values():
            timer.cancel()
