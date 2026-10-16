"""Reusable Agent mounting and execution; no network creation tools."""
from pathlib import Path
from uuid import uuid4
from datanet.core.application import Component

class Plugin(Component):
    def install(self):
        self.on('agent/bound', lambda e: self.memory_tools(e['actor']))

    def memory_tools(self, actor):
        for name, description, parameters in (
            ('datanet_memory_read', '读取自己的个人记忆文件。', {'type': 'object', 'properties': {}, 'additionalProperties': False}),
            ('datanet_memory_write', '更新自己的个人记忆文件；保留值得复用的经验和关键信息。', {'type': 'object', 'properties': {'content': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['replace', 'append'], 'default': 'replace'}}, 'required': ['content'], 'additionalProperties': False}),
        ):
            self.r.state(actor)['dynamic'][name] = dict(owner=self.id, name=name, description=description, parameters=parameters)


    def manages(self, actor, target, scope='self'):
        if actor == target:
            return True
        if scope == 'self':
            return False
        bindings = self.r.backend.agents
        current = bindings.get(target, {}).get('manager_id')
        if scope == 'children':
            return current == actor
        seen = set()
        while current and current not in seen:
            if current == actor:
                return True
            seen.add(current)
            current = bindings.get(current, {}).get('manager_id')
        return False


    def create(self, target, prompt, parent, strength=2, boxes=None, role=None, binding=None, allowed_toolboxes=None, resume=None):
        r = self.r
        if binding is None and target in r.states:
            raise ValueError('Node already has an Agent')
        r.rpc('ensure_agent_node', target=target)
        grant = r.resolve(boxes if boxes is not None else r.config.get('defaultAgentToolboxes', r.defaults.get('toolboxes', [])), None if binding else r.allowed if allowed_toolboxes is None else allowed_toolboxes, r.defaults.get('roleKinds', {}).get(role, role))
        path = r.directory / 'agents' / (target.encode().hex() + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding='utf-8')
        options = r.host('inspect', actor=parent).get('options', {})
        options = {k: options[k] for k in ('provider', 'model', 'maxTokens', 'reasoningEffort') if k in options}
        if r.config.get('provider'):
            options.update(provider=r.config['provider'], model=r.config.get('model'))
        options['maxTokens'] = r.config.get('agentMaxTokens', options.get('maxTokens', 4096))
        lifecycle = r.plugins.get('capabilities/agent_lifecycle')
        reused = False
        key = None
        if binding is None and lifecycle:
            key, claim = lifecycle.claim(target, dict(prompt=prompt, toolboxes=sorted(grant['names']), strength=float(strength), role=role, agentOptions=options, node_options=r.backend.network.nodes[target].creation_options))
            if claim['reused']:
                target, binding, reused = claim['node_id'], claim['binding'], True
                path = r.directory / 'agents' / (target.encode().hex() + '.md')
                path.write_text(prompt, encoding='utf-8')
        saved = {**(binding or {}), 'session_id': (binding or {}).get('session_id', 'datanet-' + str(uuid4())), 'kind': (binding or {}).get('kind', r.backend.agents.get(target, {}).get('kind', 'generic')), 'creator_node_id': (binding or {}).get('creator_node_id', parent), 'prompt': prompt, 'promptPath': str(path), 'toolboxes': grant['names'], 'maxStrength': strength, 'role': role, 'agentOptions': (binding or {}).get('agentOptions', options), 'status': (binding or {}).get('status', 'prepared')}
        saved.pop('target', None)
        saved['native_parent_id'] = parent
        if role in r.defaults.get('roleKinds', {}):
            saved['kind'] = r.defaults['roleKinds'][role]
        if binding is None or reused:
            saved.update(manager_id=parent, creator_node_id=parent, reuse_key=key, reuse_eligible=True)
        r.rpc('bind_agent', target=target, **saved)
        mounted = r.host('create', actor=target, parent=parent, grant=grant, binding=r.backend.agents[target], resume=binding is not None if resume is None else resume)
        r.rpc('agent_progress', target=target, status='ready', activity='interrupted' if saved.get('activity') == 'running' else 'idle')
        r.bind(target, mounted['session_id'], role, grant, prompt)
        r.host('view-update', actor=target, view=r.view(target))
        if reused:
            r.state(target)['pending_task_boundary'] = '你已被重新装配。管理者：' + parent + '。个人记忆和会话已保留，当前任务以新的委托为准。'
        return dict(node_id=target, reused=reused, memory_path=str(r.backend.network.nodes[target].file_path), manager_id=r.backend.agents[target].get('manager_id'), creator_node_id=saved['creator_node_id'], session_id=mounted['session_id'], prompt_path=str(path), toolboxes=grant['names'])


    def tool_datanet_memory_read(self, actor, p):
        return self.r.backend.network.nodes[actor].read_memory()


    def tool_datanet_memory_write(self, actor, p):
        result = self.r.backend.network.nodes[actor].write_memory(p['content'], p.get('mode', 'replace'))
        self.r.rpc('save')
        return result


    def reserve(self, actor, target, action):
        problem = self.r.plugins.get('capabilities/problem_handling')
        if problem:
            problem.reserve(actor, target, action)


    def execute(self, actor, target, task, kind='agent', parent=None, round=None, reference=None, asynchronous=False, timeout_ms=None):
        r = self.r
        if target not in r.states:
            raise ValueError('Node has no mounted Agent')
        if r.host('inspect', actor=target)['status'] != 'idle':
            raise RuntimeError('Agent is already busy')
        self.reserve(actor, target, 'execute')
        reports = r.plugins.get('capabilities/reports')
        diagnostics = r.plugins.get('capabilities/execution_records')
        if diagnostics and not asynchronous:
            diagnostics.start(actor)
        if reference and reports:
            reports.contexts[target] = reference
        else:
            reference = reports.delegate(actor, target, task, kind, parent, round) if reports else None
        problem = r.plugins.get('capabilities/problem_handling')
        previous = problem.latest(target) if problem else None
        r.state(target)['scheduled'] = True
        try:
            if diagnostics:
                diagnostics.start(target)
            boundary = r.state(target).pop('pending_task_boundary', '')
            response = r.host('run', actor=target, text=(boundary + '\n' if boundary else '') + task, timeout_ms=timeout_ms or r.config.get('turnTimeoutMs', 180000))
            if response.get('completion') != 'completed':
                raise RuntimeError('Host did not confirm normal Agent completion')
            feedback = problem.latest(target) if problem else None
            blocked = feedback and feedback.get('id') != (previous or {}).get('id')
            if not blocked:
                if problem:
                    problem.assert_closed(target)
                if diagnostics:
                    diagnostics.complete(target, response['messages'])
            return dict(status='blocked' if blocked else 'ok', session_id=response['session_id'], message=next((m for m in reversed(response['messages']) if m['role'] == 'assistant'), None), report_reference=reports.reference(target) if reports else None,
                        **({'feedback': dict(node_id=feedback['actor'], error=feedback['message'])} if blocked else {'retry_run_id': diagnostics.last_completed.get(target) if diagnostics else None}))
        except Exception as error:
            if diagnostics:
                diagnostics.exception(target, str(error))
            if problem:
                problem.interrupt(target, str(error))
            raise
        finally:
            r.state(target)['scheduled'] = False
            r.rpc('agent_progress', target=target, activity='blocked' if problem and problem.latest(target) != previous else 'idle')


    def update_prompt(self, actor, target, prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Prompt required')
        self.reserve(actor, target, 'update_prompt')
        state = self.r.state(target)
        path = Path(self.r.backend.agents[target]['promptPath'])
        path.with_suffix(path.suffix + '.bak').write_text(state['prompt'], encoding='utf-8')
        path.write_text(prompt, encoding='utf-8')
        state['prompt'] = prompt
        self.r.rpc('agent_progress', target=target, prompt=prompt, reuse_eligible=False)
        self.r.host('view-update', actor=target, view=self.r.view(target))
        return dict(node_id=target, updated=True, context_preserved=True)


