from uuid import uuid4
from datanet.core.application import Component
from datanet.core.state_store import JsonStore
from datanet.core.record_values import now, uuid7, redact

def report_text(messages):
    final = next((m for m in reversed(messages) if m.get('role') == 'assistant'), {})
    return '\n'.join(c['text'] for c in final.get('content', []) if c.get('type') == 'text')


class Plugin(Component):
    def install(self):
        self.store = JsonStore(self.r.directory / 'execution-records/state.json', dict(incidents=[], runs=[]))
        self.running, self.starts, self.failed, self.last_failure, self.last_completed = {}, {}, set(), {}, {}
        self.on('agent/pre-step', lambda e: self.start(e['actor'], e.get('messages')))
        self.on('agent/error', lambda e: self.exception(e['actor'], e['error'], 'agent_error'))
        self.on('agent/status', self.idle)
        self.on('tool/result', self.result)
        self.on('tool/error', lambda e: self.last_failure.update({e['actor']: dict(tool=e['name'], error=redact(e['error']), time=now())}))
        def recover(db):
            for run in db['runs']:
                if run['source'] == str(self.r.directory) and run['status'] == 'running':
                    run.update(status='interrupted', finished_at=now())
                    if not any(i.get('run_id') == run['id'] for i in db['incidents']):
                        db['incidents'].append(dict(**{k: v for k, v in run.items() if k not in ('id', 'status')}, id=str(uuid4()), type='execution_exception', category='interrupted', status='unresolved', message='上次执行中断，结果未确认', run_id=run['id'], created_at=now()))
        self.store.mutate(recover)

    def start(self, actor, messages=None):
        if actor in self.running:
            return
        messages = messages if messages is not None else self.r.host('messages', actor=actor)
        run = dict(id=uuid7(), **self.r.metadata(actor), source=str(self.r.directory), status='running', started_at=now())
        self.running[actor] = run
        self.starts[actor] = len(messages)
        self.failed.discard(actor)
        self.last_failure.pop(actor, None)
        self.last_completed.pop(actor, None)
        self.store.mutate(lambda db: db['runs'].append(run))
        reports = self.r.plugins.get('tools/reports')
        if reports:
            task = next((m for m in reversed(messages) if m.get('role') == 'user'), {})
            task = '\n'.join(c.get('text', '') for c in task.get('content', []) if c.get('type') == 'text')
            reports.start(actor, run['id'], task)

    def finish(self, actor, status, summary):
        run = self.running.pop(actor, None)
        if run:
            def update(db):
                stored = next(r for r in db['runs'] if r['id'] == run['id'])
                if stored['status'] == 'running':
                    stored.update(status=status, finished_at=now(), summary=redact(summary))
            self.store.mutate(update)
        return run

    def complete(self, actor, messages):
        if actor in self.failed:
            raise RuntimeError('Agent execution failed')
        summary = report_text(messages)
        run = self.finish(actor, 'completed', summary or '委托正常结束，无新增阻塞')
        reports = self.r.plugins.get('tools/reports')
        if reports:
            reports.finish(actor, 'completed', summary, messages=messages)
        if run:
            self.last_completed[actor] = run['id']
        return self.last_completed.get(actor)

    def incident(self, actor, type, message, **extra):
        item = dict(id=str(uuid4()), type=type, status='unresolved', **self.r.metadata(actor), source=str(self.r.directory), version='0.3.0', created_at=now(), message=redact(message), last_failure=self.last_failure.get(actor), **extra)
        def record(db):
            if extra.get('feedback_id') and any(i.get('feedback_id') == extra['feedback_id'] for i in db['incidents']):
                return
            db['incidents'].append(item)
        self.store.mutate(record)

    def blocked(self, actor, report):
        run = self.running.get(actor)
        self.failed.add(actor)
        self.incident(actor, 'blocked', report['message'], feedback_id=report['id'], category=report['category'], run_id=(run or {}).get('id'))
        self.finish(actor, 'blocked', report['message'])
        reports = self.r.plugins.get('tools/reports')
        if reports:
            reports.finish(actor, 'blocked', error=report['message'], messages=self.r.host('messages', actor=actor)[self.starts.get(actor, 0):])

    def exception(self, actor, error, category='execution_error'):
        self.failed.add(actor)
        run = self.running.get(actor)
        if run:
            self.incident(actor, 'execution_exception', error, category=category, run_id=run['id'])
            self.finish(actor, 'failed', error)
            reports = self.r.plugins.get('tools/reports')
            if reports:
                reports.finish(actor, 'failed', error=error, messages=self.r.host('messages', actor=actor)[self.starts.get(actor, 0):])

    def result(self, e):
        result = e['result']
        value = result.get('value') or {}
        if '[DATANET_TOOL_PERMISSION_DENIED]' not in str(result) and (result.get('isError') or isinstance(value, dict) and (value.get('status') in ('error', 'forbidden') or value.get('exitCode', value.get('exit_code', 0)) != 0)):
            self.last_failure[e['actor']] = dict(tool=e['name'], call_id=e.get('call_id'), error=redact(str(result)), time=now())
        reports = self.r.plugins.get('tools/reports')
        if reports:
            reports.record(e['actor'], e)

    def idle(self, e):
        actor = e['actor']
        if e['status'] != 'idle' or actor not in self.running or self.r.state(actor).get('scheduled'):
            return
        messages = e['messages'][self.starts.get(actor, 0):]
        try:
            problem = self.r.plugins.get('toolboxes/problem_handling')
            if problem:
                problem.assert_closed(actor)
            if not report_text(messages).strip():
                raise RuntimeError('执行停止，未得到完成结果')
            self.complete(actor, messages)
        except Exception as error:
            self.exception(actor, str(error), 'stopped')
            if problem:
                problem.interrupt(actor, str(error))
        self.r.rpc('agent_progress', target=actor, activity='blocked' if actor in self.failed else 'idle')

    def tool_incident_query(self, actor, p):
        status = p.get('status', 'all')
        words = p.get('query', '').lower().split()
        records = [i for i in self.store.data['incidents'] if (status == 'all' or i['status'] == status) and (not p.get('node_id') or i['node_id'] == p['node_id']) and all(w in str(i).lower() for w in words)]
        offset, limit = p.get('offset', 0), p.get('limit', 6)
        return dict(incidents=records[offset:offset + limit], retry_runs=[run for run in self.store.data['runs'] if run['source'] == str(self.r.directory) and (not p.get('node_id') or run['node_id'] == p['node_id'])][-limit:])

    def tool_incident_resolve(self, actor, p):
        if not isinstance(p['evidence'], str) or not p['evidence'].strip() or len(p['evidence']) > 1000:
            raise ValueError('Resolution evidence requires 1-1000 characters')
        if p.get('experience_id'):
            experience = self.r.plugins.get('toolboxes/experience')
            if not experience or not experience.query(dict(ids=[p['experience_id']])):
                raise ValueError('Linked experience must be pending or verified')
        def resolve(db):
            incident = next(i for i in db['incidents'] if i['id'] == p['id'])
            manager = self.r.backend.agents[incident['node_id']].get('manager_id')
            if actor not in (incident['node_id'], manager) and 'experience_review' not in self.r.state(actor)['grant']['framework']:
                raise PermissionError('Only reporter, manager or authorized maintainer may resolve')
            run = next((r for r in db['runs'] if r['id'] == p['retry_run_id']), None)
            if incident['status'] != 'unresolved' or not run or run['node_id'] != incident['node_id'] or run['source'] != incident['source'] or run['status'] != 'completed' or run['started_at'] < incident['created_at']:
                raise ValueError('A completed retry after this incident is required')
            incident.update(status='resolved', resolved_by=actor, resolved_at=now(), retry_run_id=p['retry_run_id'], evidence=p['evidence'])
            if p.get('experience_id'):
                incident['experience_id'] = p['experience_id']
            return dict(id=p['id'], status='resolved', retry_run_id=p['retry_run_id'], incident=incident)
        result = self.store.mutate(resolve)
        incident = result.pop('incident')
        if incident.get('feedback_id'):
            problem = self.r.plugins.get('toolboxes/problem_handling')
            if problem:
                def budgets(db):
                    for b in db.get('recovery_budgets', []):
                        if b['target'] == incident['node_id'] and b['status'] == 'unresolved' and b['feedback_ids'][-1] == incident['feedback_id']:
                            b.update(status='resolved', finished_at=now())
                problem.store.mutate(budgets)
        return result
