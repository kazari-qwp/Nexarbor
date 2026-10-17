"""Optional local workbench. Editing reuses core snapshots and mounted components."""
import asyncio
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock, Thread
import inspect
import json
import tempfile
import time
import uuid

from datanet.core.application import Component, Application
from datanet.core.backend import Backend
from datanet.core.pulse_node import PulseNode
from datanet.core.serialization import _build
from .documents import link, portable, preset, refresh_map, resource, safe_document, template


class ValidationPort:
    """No model, process or native session activation during configuration checks."""
    def __call__(self, operation, p):
        if operation == 'inspect': return dict(status='idle', options={})
        if operation == 'create': return dict(session_id=p['binding']['session_id'])
        if operation in ('tools', 'view-update', 'input-message', 'capabilities', 'dispose-agent'): return {}
        if operation in ('load-document', 'document-present'): return False
        raise RuntimeError('配置校验不能执行宿主操作：' + operation)


class Plugin(Component):
    def install(self):
        self.lock = RLock()
        self.stop_requested = Event()
        self.job = dict(status='idle', completed=0, requested=0, reports=[])
        self.job_thread = None
        self.path = self.r.directory / 'editor-draft.json'
        self.draft = json.loads(self.path.read_text('utf-8')) if self.path.exists() else None
        self.readonly = False
        self.on('session/root', self.root)

    def root(self, event):
        self.r.rpc('bind_agent', target='root', session_id=event['session_id'], kind='root', manager_id=None, creator_node_id=None)
        event['view'] = self.r.bind('root', event['session_id'], grant=self.r.resolve([]))
        self.r.backend.modules.bind(self.r)

    def catalog(self):
        b = self.r.backend
        modules = {}
        for key in b.components.order:
            manifest = b.components.catalog[key]
            file = manifest.get('editor', {}).get('modules')
            if key in b.components.enabled and file:
                for name, spec in json.loads(resource(b.components.catalog, key, file)).items():
                    if name not in b.components.module_types: continue
                    factory = b.components.module_types[name]
                    methods = [n for n, fn in inspect.getmembers(factory, inspect.isfunction)
                               if not n.startswith('_') and n not in ('bind', 'close', 'install', 'unmount', 'listen', 'tool')]
                    modules[name] = dict(spec, owner=key, methods=methods)
        return dict(modules=modules,
                    components=[dict(id=k, kind=m['kind'], description=m.get('description', ''), enabled=k in b.components.enabled,
                                     requires=m.get('requires', [])) for k, m in b.components.catalog.items()],
                    presets=[dict(id=k, name=m.get('preset', k), description=m.get('description', ''))
                             for k, m in b.components.catalog.items() if k in b.components.enabled and m.get('initialNetwork')],
                    nodeTypes=['node', 'agent', 'text_file', 'pulse'])

    def current(self):
        b = self.r.backend
        with b._transaction_lock:
            doc = portable(b.snapshot())
            return dict(document=doc, commit=b.store.stats()['commit_id'],
                        sessions={k: dict(session_id=v.get('session_id'), name=b.network.nodes[k].name)
                                  for k, v in b.agents.items() if k in b.network.nodes},
                        metadata={k: b.network.get_metadata(k) for k in b.network.nodes})

    def state(self):
        return dict(live=self.current(), draft=self.draft, job=deepcopy(self.job), readonly=self.readonly,
                    mode=self.r.config.get('editor', {}).get('mode', 'Harness'))

    def idle(self):
        if self.job_thread and self.job_thread.is_alive(): raise RuntimeError('请等待当前时刻结束并暂停，再修改运行网络')
        for actor in self.r.states:
            status = self.r.host('inspect', actor=actor)
            if status.get('status') != 'idle' or status.get('pending_messages', 0):
                raise RuntimeError('Agent 正在执行，请先停止：' + actor)
        if any(getattr(n, '_running', False) for n in self.r.backend.network.nodes.values()):
            raise RuntimeError('信号仍在传播')
        executor = self.r.plugins.get('capabilities/module_execution')
        if executor and (executor.running or executor.workers):
            raise RuntimeError('模块执行仍在完成或停止，请稍后再试')

    def validate(self, document):
        from jsonschema import Draft202012Validator, FormatChecker
        b = self.r.backend
        try:
            doc = safe_document(document, b.components.catalog, b.components.enabled)
            ids = {n['node_id'] for n in doc['network']['nodes']}
            formats = FormatChecker()
            @formats.checks('node-id')
            def node_id(value): return not isinstance(value, str) or value in ids or '{{' in value
            schemas = self.catalog()['modules']
            errors = []
            for node in doc['network']['nodes']:
                for name, spec in node['modules'].items():
                    if name not in schemas:
                        errors.append(dict(path=node['node_id'] + '/' + name, message='此模块尚未提供编辑器配置定义'))
                        continue
                    for field, schema in [('config', 'schema'), ('state', 'stateSchema')]:
                        for error in Draft202012Validator(schemas[name][schema], format_checker=formats).iter_errors(spec[field]):
                            errors.append(dict(path=node['node_id'] + '/' + name + '/' + field + '/' + '/'.join(map(str, error.path)), message=error.message))
            if errors: return dict(valid=False, errors=errors[:40], warnings=[])
            # Build/bind in a disposable store using the same loaded component services.
            # Session operations terminate in ValidationPort; no native Agent is created.
            with tempfile.TemporaryDirectory(prefix='editor-validation-', dir=b.directory) as folder:
                candidate = Backend(folder)
                app = None
                try:
                    candidate.restore(doc)
                    candidate.components.graph_loaded(candidate)
                    app = Application(candidate, ValidationPort(), {**self.r.config, 'rootNetwork': None, 'allowedAgentToolboxes': self.r.allowed})
                    app.bind_session('validation-root')
                    candidate.modules.bind(app)
                    # Exercise the current access/context assembly before accepting it.
                    for actor in app.states:
                        if actor != 'root': app.emit('context/prepare', actor=actor)
                    _build(doc['network'], Path(folder))
                finally:
                    candidate.modules.clear()
                    candidate.close()
            warnings = []
            pulses = [n for n in doc['network']['nodes'] if n['type'] == 'pulse']
            if not pulses: warnings.append('没有脉冲节点，仍可编辑；自动推进前需要添加时间循环。')
            return dict(valid=True, errors=[], warnings=warnings)
        except Exception as error:
            return dict(valid=False, errors=[dict(path='network', message=str(error))], warnings=[])

    def save_draft(self, p):
        expected = p.get('expected_version')
        version = self.draft['version'] if self.draft else 0
        if expected != version: raise ValueError('草稿已在其他窗口更新，请重新载入')
        document = safe_document(p['document'], self.r.catalog, self.r.enabled)
        data = dict(version=version + 1, document=document, layout=p.get('layout', {}), base_commit=p.get('base_commit'), applied=p.get('applied', False), updated_at=time.time())
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.draft = data
        return data

    def apply(self, p):
        self.idle()
        b = self.r.backend
        if p['base_commit'] != b.store.stats()['commit_id']: raise ValueError('运行网络已有变化，请重新载入后再应用，避免覆盖活动结果')
        check = self.validate(p['document'])
        if not check['valid']: return check
        doc = safe_document(p['document'], self.r.catalog, self.r.enabled)
        old = b.snapshot()
        root_state = deepcopy(self.r.states['root'])
        # Include native cursor capture before detaching nodes whenever available.
        # Existing bindings survive edits to their node; new identities get new sessions.
        ids = {n['node_id'] for n in doc['network']['nodes'] if n['type'] == 'agent'}
        if 'root' not in ids: raise ValueError('根节点必须是 Agent')
        for actor in set(b.agents) - ids:
            if actor in self.r.states: self.r.host('dispose-agent', actor=actor)
        doc['agents'] = {k: v for k, v in old['agents'].items() if k in ids}
        def mount(document):
            b.modules.clear()
            with b._transaction_lock:
                b.restore(document)
                b.components.graph_loaded(b)
            self.r.states.clear()
            self.r.bind('root', root_state['session_id'], root_state['role'], root_state['grant'], root_state['prompt'])
            b.modules.bind(self.r)
            for actor in self.r.states: self.r.host('view-update', actor=actor, view=self.r.view(actor))
            b.dispatch('save', {})
        try:
            mount(doc)
        except Exception as error:
            try: mount(old)
            except Exception as recovery:
                self.readonly = True
                raise RuntimeError('应用配置失败，自动恢复失败；请重启并恢复最近检查点：' + str(recovery)) from error
            raise RuntimeError('应用失败，已恢复原网络：' + str(error)) from error
        current = self.current()
        draft = self.save_draft(dict(document=current['document'], expected_version=self.draft['version'] if self.draft else 0,
                                    layout=p.get('layout', {}), base_commit=current['commit'], applied=True))
        return dict(valid=True, applied=True, draft=draft, **current)

    def view(self, p):
        b = self.r.backend
        actor = p['actor']; strength = p.get('strength', 2)
        if type(strength) not in (int, float) or not 0 <= strength <= 20: raise ValueError('访问强度范围0至20')
        with b._transaction_lock:
            if actor not in b.network.nodes: raise ValueError('节点尚未应用到运行网络')
            maximum = self.r.states.get(actor, {}).get('strength', strength)
            strength = min(strength, maximum)
            paths = {}
            for direction in ('read', 'write'):
                paths[direction] = [dict(id=n.node_id, path=path, remaining=remaining)
                                    for n, path, remaining in b.network.walk_states(actor, direction=direction, strength=strength)]
            return dict(actor=actor, paths=paths, strength=strength, max_strength=maximum, tools=self.r.definitions(actor) if actor in self.r.states else [],
                        metadata=b.network.get_metadata(actor))

    def start(self, p):
        self.idle()
        pulse_id = p['pulse']; cycles = p.get('cycles', 1); timeout = p.get('timeout', 120)
        if type(cycles) is not int or not 1 <= cycles <= 20: raise ValueError('每次最多运行20个时刻')
        if type(timeout) is not int or not 1 <= timeout <= 180: raise ValueError('单时刻时限1至180秒')
        pulse = self.r.backend.network.nodes[pulse_id]
        if not isinstance(pulse, PulseNode): raise ValueError('请选择脉冲节点')
        if pulse.state['phase'] == 'interrupted': raise ValueError('上次脉冲被中断，请先检查效果并明确确认恢复')
        self.stop_requested.clear()
        self.job = dict(id=uuid.uuid4().hex, status='running', completed=0, requested=cycles, pulse=pulse_id, reports=[], started_at=time.time())
        async def work():
            try:
                for _ in range(cycles):
                    if self.stop_requested.is_set(): break
                    report = await pulse.run(self.r.backend.signals, cycles=1, timeout_seconds=timeout, allow_partial=True)
                    self.job['reports'].append(report)
                    self.job['completed'] += 1
                    if report['status'] != 'completed': break
                self.job['status'] = 'paused' if self.stop_requested.is_set() else 'completed'
            except BaseException as error:
                self.job.update(status='failed', error=str(error) or type(error).__name__)
            finally:
                self.job['ended_at'] = time.time()
        self.job_thread = Thread(target=lambda: asyncio.run(work()), name='network-editor-pulse', daemon=True)
        self.job_thread.start()
        return deepcopy(self.job)

    def host_request(self, operation, p):
        # Pause can bypass a slow request lock, but never interrupts an in-flight tick.
        if operation == 'pause':
            self.stop_requested.set()
            return dict(pausing=self.job.get('status') == 'running')
        if operation == 'state': return self.state()
        with self.lock:
            if operation == 'catalog': return self.catalog()
            if operation == 'validate': return self.validate(p['document'])
            if operation == 'draft': return self.save_draft(p)
            if operation == 'preset': return preset(self.r.catalog, p['id'])
            if operation == 'template': return template(self.r.catalog, p['document'], p['kind'], p.get('options', {}))
            if operation == 'connect':
                doc = deepcopy(p['document']); link(doc, **p['connection']); return refresh_map(doc)
            if operation == 'map': return refresh_map(deepcopy(p['document']))
            if operation == 'view': return self.view(p)
            if operation == 'apply':
                if self.readonly: raise RuntimeError('运行网络处于只读恢复状态')
                return self.apply(p)
            if operation == 'run': return self.start(p)
            if operation == 'reconcile':
                self.idle(); node = self.r.backend.network.nodes[p['pulse']]
                node.reconcile(p['reason']); self.r.backend.dispatch('save', {}); return self.current()
            if operation == 'checkpoint':
                self.idle(); return self.r.backend.dispatch('save', {'full': True})
            if operation == 'points': return self.r.backend.dispatch('persistence_points', {})
            raise ValueError('未知编辑器操作：' + operation)

    def close(self):
        self.stop_requested.set()
        if self.job_thread and self.job_thread.is_alive(): self.job_thread.join(timeout=5)
