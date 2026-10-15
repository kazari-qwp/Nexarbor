from copy import deepcopy
from uuid import uuid4
from datanet.core.application import Component
from datanet.core.record_values import now, redact

TEMPORARY = {'experience_query', 'experience_submit', 'incident_query', 'incident_resolve', 'datanet_feedback', 'problem_attempt', 'problem_resolved', 'problem_defer'}
INSPECTION = {'datanet_contacts_channel', 'datanet_pending_messages', 'read', 'glob', 'grep', 'node_read', 'node_list', 'node_tools', 'network_structure', 'datanet_recovery_status', 'experience_review', 'datanet_agent_capabilities', 'datanet_presets'}

def text(value, name, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('Invalid ' + name)
    return value.strip()


class Plugin(Component):
    def install(self):
        self.store = self.r.plugins['capabilities/experience'].store
        self.problems, self.unlocked = {}, set()
        self.on('agent/bound', self.bound)
        self.on('context/prepare', self.prepare)
        self.on('context/tail', self.tail)
        self.on('tool/available', self.available)
        self.on('tool/guard', self.guard)
        self.on('tool/before', self.before)
        self.on('tool/result', self.outcome)
        self.on('agent/error', lambda e: self.interrupt(e['actor'], e['error']))
        self.on('agent/turn-stopping', self.stopping)
        self.on('feedback/received', lambda e: self.feedback_received(e['report']))
        def recover(db):
            for problem in db.get('problems', []):
                if problem['source'] == str(self.r.directory) and problem['status'] == 'active':
                    problem.update(status='interrupted', finished_at=now())
        self.store.mutate(recover)
        for report in getattr(self.r.backend, 'feedback', []):
            manager = self.r.backend.agents.get(report['actor'], {}).get('manager_id')
            if manager:
                self.unlocked.add(manager)

    def active(self, actor):
        problem = self.problems.get(actor)
        return problem if problem and problem['status'] == 'active' else None

    def self_repair(self, actor):
        return self.r.state(actor)['grant']['framework'].get('handle_problem', {}).get('allow_self_repair') is True

    def save(self, actor):
        snapshot = deepcopy(self.problems[actor])
        def update(db):
            items = db.setdefault('problems', [])
            index = next((i for i, p in enumerate(items) if p['id'] == snapshot['id']), None)
            if index is None:
                items.append(snapshot)
            else:
                items[index] = snapshot
        self.store.mutate(update)

    def bound(self, e):
        actor = e['actor']
        if actor in self.unlocked:
            self.unlock(actor)

    def available(self, e):
        if e['name'] in TEMPORARY and not self.active(e['actor']):
            e['allowed'] = False
        if e['name'] == 'datanet_resolve_feedback' and e['actor'] not in self.unlocked:
            e['allowed'] = False

    def guard(self, e):
        name, actor = e['name'], e['actor']
        problem = self.active(actor)
        if name in TEMPORARY and not problem:
            e['reason'] = 'Enter handle_problem first'
        if not problem:
            return
        if name in TEMPORARY | INSPECTION | {'handle_problem'} or name.endswith('_channel') or name == 'datanet_send_message' or name.startswith('datanet_reply_') or name == 'datanet_skill' and e.get('arguments', {}).get('action') in ('list', 'read'):
            return
        if problem['stage'] in ('lookup', 'attempt_failed'):
            e['reason'] = 'Query experience, then call problem_attempt before attempting a repair; or defer the unresolved problem if the task can continue, or report a task blocker'

    def before(self, e):
        e['reason'] = None
        self.guard(e)
        if e['reason']:
            raise PermissionError(e['reason'])

    def stopping(self, e):
        if self.active(e['actor']):
            self.r.host('steer', actor=e['actor'], text='当前排障尚未结束：实际修好用 problem_resolved；未解决但当前委托可继续或交付失败结果，用 problem_defer 保留影响后正常汇报；确实阻塞自身委托才用 datanet_feedback。')

    def latest(self, actor):
        return next((report for report in reversed(getattr(self.r.backend, 'feedback', [])) if report['actor'] == actor), None)

    def assert_closed(self, actor):
        if self.active(actor):
            raise RuntimeError('PROBLEM_UNRESOLVED: resolve, defer with task impact, or report a task blocker before completing the task')

    def interrupt(self, actor, error):
        if self.active(actor):
            self.problems[actor].update(status='interrupted', finished_at=now(), interruption=redact(error))
            self.save(actor)
            self.close_tools(actor)

    def close_tools(self, actor):
        self.r.plugins['capabilities/experience'].transient_clear(actor)
        self.r.refresh(actor)

    def tail(self, e):
        actor = e['actor']
        problem = self.active(actor)
        if problem:
            e['texts'].append(f"当前问题：{problem['summary']}\n归属：{problem['origin']}；来源节点：{problem.get('origin_node_id')}；problem_id：{problem['id']}；累计尝试：{len(problem['attempts'])}/{problem['max_attempts']}。达到上限后不得再次修复或执行，选择未解决退出或自身任务阻塞上报。\n阶段：{problem['stage']}；自主排障授权：{'允许（仅原有工具权限内）' if self.self_repair(actor) else '不允许'}。")

    def prepare(self, e):
        import json
        actor = e['actor']
        manager = self.r.backend.agents[actor].get('manager_id')
        self.r.load(actor, 'state:manager', '管理者节点：' + (manager or '无（根 Agent，反馈给用户）') + '。')
        for p in self.store.data.get('problems', []):
            if p['source'] == str(self.r.directory) and p['node_id'] == actor and p['status'] == 'deferred':
                record = dict(problem_id=p['id'], problem=p['summary'], origin=p['origin'], origin_node_id=p.get('origin_node_id'), attempt_count=len(p['attempts']), **p['dispositions'][-1])
                self.r.load(actor, 'state:deferred:' + p['id'], '未解决但已结束排障的问题（不是成功；正常汇报须保留与当前任务有关的失败及影响，重新排障须复用 problem_id）：\n' + json.dumps(record, ensure_ascii=False))
        for report in getattr(self.r.backend, 'feedback', []):
            if self.r.backend.agents.get(report['actor'], {}).get('manager_id') == actor:
                self.r.load(actor, 'state:feedback:' + report['id'], '下属阻塞反馈（历史记录，不代表已解决）：\n' + json.dumps(dict(node_id=report['actor'], error=report['message']), ensure_ascii=False))

    def info(self, actor):
        p = self.active(actor)
        return dict(problem_id=p['id'], origin=p['origin'], origin_node_id=p.get('origin_node_id'), stage=p['stage'], attempt_count=len(p['attempts']), max_attempts=p['max_attempts'], remaining_attempts=max(0, p['max_attempts'] - len(p['attempts'])), allow_self_repair=self.self_repair(actor))

    def tool_handle_problem(self, actor, args):
        limit = args.get('max_attempts', 3)
        if type(limit) is not int or not 1 <= limit <= 3:
            raise ValueError('max_attempts must be an integer from 1 to 3')
        summary, origin = text(args['problem'], 'problem', 240), args['origin']
        source = args.get('origin_node_id')
        if origin == 'self':
            if source and source != actor:
                raise ValueError('Self problem must belong to the current node')
            source = actor
        elif origin == 'subordinate':
            source = text(source, 'origin_node_id', 240)
        elif origin != 'dependency':
            raise ValueError('Invalid problem origin')
        if self.active(actor):
            p = self.active(actor)
            if args.get('problem_id') and args['problem_id'] != p['id']:
                raise ValueError('Finish the current problem before opening another')
            p['max_attempts'] = min(p['max_attempts'], limit)
        else:
            records = self.store.data.get('problems', [])
            old = next((p for p in reversed(records) if p['source'] == str(self.r.directory) and p['node_id'] == actor and p['status'] in ('deferred', 'interrupted', 'reported') and (p['id'] == args['problem_id'] if args.get('problem_id') else p['summary'] == summary and p['origin'] == origin and p.get('origin_node_id') == source)), None)
            if args.get('problem_id') and old is None:
                raise ValueError('Only this node can reopen its unresolved problem')
            p = deepcopy(old) if old else dict(id=str(uuid4()), source=str(self.r.directory), **self.r.metadata(actor), summary=summary, origin=origin, origin_node_id=source, max_attempts=limit, created_at=now(), experience_ids=[], attempts=[], candidate_ids=[])
            p.update(status='active', stage='lookup', queried=False, max_attempts=min(p['max_attempts'], limit))
            self.problems[actor] = p
        self.save(actor)
        added = self.r.load(actor, 'problem_handling', self.r.resource(self.id, 'docs/AGENTS.md'))
        recovery_added = self.self_repair(actor) and self.r.load(actor, 'recovery_limits', self.r.resource(self.id, 'docs/RECOVERY_LIMITS.md'))
        self.r.refresh(actor)
        return dict(**self.info(actor), instructions_added=added, recovery_instructions_added=recovery_added, tools=sorted(TEMPORARY), next='需排障先调用 experience_query；若未解决也不妨碍当前委托，可直接 problem_defer 记录影响并退出。')

    def queried(self, actor, entries):
        p = self.active(actor)
        if not p:
            raise ValueError('Enter handle_problem first')
        p.update(queried=True, experience_ids=list(dict.fromkeys(p['experience_ids'] + [e['id'] for e in entries])))
        self.save(actor)

    def tool_problem_attempt(self, actor, args):
        p = self.active(actor)
        if not p or not p['queried']:
            raise ValueError('Query experience before attempting repair')
        if len(p['attempts']) >= p['max_attempts']:
            raise RuntimeError('RECOVERY_LIMIT_REACHED: no further attempts; defer with task impact or report an actual task blocker')
        experience = args.get('experience_id')
        if experience and experience not in p['experience_ids']:
            raise ValueError('Experience must have been returned by experience_query for this problem')
        if not experience and not self.self_repair(actor):
            raise PermissionError('Self repair is not authorized')
        if p['attempts'] and not p['attempts'][-1].get('finished_at'):
            p['attempts'][-1].update(outcome='abandoned', finished_at=now())
        attempt = dict(id=str(uuid4()), mode='experience' if experience else 'self', experience_id=experience, started_at=now(), successes=[], failures=[])
        p['attempts'].append(attempt)
        p['stage'] = 'trying'
        self.save(actor)
        return dict(problem_id=p['id'], attempt_id=attempt['id'], attempt_count=len(p['attempts']), max_attempts=p['max_attempts'], mode=attempt['mode'])

    def outcome(self, e):
        p = self.active(e['actor'])
        name = e['name']
        if not p or p['stage'] != 'trying' or name in TEMPORARY | {'handle_problem'} or name.endswith('_channel') or name == 'datanet_send_message' or name.startswith('datanet_reply_'):
            return
        result = e['result']
        if '[DATANET_TOOL_PERMISSION_DENIED]' in str(result):
            return
        attempt = p['attempts'][-1]
        if e.get('call_id') and any(item['call_id'] == e['call_id'] for item in attempt['successes'] + attempt['failures']):
            return
        value = result.get('value') or {}
        success = not result.get('isError') and (not isinstance(value, dict) or value.get('status', 'ok') in ('ok', 'success', 'completed') and value.get('exitCode', value.get('exit_code', 0)) == 0)
        evidence = dict(tool=name, call_id=e.get('call_id') or str(uuid4()), time=now())
        if success:
            attempt['successes'] = (attempt['successes'] + [evidence])[-8:]
        else:
            attempt['failures'].append(dict(**evidence, error=redact(str(result))))
            attempt.update(outcome='failed', finished_at=now())
            p['stage'] = 'attempt_failed'
        self.save(e['actor'])

    def can_submit(self, actor):
        p = self.active(actor)
        if not p or p['stage'] != 'trying' or not p['attempts'] or p['attempts'][-1]['mode'] != 'self' or not p['attempts'][-1]['successes'] or not self.self_repair(actor):
            raise ValueError('Candidate submission requires authorized self repair and an observed successful verification')

    def submitted(self, actor, id):
        p = self.active(actor)
        p['candidate_ids'].append(id)
        p['attempts'][-1].setdefault('candidate_ids', []).append(id)
        self.save(actor)

    def record_uses(self, p, resolved):
        def update(db):
            uses = db.setdefault('experience_uses', [])
            for attempt in p['attempts']:
                experience = attempt.get('experience_id')
                if not experience or any(u['problem_id'] == p['id'] and u['experience_id'] == experience for u in uses):
                    continue
                outcome = 'success' if resolved and attempt['id'] == p['attempts'][-1]['id'] else 'failure'
                uses.append(dict(problem_id=p['id'], experience_id=experience, node_id=p['node_id'], source=p['source'], session_id=p['session_id'], outcome=outcome, evidence=p.get('evidence', '方案未解决此问题'), verification=attempt['successes'], time=now()))
                entry = next((e for e in db['entries'] if e['id'] == experience), None)
                if entry:
                    entry['success_count'] = sum(u['experience_id'] == experience and u['outcome'] == 'success' for u in uses)
                    entry['failure_count'] = sum(u['experience_id'] == experience and u['outcome'] == 'failure' for u in uses)
                    entry['promotion_candidate'] = entry['status'] == 'verified' and not entry['core'] and entry['success_count'] >= 5
        self.store.mutate(update)

    def tool_problem_resolved(self, actor, args):
        p = self.active(actor)
        if not p or p['stage'] != 'trying' or not p['attempts'] or not p['attempts'][-1]['successes']:
            raise ValueError('A successful observed verification after problem_attempt is required')
        attempt = p['attempts'][-1]
        if attempt['mode'] == 'self' and not attempt.get('candidate_ids'):
            raise ValueError('Submit the verified solution as candidate experience before finishing self repair')
        p.update(status='resolved', evidence=text(args['evidence'], 'evidence'), finished_at=now())
        attempt.update(outcome='resolved', finished_at=now())
        self.save(actor)
        self.record_uses(p, True)
        self.close_tools(actor)
        return dict(problem_id=p['id'], status='resolved', experience_id=attempt['experience_id'], candidate_ids=p['candidate_ids'], promotion_requires_review=True)

    def tool_problem_defer(self, actor, args):
        p = self.active(actor)
        disposition = {key: text(args[key], key) for key in ('reason', 'impact', 'continuation')}
        disposition['time'] = now()
        p.update(status='deferred', finished_at=now())
        p.setdefault('dispositions', []).append(disposition)
        if p['attempts'] and not p['attempts'][-1].get('finished_at'):
            p['attempts'][-1].update(outcome='unresolved', finished_at=now())
        self.save(actor)
        self.close_tools(actor)
        return dict(problem_id=p['id'], status='deferred', resolved=False, attempt_count=len(p['attempts']), **disposition, next='继续当前委托，正常汇报必须保留未解决问题和影响；继续排障时复用 problem_id，不得重置尝试记录。')

    def reserve(self, actor, target, action):
        feedback = self.latest(target)
        if feedback is None:
            return
        limit = (self.active(actor) or {}).get('max_attempts', 3)
        def update(db):
            budgets = db.setdefault('recovery_budgets', [])
            budget = next((b for b in reversed(budgets) if b['source'] == str(self.r.directory) and b['target'] == target and b['status'] == 'unresolved'), None)
            if budget is None:
                if any(b['target'] == target and b['status'] == 'resolved' and feedback['id'] in b['feedback_ids'] for b in budgets):
                    return
                budget = dict(id=str(uuid4()), source=str(self.r.directory), target=target, status='unresolved', max_attempts=limit, feedback_ids=[], attempts=[], created_at=now())
                budgets.append(budget)
            budget['max_attempts'] = min(budget['max_attempts'], limit)
            if feedback['id'] not in budget['feedback_ids']:
                budget['feedback_ids'].append(feedback['id'])
            attempt = budget['attempts'][-1] if budget['attempts'] else None
            if not attempt or attempt.get('finished_at') or any(a['action'] == action for a in attempt['actions']):
                if len(budget['attempts']) >= budget['max_attempts']:
                    raise RuntimeError('RECOVERY_LIMIT_REACHED: target ' + target + ' has exhausted recovery attempts; return existing failure evidence')
                if attempt and not attempt.get('finished_at'):
                    attempt.update(outcome='superseded', finished_at=now())
                attempt = dict(id=str(uuid4()), started_at=now(), actions=[])
                budget['attempts'].append(attempt)
            attempt['actions'].append(dict(action=action, actor=actor, time=now()))
            if action == 'execute':
                attempt.update(finished_at=now(), outcome='execution_requested')
        self.store.mutate(update)

    def tool_datanet_feedback(self, actor, args):
        p = self.active(actor)
        blocker = text(args['task_blocker'], 'task_blocker')
        if not p or not p['queried']:
            raise ValueError('Query experience before reporting a blocker')
        if self.self_repair(actor) and len(p['attempts']) < p['max_attempts'] and not any(a['mode'] == 'self' for a in p['attempts']):
            raise ValueError('Attempt authorized self repair before reporting; use problem_attempt without experience_id')
        report = self.r.rpc('report_feedback', actor=actor, category=args['category'], **({'message': args['message']} if args.get('message') else {}))
        p.update(status='reported', feedback_id=report['id'], task_blocker=blocker, finished_at=now())
        self.save(actor)
        self.record_uses(p, False)
        diagnostics = self.r.plugins.get('capabilities/execution_records')
        if diagnostics:
            diagnostics.blocked(actor, report)
        self.r.emit('feedback/received', report=report)
        self.close_tools(actor)
        self.r.host('conclude')
        return dict(node_id=actor, error=report['message'])

    def unlock(self, actor):
        self.unlocked.add(actor)
        state = self.r.state(actor)
        if 'datanet_resolve_feedback' not in state['grant']['framework']:
            return
        state['channels'].add('datanet_resolve_feedback')
        self.r.load(actor, 'tool:datanet_resolve_feedback', self.r.resource(self.id, 'guides/datanet_resolve_feedback/AGENTS.md'))
        if self.self_repair(actor):
            self.r.load(actor, 'recovery_limits', self.r.resource(self.id, 'docs/RECOVERY_LIMITS.md'))
        self.r.refresh(actor)

    def feedback_received(self, report):
        manager = self.r.backend.agents.get(report['actor'], {}).get('manager_id')
        if manager:
            self.unlocked.add(manager)
        if manager in self.r.states:
            self.unlock(manager)
            if self.r.host('inspect', actor=manager)['status'] != 'idle':
                import json
                self.r.host('steer', actor=manager, text='下属任务已阻塞并停止。先判断对当前委托的影响；可汇总失败结果时正常汇报，不自动转成自身阻塞。需要时按授权处理：' + json.dumps(dict(node_id=report['actor'], error=report['message']), ensure_ascii=False))

    def tool_datanet_resolve_feedback(self, actor, p):
        target, action = p.get('target', actor), p['action']
        management = self.r.plugins['capabilities/tools_network_management']
        if target != actor and not self.r.rpc('check_feedback_owner', actor=actor, target=target)['allowed']:
            raise PermissionError('Not the manager of a reporting Agent')
        native = self.r.host('inspect', actor=target)
        if action != 'inspect' and native['status'] != 'idle':
            raise RuntimeError('Reporting Agent is busy')
        with management.lock:
            if target in management.locks:
                raise RuntimeError('Reporting Agent is busy')
            management.locks.add(target)
        try:
            state = self.r.state(target)
            if action == 'inspect':
                return dict(node_id=target, creator_node_id=self.r.backend.agents[target].get('creator_node_id'), toolboxes=state['grant']['names'], prompt=state['prompt'], feedback=self.latest(target))
            if action == 'update_prompt':
                return self.r.plugins['capabilities/agent_runtime'].update_prompt(actor, target, p['prompt'])
            if action == 'instruct':
                instruction = text(p.get('instruction'), 'instruction')
                if self.r.backend.agents[target]['kind'] == 'discussion':
                    self.r.plugins['capabilities/agent_runtime'].update_prompt(actor, target, state['prompt'] + '\n\n管理者补充职责：' + instruction)
                    return dict(node_id=target, status='clarified', next='继续调用datanet_discuss恢复该组')
                return self.r.plugins['capabilities/agent_runtime'].execute(actor, target, instruction, kind='retry')
            if not p.get('toolboxes'):
                raise ValueError('Toolboxes required')
            self.r.resolve(p['toolboxes'], self.r.allowed)
            grant = self.r.resolve(list(dict.fromkeys(state['grant']['names'] + p['toolboxes'])), role='discussion' if self.r.backend.agents[target]['kind'] == 'discussion' else state['role'])
            if grant['official']['skills'] != state['grant']['official']['skills'] or grant['official']['skillProviders'] != state['grant']['official']['skillProviders']:
                raise ValueError('Runtime official Skill grant changes are not supported; tools can be added')
            self.reserve(actor, target, 'add_toolboxes')
            result = self.r.host('capabilities', actor=target, grant=grant)
            state['grant'] = grant
            self.r.rpc('agent_progress', target=target, toolboxes=grant['names'], reuse_eligible=False)
            self.r.refresh(target)
            return dict(node_id=target, status='updated', context_preserved=True, toolboxes=grant['names'], unavailable_tools=result.get('unavailableTools', []))
        finally:
            with management.lock:
                management.locks.remove(target)

    def tool_datanet_recovery_status(self, actor, p):
        self.r.load(actor, 'tool:datanet_recovery_status', self.r.resource(self.id, 'guides/datanet_recovery_status/AGENTS.md'))
        status = self.r.rpc('recovery_info')
        status['feedback'] = [dict(node_id=f['actor'], error=f['message']) for f in status.get('feedback', [])]
        fields = ('session_id', 'kind', 'toolboxes', 'manager_id', 'managed_ids', 'creator_node_id', 'activity', 'count')
        status['agents'] = {actor: {field: b.get(field) for field in fields} for actor, b in status['agents'].items()}
        status.update(mounted_agents=[actor for actor in self.r.states if actor != 'root'], recovery_budgets=[dict(target=b['target'], status=b['status'], attempt_count=len(b['attempts']), max_attempts=b['max_attempts'], remaining_attempts=max(0, b['max_attempts'] - len(b['attempts']))) for b in self.store.data.get('recovery_budgets', []) if b['source'] == str(self.r.directory)], errors=self.r.errors)
        return status
