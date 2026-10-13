from copy import deepcopy
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json, os
from datanet.core.application import Component
from datanet.core.record_values import now, uuid7, redact
from datanet.core.storage_paths import storage_path

def schema(props=None, required=None):
    return dict(type='object', properties=props or {}, required=required or [], additionalProperties=False)


class Plugin(Component):
    def install(self):
        self.directory = storage_path(self.r.directory / 'reports')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.requests, self.contexts, self.lock = {}, {}, RLock()
        for file in self.directory.glob('*/manifest.json'):
            q = json.loads(file.read_text(encoding='utf-8'))
            self.requests[q['root_request_id']] = q
            for d in q['delegations'].values():
                if d['status'] == 'running':
                    d.update(status='interrupted', finished_at=now())
                for run in d['runs']:
                    if run['status'] == 'running':
                        run.update(status='interrupted', finished_at=now(), error='宿主重启，执行结果未确认')
                        self.atomic(q, run['files']['metadata'], run)
                self.atomic(q, d['path'] + '/delegation.json', d)
            self.persist(q)
        self.on('agent/bound', self.bound)

    def atomic(self, q, relative, value):
        file = self.directory / q['root_request_id'] / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        temp = file.with_name(file.name + '.' + uuid4().hex + '.tmp')
        temp.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(file)

    def descendant(self, q, delegation, ancestor):
        current = q['delegations'].get(delegation)
        while current:
            if current['delegation_id'] == ancestor:
                return True
            current = q['delegations'].get(current['parent_delegation_id'])
        return False

    def allowed(self, q, d, actor):
        return d['target_node_id'] == actor or any(p['caller_node_id'] == actor and self.descendant(q, d['delegation_id'], p['delegation_id']) for p in q['delegations'].values()) or any(g['actor'] == actor and self.descendant(q, d['delegation_id'], g['delegation_id']) for g in q.get('archive_grants', []))

    def listing(self, d):
        return {**{k: deepcopy(v) for k, v in d.items() if k != 'task'}, 'task_preview': d['task'][:160], 'delegation_path': d['path'] + '/delegation.json'}

    def index(self, q, actor=None):
        nodes = {}
        for d in q['delegations'].values():
            if d['kind'] != 'discussion' and (actor is None or self.allowed(q, d, actor)):
                nodes.setdefault(d['target_node_id'], []).append(self.listing(d))
        return dict(version=1, root_request_id=q['root_request_id'], nodes=nodes)

    def topology(self, q, actor=None):
        entries = []
        for d in q['delegations'].values():
            if actor is None or self.allowed(q, d, actor):
                item = self.listing(d)
                item['run_ids'] = [run['run_id'] for run in item.pop('runs')]
                entries.append(item)
        return dict(version=1, root_request_id=q['root_request_id'], delegations=entries)

    def persist(self, q):
        self.atomic(q, 'manifest.json', q)
        self.atomic(q, 'node-index.json', self.index(q))
        self.atomic(q, 'topology.json', self.topology(q))

    def current(self, actor):
        c = self.contexts.get(actor)
        q = self.requests.get(c['root_request_id']) if c else None
        d = q['delegations'].get(c['delegation_id']) if q else None
        run = next((run for run in d['runs'] if run['run_id'] == c.get('run_id')), None) if d else None
        return c, q, d, run

    def bound(self, e):
        actor, session = e['actor'], self.r.state(e['actor'])['session_id']
        latest = None
        for q in self.requests.values():
            for d in q['delegations'].values():
                if d['target_node_id'] == actor:
                    for run in d['runs']:
                        if run['session_id'] == session and (latest is None or run['started_at'] >= latest[0]):
                            latest = (run['started_at'], dict(root_request_id=q['root_request_id'], delegation_id=d['delegation_id'], run_id=run['run_id']))
        if latest:
            self.contexts[actor] = latest[1]
        if any(d['caller_node_id'] == actor and d['kind'] != 'request' for q in self.requests.values() for d in q['delegations'].values()) or any(g['actor'] == actor for q in self.requests.values() for g in q.get('archive_grants', [])):
            self.unlock(actor)

    def unlock(self, actor):
        self.r.state(actor)['dynamic']['datanet_reports_channel'] = dict(owner=self.id, name='datanet_reports_channel', description='查询你发起的委托或获准归档范围内的报告。进入后加载报告结构、索引用法和专用读取工具；这是普通查询入口，不启动排障或重试。', parameters=schema({'root_request_id': {'type': 'string'}, 'delegation_id': {'type': 'string'}}))
        self.r.refresh(actor)

    def start(self, actor, run_id, task=''):
        with self.lock:
            c, q, d, previous = self.current(actor)
            if d is None or (previous and previous['status'] != 'running'):
                root_id, delegation = uuid7(), uuid7()
                q = dict(version=1, root_request_id=root_id, created_at=now(), origin_node_id=actor, delegations={}, archive_grants=[])
                d = dict(delegation_id=delegation, parent_delegation_id=None, caller_run_id=None, caller_node_id=actor, target_node_id=actor, sequence=1, kind='request', task=redact(task or ''), created_at=now(), status='running', path='delegations/001_' + delegation, runs=[])
                q['delegations'][delegation] = d
                self.requests[root_id] = q
                c = dict(root_request_id=root_id, delegation_id=delegation)
            base = d['path'] + '/runs/' + run_id
            run = dict(run_id=run_id, node_id=actor, session_id=self.r.state(actor)['session_id'], status='running', started_at=now(), files=dict(metadata=base + '/metadata.json', tools=base + '/tools.jsonl', transcript=base + '/transcript.jsonl'), tool_sequence=0)
            d['runs'].append(run)
            d['status'] = 'running'
            self.contexts[actor] = {**c, 'run_id': run_id}
            for name in ('tools', 'transcript'):
                file = self.directory / q['root_request_id'] / run['files'][name]
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('', encoding='utf-8')
            self.atomic(q, run['files']['metadata'], run)
            self.atomic(q, d['path'] + '/delegation.json', d)
            self.persist(q)
            return self.reference(actor)

    def delegate(self, actor, target, task, kind='agent', parent=None, round=None, activate=True):
        with self.lock:
            c, q, caller, run = self.current(actor)
            if c is None:
                self.start(actor, uuid7(), task)
                c, q, caller, run = self.current(actor)
            parent_id = (parent or {}).get('delegation_id', c['delegation_id'])
            p = q['delegations'][parent_id]
            sequence = 1 + sum(d['parent_delegation_id'] == parent_id for d in q['delegations'].values())
            id = uuid7()
            d = dict(delegation_id=id, parent_delegation_id=parent_id, caller_run_id=c.get('run_id'), caller_node_id=actor, target_node_id=target, sequence=sequence, kind=kind, task=redact(task), created_at=now(), status='running', path=p['path'] + '/children/' + f'{sequence:03d}_' + id, runs=[])
            previous = self.current(target)[3]
            if previous and previous['status'] in ('failed', 'blocked', 'interrupted'):
                d['retry_of'] = previous['run_id']
            if round:
                d['round'] = round
            q['delegations'][id] = d
            result = dict(root_request_id=q['root_request_id'], delegation_id=id)
            if activate and target in self.r.states:
                self.contexts[target] = result
            self.atomic(q, d['path'] + '/delegation.json', d)
            self.persist(q)
        self.unlock(actor)
        return result

    def reference(self, actor):
        c, q, d, run = self.current(actor)
        return {**c, **({'files': deepcopy(run['files'])} if run else {})} if c else None

    def record(self, actor, event):
        with self.lock:
            c, q, d, run = self.current(actor)
            if not run:
                return
            run['tool_sequence'] += 1
            file = self.directory / q['root_request_id'] / run['files']['tools']
            with file.open('a', encoding='utf-8') as output:
                output.write(json.dumps(redact(dict(sequence=run['tool_sequence'], time=now(), call_id=event.get('call_id'), tool=event['name'], arguments=event.get('arguments', {}), result=event['result'])), ensure_ascii=False) + '\n')

    def artifact(self, actor, content, submission=False):
        with self.lock:
            c, q, d, run = self.current(actor)
            if not run:
                return
            key = 'submission' if submission else 'output'
            relative = d['path'] + '/runs/' + run['run_id'] + ('/submission.json' if submission else '/artifacts/output.md')
            run['files'][key] = relative
            if submission:
                self.atomic(q, relative, content)
            else:
                file = self.directory / q['root_request_id'] / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(redact(content), encoding='utf-8')
            self.persist(q)

    def finish(self, actor, status, report='', error=None, messages=None):
        with self.lock:
            c, q, d, run = self.current(actor)
            if not run or run['status'] != 'running':
                return
            run.update(status=status, finished_at=now())
            base = d['path'] + '/runs/' + run['run_id']
            if status == 'completed' and report.strip():
                run['files']['report'] = base + '/report.md'
                (self.directory / q['root_request_id'] / run['files']['report']).write_text(redact(report), encoding='utf-8')
            if error:
                run.update(error=redact(error))
                run['files']['error'] = base + '/error.json'
                self.atomic(q, run['files']['error'], dict(status=status, error=run['error']))
            (self.directory / q['root_request_id'] / run['files']['transcript']).write_text(''.join(json.dumps(redact(m), ensure_ascii=False) + '\n' for m in messages or []), encoding='utf-8')
            d.update(status=status, finished_at=run['finished_at'])
            self.atomic(q, run['files']['metadata'], run)
            self.atomic(q, d['path'] + '/delegation.json', d)
            self.persist(q)

    def end(self, reference, status, error=None):
        with self.lock:
            q = self.requests[reference['root_request_id']]
            d = q['delegations'][reference['delegation_id']]
            d.update(status=status, finished_at=now())
            if error:
                d['error'] = redact(error)
            self.atomic(q, d['path'] + '/delegation.json', d)
            self.persist(q)

    def archive(self, actor, reference):
        with self.lock:
            q = self.requests[reference['root_request_id']]
            grant = dict(actor=actor, delegation_id=reference['delegation_id'])
            if grant not in q['archive_grants']:
                q['archive_grants'].append(grant)
                self.persist(q)
        self.unlock(actor)

    def tool_datanet_reports_channel(self, actor, p):
        dynamic = self.r.state(actor)['dynamic']
        string, offset = {'type': 'string', 'minLength': 1}, {'type': 'integer', 'minimum': 0}
        dynamic['datanet_reports_query'] = dict(owner=self.id, name='datanet_reports_query', description='按请求、委托或节点查询获授权报告索引及实际委托拓扑，返回可直接读取的相对路径；不返回报告正文。省略请求和委托时查询当前请求。', parameters=schema(dict(root_request_id=string, delegation_id=string, node_id=string, offset=offset, limit={'type': 'integer', 'minimum': 1, 'maximum': 50})))
        dynamic['datanet_report_read'] = dict(owner=self.id, name='datanet_report_read', description='按索引路径读取获授权报告文件，或读取按权限过滤的 node-index.json、topology.json。长文件按字符分页；路径不扩大权限。', parameters=schema(dict(root_request_id=string, path=string, offset=offset, limit={'type': 'integer', 'minimum': 1, 'maximum': 20000}), ['root_request_id', 'path']))
        self.r.refresh(actor)
        current = self.contexts.get(actor, {})
        return dict(tools=['datanet_reports_query', 'datanet_report_read'], instructions_added=self.r.load(actor, 'tool:datanet_reports', self.r.resource(self.id, 'guides/datanet_reports/AGENTS.md')), root_request_id=p.get('root_request_id', current.get('root_request_id')), indices=['node-index.json', 'topology.json'])

    def tool_datanet_reports_query(self, actor, p):
        with self.lock:
            request = p.get('root_request_id', None if p.get('delegation_id') else self.contexts.get(actor, {}).get('root_request_id'))
            items = []
            for q in self.requests.values():
                if request and q['root_request_id'] != request:
                    continue
                for d in q['delegations'].values():
                    if not self.allowed(q, d, actor) or (p.get('delegation_id') and not self.descendant(q, d['delegation_id'], p['delegation_id'])) or (p.get('node_id') and d['target_node_id'] != p['node_id']):
                        continue
                    items.append(dict(root_request_id=q['root_request_id'], **self.listing(d)))
            items.sort(key=lambda d: (d['created_at'], d['sequence']))
            offset, limit = p.get('offset', 0), p.get('limit', 20)
            return dict(items=items[offset:offset + limit], offset=offset, total=len(items), has_more=offset + limit < len(items), next_offset=offset + limit if offset + limit < len(items) else None)

    def tool_datanet_report_read(self, actor, p):
        with self.lock:
            q = self.requests[p['root_request_id']]
            relative = p['path']
            if '\\' in relative or Path(relative).is_absolute() or any(part in ('', '.', '..') for part in relative.split('/')):
                raise ValueError('Invalid report path')
            if relative in ('node-index.json', 'topology.json'):
                if not any(self.allowed(q, d, actor) for d in q['delegations'].values()):
                    raise PermissionError('Report request is outside grant')
                content = json.dumps(self.index(q, actor) if relative == 'node-index.json' else self.topology(q, actor), ensure_ascii=False, indent=2)
            else:
                owner = next((d for d in q['delegations'].values() if relative == d['path'] + '/delegation.json' or any(relative in run['files'].values() for run in d['runs'])), None)
                if owner is None or not self.allowed(q, owner, actor):
                    raise PermissionError('Report file is outside delegated or archive grant')
                base = (self.directory / q['root_request_id']).resolve()
                file = (base / relative).resolve()
                if not file.is_relative_to(base):
                    raise PermissionError('Report file escapes request directory')
                content = redact(file.read_text(encoding='utf-8'))
            offset, limit = p.get('offset', 0), p.get('limit', 12000)
            return dict(root_request_id=q['root_request_id'], path=relative, offset=offset, content=content[offset:offset + limit], total_characters=len(content), has_more=offset + limit < len(content), next_offset=offset + limit if offset + limit < len(content) else None)
