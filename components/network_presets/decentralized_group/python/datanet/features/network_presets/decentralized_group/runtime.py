"""Optional peer collaboration policy on native events and persistent delegations."""
from threading import RLock, Timer
from time import time, monotonic, sleep
import json
from datanet.core.application import Component
from .workspace import Workspace


class Plugin(Component):
    def install(self):
        self.lock, self.timers, self.closed, self.starting = RLock(), {}, False, set()
        self.on('network/before-create', self.before_create)
        self.on('network/created', self.created)
        self.on('agent/bound', self.bound)
        self.on('agent/pre-step', self.pre_step)
        self.on('agent/request', self.request)
        self.on('agent/turn-stopping', self.stopping)
        self.on('context/tail', self.tail)
        self.on('delegation/delivery', self.delivery)
        self.on('delegation/settled', self.settled)
        self.on('tool/available', self.available)
        # An uncertain native operation is retained for inspection, never replayed.
        queue = self.r.plugins['tools/agent_delegation']
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
        return self.r.rpc('cooperative_' + method, actor=actor, group_id=group['group_id'], strength=self.r.state(actor)['strength'], **params)

    def before_create(self, e):
        if e['arguments']['preset'] != 'decentralized_group' or e['arguments'].get('with_agents') is False:
            return
        state = self.r.state(e['actor'])
        if state['grant']['framework'].get('datanet_create_agent', {}).get('scope') != 'descendants':
            raise PermissionError('此预设需要 descendants 范围的 Agent 创建权限')
        self.r.resolve(self.r.presets['cooperative_worker']['toolboxes'], self.r.allowed, 'cooperative_worker')
        if state['strength'] < 2:
            raise PermissionError('创建者信号上限须至少为2')

    def created(self, e):
        if e['arguments']['preset'] != 'decentralized_group' or e['arguments'].get('with_agents') is False:
            return
        group = self.r.backend.cooperative_groups[e['result']['group_id']]
        manager = self.r.plugins['tools/network_management']
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

    def bound(self, e):
        if e['actor'] == 'root':
            for group in list(self.r.backend.cooperative_groups.values()):
                if group['phase'] in ('running', 'review'):
                    self.arm(group)

    def available(self, e):
        if e['name'].startswith('datanet_team_') and self.group_for(e['actor']) is None:
            e['allowed'] = False

    def workspace(self, group):
        return Workspace(self.r.directory / 'cooperation' / group['group_id'].encode().hex() / 'workspace', group['members'])

    def group(self, actor):
        group = self.group_for(actor)
        if not group:
            raise PermissionError('节点不是协作小组成员')
        return group

    def guide(self, actor):
        self.r.load(actor, 'preset:decentralized_group', self.r.resource(self.id, 'AGENTS.md'))

    def pre_step(self, e):
        if e['actor'] == 'root':
            for saved in self.r.backend.cooperative_groups.values():
                if saved.get('caller') and not saved.get('notified') and saved['phase'] not in ('ready', 'running', 'review'):
                    self.notify(saved)
        group = self.group_for(e['actor'])
        if not group:
            return
        self.guide(e['actor'])
        if group['phase'] in ('running', 'review'):
            if time() >= group['deadline']:
                self.stop_group(group, 'budget_exhausted', '达到运行时间预算')
                raise RuntimeError('协作时间预算已结束')
            if group['requests'].get(e['actor'], 0) >= self.r.config.get('cooperativeRequestLimit', 100):
                self.stop_group(group, 'budget_exhausted', '成员达到模型请求预算')
                raise RuntimeError('协作请求预算已结束')

    def request(self, e):
        group = self.group_for(e['actor'])
        if group and group['phase'] in ('running', 'review'):
            with self.r.backend._transaction_lock:
                group['requests'][e['actor']] = group['requests'].get(e['actor'], 0) + 1
                self.r.rpc('save')

    def stopping(self, e):
        group = self.group_for(e['actor'])
        if group and group['phase'] in ('running', 'review'):
            self.r.host('steer', actor=e['actor'], text='共同目标尚未收尾。依据当前协作状态继续推进；没有可执行工作时联系同组成员，已有成果候选时完成验收。')

    def tail(self, e):
        from copy import deepcopy
        group = self.group_for(e['actor'])
        if group:
            with self.r.backend._transaction_lock:
                payload = deepcopy(dict(group_id=group['group_id'], phase=group['phase'], run_id=group['run_id'], task=group['task'],
                               members=group['members'], active_claims=[c for c in group['claims'].values() if c['state'] == 'active'],
                               candidate=group['candidate'], recent_entries=group['entries'][-20:]))
            e['texts'].append('[协作状态：' + group['group_id'] + ']\n' + json.dumps(payload, ensure_ascii=False))

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
            if actor == sender:
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
            result = dict(type='cooperation_result', group_id=group['group_id'], run_id=run_id, status=group['phase'],
                          output_id=group['entry_points']['output'], workspace=str(self.workspace(group).main), failure=group.get('failure'),
                          report_reference=reference, archive_path=str(self.r.directory / group['archive_path']) if group.get('archive_path') else None)
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
        reports = self.r.plugins.get('tools/reports')
        if reports and reference:
            reports.end(reference, 'completed' if result['status'] == 'completed' else 'failed', result['failure'])

    def stop_group(self, group, phase, reason):
        with self.lock:
            if group['phase'] not in ('running', 'review'):
                return
            self.r.rpc('cooperative_stop', actor=group['caller'], group_id=group['group_id'], strength=self.r.state(group['caller'])['strength'], phase=phase, failure=reason)
            queue = self.r.plugins['tools/agent_delegation']
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
            queue = self.r.plugins['tools/agent_delegation']
            job = queue.jobs.get(e['delegation_id'])
            if e['delegation_id'] not in group['jobs'].values() or (job and job.get('context', {}).get('cooperative_run_id', group['run_id']) != group['run_id']):
                return
            jobs = [queue.jobs[id] for id in group['jobs'].values() if id in queue.jobs]
            failed = next((job for job in jobs if job['status'] in ('failed', 'blocked', 'interrupted')), None)
            if failed and group['phase'] in ('running', 'review'):
                self.stop_group(group, 'failed', json.dumps(failed.get('result'), ensure_ascii=False))
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
        queue = self.r.plugins['tools/agent_delegation']
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
        self.workspace(group).prepare()
        self.call('start', actor, group, **{k: p[k] for k in ('task', 'budget_minutes') if k in p})
        try:
            reports = self.r.plugins.get('tools/reports')
            parent = reports.delegate(actor, group['group_id'], p['task'], kind='cooperation') if reports else None
            self.r.rpc('cooperative_update', group_id=group['group_id'], report_reference=parent)
            self.arm(group)
            for member in group['members']:
                if group['phase'] not in ('running', 'review'):
                    break
                self.guide(member)
                project = self.r.rpc('query_text', actor=member, target=group['entry_points']['project'], strength=self.r.state(member)['strength'])
                self.r.load(member, 'cooperation:project:' + group['group_id'], project['text'])
                task = f"共同目标：{p['task']}\n协作小组：{group['group_id']}；本次运行：{group['run_id']}。\n你的工作目录：{self.workspace(group).personal(member)}\n成员平等，自主认领并推进；完成局部工作后继续寻找有价值的工作，共同成果通过 datanet_team_finish 验收收尾。"
                receipt = self.r.plugins['tools/agent_delegation'].submit(actor, member, task, context={'cooperative_group_id': group['group_id'], 'cooperative_run_id': group['run_id']}, parent=parent, timeout_ms=max(1000, int((group['deadline'] - time()) * 1000)))
                jobs = {**group['jobs'], member: receipt['delegation_id']}
                self.r.rpc('cooperative_update', group_id=group['group_id'], jobs=jobs)
            return dict(status='accepted', group_id=group['group_id'], run_id=group['run_id'], members=group['members'], report_reference=parent)
        except Exception as error:
            self.stop_group(group, 'failed', str(error))
            raise

    def tool_datanet_team_status(self, actor, p):
        return self.call('status', actor, self.group(actor), **p)

    def tool_datanet_team_claim(self, actor, p):
        return self.call('claim', actor, self.group(actor), **p)

    def tool_datanet_team_note(self, actor, p):
        return self.call('note', actor, self.group(actor), **p)

    def tool_datanet_team_send(self, actor, p):
        group = self.group(actor)
        if group['phase'] not in ('running', 'review') or p['target'] not in group['members'] or p['target'] == actor:
            raise PermissionError('只能向运行中的本组其他成员发信')
        return self.r.plugins['toolboxes/agent_messaging'].deliver(actor, p['target'], p['content'])

    def tool_datanet_team_workspace(self, actor, p):
        group = self.group(actor)
        if p['action'] != 'inspect' and group['phase'] != 'running':
            raise ValueError('仅运行阶段允许修改共同成果')
        with self.lock:
            return self.workspace(group).invoke(actor, p['action'], p.get('message', 'Publish contribution'))

    def tool_datanet_team_finish(self, actor, p):
        group = self.group(actor)
        with self.lock:
            result = self.call('finish', actor, group, **p)
            if result['phase'] == 'review' and p['action'] == 'propose':
                self.broadcast(group, actor, '本组已提出最终成果候选：' + result['candidate']['id'] + '。读取 datanet_team_status，对照目标和共同工作区验收，使用 datanet_team_finish approve 或 reject，并提供证据。')
            elif p['action'] == 'reject':
                self.broadcast(group, actor, '成果候选被否决：' + p['evidence'] + '。小组恢复工作，请协商认领并修正。')
            if result['phase'] == 'completed':
                reports = self.r.plugins.get('tools/reports')
                if reports:
                    reports.artifact(actor, result['candidate']['content'])
                self.broadcast(group, actor, '共同成果已获全体成员验收，协作结束。请停止当前工作并简短回复。')
                self.notify(group)
                self.r.host('conclude')
            return dict(phase=result['phase'], candidate=result['candidate'], output_id=result['entry_points']['output'])

    def close(self):
        self.closed = True
        for timer in self.timers.values():
            timer.cancel()
