"""Agent creation, delegation and capability channels, independent of Harness."""
from pathlib import Path
from threading import Lock
from uuid import uuid4
import json
from datanet.core.application import Component

CHANNELS = {'datanet_create_node', 'datanet_create_agent', 'datanet_manage_agent', 'datanet_interfaces', 'datanet_create_network'}


class Plugin(Component):
    def install(self):
        self.locks = set()
        self.lock = Lock()
        self.guides = {m['preset']: self.r.resource(key, m['guide']) for key, m in self.r.catalog.items() if key in self.r.enabled and m.get('preset') and m.get('guide')}
        self.on('agent/bound', self.bound)
        self.on('capabilities/changed', self.bound)
        self.on('tool/available', self.available)
        self.on('tool/definition', self.definition)

    def bound(self, e):
        actor = e['actor']
        self.memory_tools(actor)
        for name in CHANNELS & self.r.state(actor)['grant']['framework'].keys():
            self.r.state(actor)['dynamic'][name + '_channel'] = dict(owner=self.id, name=name + '_channel', description=self.r.tools[name]['description'], parameters={'type': 'object', 'properties': {'preset': {'type': 'string', 'enum': list(self.guides)}} if name == 'datanet_create_network' else {}, 'required': ['preset'] if name == 'datanet_create_network' else [], 'additionalProperties': False})

    def memory_tools(self, actor):
        for name, description, parameters in (
            ('datanet_memory_read', '读取自己的个人记忆文件。', {'type': 'object', 'properties': {}, 'additionalProperties': False}),
            ('datanet_memory_write', '更新自己的个人记忆文件；保留值得复用的经验和关键信息。', {'type': 'object', 'properties': {'content': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['replace', 'append'], 'default': 'replace'}}, 'required': ['content'], 'additionalProperties': False}),
        ):
            self.r.state(actor)['dynamic'][name] = dict(owner=self.id, name=name, description=description, parameters=parameters)

    def available(self, e):
        if e['name'] in CHANNELS and e['name'] not in self.r.state(e['actor'])['channels']:
            e['allowed'] = False

    def definition(self, e):
        props = e['spec']['parameters'].get('properties', {})
        state = self.r.state(e['actor'])
        if e['name'] == 'datanet_create_network':
            props['preset']['enum'] = list(self.guides)
        if e['name'] == 'datanet_create_agent':
            props['preset']['enum'] = list(self.r.presets)
            props['toolboxes']['items']['enum'] = self.r.allowed
        if e['name'] == 'datanet_interfaces':
            props['action']['enum'] = state['grant']['framework'].get(e['name'], {}).get('actions', ['list', 'add', 'update', 'remove'])
        if e['name'] == 'datanet_presets':
            props['preset']['enum'] = list(self.guides)

    def invoke(self, actor, name, args):
        if name.endswith('_channel'):
            return self.enter(actor, name[:-8], args.get('preset'))
        if name not in ('datanet_create_agent', 'datanet_call_agent', 'datanet_manage_agent'):
            return super().invoke(actor, name, args)
        if name == 'datanet_call_agent':
            self.authorize(actor, args['target'], name, args)
            return super().invoke(actor, name, args)
        target = args.get('target', args.get('parent_node_id', actor) + '/' + args.get('child_id', ''))
        with self.lock:
            if target in self.locks:
                raise RuntimeError('Target Agent is busy')
            self.locks.add(target)
        try:
            self.authorize(actor, args.get('parent_node_id', actor) if name == 'datanet_create_agent' else target, name, args)
            return super().invoke(actor, name, args)
        finally:
            with self.lock:
                self.locks.remove(target)

    def authorize(self, actor, target, name, args):
        options = self.r.state(actor)['grant']['framework'].get(name, {})
        scope = options.get('scope', 'self')
        if name == 'datanet_manage_agent' and target in self.r.backend.agents:
            allowed = self.manages(actor, target, scope)
        else:
            method = 'check_delegation' if name == 'datanet_call_agent' else 'check_management'
            allowed = self.r.rpc(method, actor=actor, target=target, scope=scope, strength=args.get('strength', self.r.state(actor)['strength']))['allowed']
        if not allowed:
            raise PermissionError('Target is outside management grant')

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

    def enter(self, actor, name, preset=None):
        state = self.r.state(actor)
        if name not in state['grant']['framework']:
            raise PermissionError('Tool is not granted')
        if name == 'datanet_create_network':
            if preset not in self.guides:
                raise ValueError('Choose a supported network preset')
            added = self.r.load(actor, 'preset:' + preset, self.guides[preset])
        else:
            added = self.r.load(actor, 'tool:' + name, self.r.resource(self.id, 'guides/' + name + '/AGENTS.md'))
        skill = self.r.plugins.get('skills/network_management')
        if skill and 'network_management' in state['grant']['expanded']:
            skill.management_guide(actor)
        state['channels'].add(name)
        self.r.refresh(actor)
        return dict(tool=name, available=True, instructions_added=added)

    def bind_root(self, session_id):
        r = self.r
        if r.config.get('rootNetwork'):
            key = 'network_presets/' + r.config['rootNetwork']
            if key not in r.catalog or key in r.enabled:
                r.rpc('load_root_network', package=r.config['rootNetwork'], entry_point=r.config.get('rootEntryPoint', 'root'))
        binding = dict(r.backend.agents.get('root', {}))
        binding.pop('target', None)
        grant = r.resolve(r.config.get('rootToolboxes', r.defaults.get('rootToolboxes', [])))
        r.rpc('bind_agent', target='root', **{**binding, 'session_id': session_id, 'kind': 'root', 'creator_node_id': None, 'manager_id': None, 'activity': 'idle'})
        root = r.rpc('root_network_info')
        prompt = Path(root['agent_config']['prompt_path']).read_text(encoding='utf-8') if root.get('agent_config') else ''
        r.bind('root', session_id, 'project_root', grant, prompt)
        r.state('root')['strength'] = r.config.get('maxSignalStrength', 4)
        lifecycle = r.plugins.get('tools/agent_lifecycle')
        if lifecycle:
            lifecycle.initial()
        for actor, saved in list(r.backend.agents.items()):
            if actor == 'root' or actor in r.states or actor not in r.backend.network.nodes:
                continue
            if saved.get('kind') == 'discussion' and 'network_presets/discussion_group' not in r.enabled:
                continue
            try:
                self.create(actor, saved['prompt'], 'root', saved.get('maxStrength', r.config.get('discussionMaxSignalStrength', 2) if saved.get('kind') == 'discussion' else 2), saved.get('toolboxes', []), saved.get('role'), saved)
            except Exception as error:
                r.errors.append(dict(target=actor, error=str(error)))
        return r.view('root')

    def create(self, target, prompt, parent, strength=2, boxes=None, role=None, binding=None):
        r = self.r
        if binding is None and target in r.states:
            raise ValueError('Node already has an Agent')
        r.rpc('ensure_agent_node', target=target)
        grant = r.resolve(boxes or r.config.get('defaultAgentToolboxes', r.defaults.get('toolboxes', [])), None if binding else r.allowed, 'discussion' if role in ('leader', 'recorder', 'member') else role)
        path = r.directory / 'agents' / (target.encode().hex() + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding='utf-8')
        options = r.host('inspect', actor=parent).get('options', {})
        options = {k: options[k] for k in ('provider', 'model', 'maxTokens', 'reasoningEffort') if k in options}
        if r.config.get('provider'):
            options.update(provider=r.config['provider'], model=r.config.get('model'))
        options['maxTokens'] = r.config.get('agentMaxTokens', 4096)
        lifecycle = r.plugins.get('tools/agent_lifecycle')
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
        if role in ('leader', 'recorder', 'member'):
            saved['kind'] = 'discussion'
        if binding is None or reused:
            saved.update(manager_id=parent, creator_node_id=parent, reuse_key=key, reuse_eligible=True)
        r.rpc('bind_agent', target=target, **saved)
        mounted = r.host('create', actor=target, parent=parent, grant=grant, binding=r.backend.agents[target], resume=binding is not None)
        r.rpc('agent_progress', target=target, status='ready', activity='interrupted' if saved.get('activity') == 'running' else 'idle')
        r.bind(target, mounted['session_id'], role, grant, prompt)
        r.host('view-update', actor=target, view=r.view(target))
        if reused:
            r.state(target)['pending_task_boundary'] = '你已被重新装配。管理者：' + parent + '。个人记忆和会话已保留，当前任务以新的委托为准。'
        return dict(node_id=target, reused=reused, memory_path=str(r.backend.network.nodes[target].file_path), manager_id=r.backend.agents[target].get('manager_id'), creator_node_id=saved['creator_node_id'], session_id=mounted['session_id'], prompt_path=str(path), toolboxes=grant['names'])

    def tool_datanet_create_agent(self, actor, p):
        preset = self.r.presets.get(p.get('preset', 'worker'))
        if not preset:
            raise ValueError('Unknown Agent preset')
        prompt = p.get('prompt') or self.r.resource(preset['owner'], preset['prompt'])
        strength = p.get('max_signal_strength', preset.get('max_signal_strength', 2))
        if strength > self.r.state(actor)['strength']:
            raise PermissionError('Child signal limit exceeds creator grant')
        parent = p.get('parent_node_id', actor)
        created = self.r.rpc('create_node', actor=actor, options={**self.r.state(actor)['grant']['framework'].get('datanet_create_agent', {}), 'allow_custom': True}, child_id=p['child_id'], parent_node_id=parent, node_spec=dict(type='agent', name=p.get('name', p['child_id']), description=p.get('description', ''), parameters=dict(file_path=str(self.r.directory / 'memories' / (uuid4().hex + '.md')), creation_options={key: p[key] for key in ('name', 'description') if key in p})))
        result = self.create(created['items'][0]['node_id'], prompt, actor, strength, p.get('toolboxes', preset.get('toolboxes')), preset.get('experience_role', preset['id']))
        self.r.emit('graph/changed', actor=actor)
        return result

    def tool_datanet_memory_read(self, actor, p):
        return self.r.backend.network.nodes[actor].read_memory()

    def tool_datanet_memory_write(self, actor, p):
        result = self.r.backend.network.nodes[actor].write_memory(p['content'], p.get('mode', 'replace'))
        self.r.rpc('save')
        return result

    def reserve(self, actor, target, action):
        problem = self.r.plugins.get('toolboxes/problem_handling')
        if problem:
            problem.reserve(actor, target, action)

    def execute(self, actor, target, task, kind='agent', parent=None, round=None, reference=None, asynchronous=False):
        r = self.r
        if target not in r.states:
            raise ValueError('Node has no mounted Agent')
        if r.host('inspect', actor=target)['status'] != 'idle':
            raise RuntimeError('Agent is already busy')
        self.reserve(actor, target, 'execute')
        reports = r.plugins.get('tools/reports')
        diagnostics = r.plugins.get('tools/execution_records')
        if diagnostics and not asynchronous:
            diagnostics.start(actor)
        if reference and reports:
            reports.contexts[target] = reference
        else:
            reference = reports.delegate(actor, target, task, kind, parent, round) if reports else None
        problem = r.plugins.get('toolboxes/problem_handling')
        previous = problem.latest(target) if problem else None
        r.state(target)['scheduled'] = True
        try:
            if diagnostics:
                diagnostics.start(target)
            boundary = r.state(target).pop('pending_task_boundary', '')
            response = r.host('run', actor=target, text=(boundary + '\n' if boundary else '') + task, timeout_ms=r.config.get('turnTimeoutMs', 180000))
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

    def tool_datanet_call_agent(self, actor, p):
        if self.r.backend.agents.get(p['target'], {}).get('kind') != 'generic':
            raise ValueError('Use discussion scheduling for discussion members')
        if not self.r.rpc('check_access', actor=actor, target=p['target'], direction='read', strength=p.get('strength', self.r.state(actor)['strength']))['allowed']:
            raise PermissionError('Target is outside permitted network path')
        queue = self.r.plugins.get('tools/agent_delegation')
        if queue:
            return queue.submit(actor, p['target'], p['task'])
        return self.execute(actor, p['target'], p['task'])

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

    def tool_datanet_manage_agent(self, actor, p):
        target = p['target']
        state = self.r.state(target)
        binding = self.r.backend.agents[target]
        native = self.r.host('inspect', actor=target)
        if p['action'] == 'inspect':
            return dict(node_id=target, **native, manager_id=binding.get('manager_id'), managed_ids=binding.get('managed_ids', []), toolboxes=state['grant']['names'], prompt=state['prompt'], prompt_path=binding.get('promptPath'), creator_node_id=binding.get('creator_node_id'))
        if native['status'] != 'idle':
            raise RuntimeError('Agent is busy')
        if p['action'] == 'update_prompt':
            return self.update_prompt(actor, target, p['prompt'])
        if binding['kind'] == 'discussion':
            raise ValueError('Discussion restart/reset is scheduler-managed')
        self.reserve(actor, target, 'restart')
        self.r.host('dispose-agent', actor=target)
        self.r.states.pop(target)
        prompt = p.get('prompt', binding['prompt'])
        saved = dict(binding)
        saved.pop('session_id', None)
        # A new native session is requested, while the management identity persists.
        saved['session_id'] = 'datanet-' + str(uuid4())
        saved['status'] = 'prepared'
        if p.get('prompt') and p['prompt'] != binding['prompt']:
            saved['reuse_eligible'] = False
        return self.create(target, prompt, actor, binding['maxStrength'], state['grant']['names'], state['role'], saved)

    def tool_datanet_agent_capabilities(self, actor, p):
        return dict(agent_presets=[{**preset, 'promptPath': str(self.r.catalog[preset['owner']]['directory'] / preset['prompt'])} for preset in self.r.presets.values()], default=self.r.config.get('defaultAgentToolboxes', self.r.defaults.get('toolboxes', [])), toolboxes=[dict(id=name, description=self.r.boxes[name].get('description', name)) for name in self.r.allowed])

    def tool_datanet_presets(self, actor, p):
        lifecycle = self.r.plugins.get('tools/agent_lifecycle')
        if p.get('archived_network_id'):
            if not lifecycle:
                raise ValueError('Saved networks component is not enabled')
            return self.r.rpc('lifecycle_inventory', actor=actor, network_id=p['archived_network_id'])
        if p.get('preset'):
            return dict(preset=p['preset'], instructions_added=self.r.load(actor, 'preset:' + p['preset'], self.guides[p['preset']]))
        result = self.r.rpc('agent_capability', actor=actor, tool='list_node_presets', options=self.r.state(actor)['grant']['framework'].get('datanet_create_node', {}))
        if lifecycle:
            result.update(self.r.rpc('lifecycle_inventory', actor=actor))
        return result

    def tool_datanet_interfaces(self, actor, p):
        args = dict(p['arguments'], action=p['action'])
        if p['action'] != 'list' and not args.get('target_node_id') and not args.get('confirmation_id'):
            raise ValueError('target_node_id is required for add/update/remove')
        if args.get('interface'):
            args['interface'] = dict(threshold=0, multiplier=1, **args['interface'])
        options = self.r.state(actor)['grant']['framework'].get('datanet_interfaces', {})
        lifecycle = self.r.plugins.get('tools/agent_lifecycle')
        if lifecycle and p['action'] == 'remove':
            result = self.r.rpc('lifecycle_interfaces', actor=actor, options=options, arguments=args)
        else:
            if lifecycle and p['action'] == 'add' and args['target_node_id'] not in self.r.backend.network.nodes:
                self.r.rpc('lifecycle_wake', target=args['target_node_id'])
            result = self.r.rpc('agent_capability', actor=actor, tool='manage_interfaces', options=options, arguments=args)
        self.r.emit('graph/changed', actor=actor)
        return result

    def tool_datanet_create_node(self, actor, p):
        options = self.r.state(actor)['grant']['framework'].get('datanet_create_node', {})
        if options.get('allow_custom') is False and not p['node_spec'].get('preset'):
            raise PermissionError('Custom node configuration is disabled')
        if not p['node_spec'].get('preset'):
            p['node_spec'] = {'parameters': {}, **p['node_spec']}
        for direction in ('read', 'write'):
            if p.get(direction + '_interface'):
                p[direction + '_interface'] = {'threshold': 0, 'multiplier': 1, **p[direction + '_interface']}
        result = self.r.rpc('create_node', actor=actor, options=options, **p)
        self.r.emit('graph/changed', actor=actor)
        return result

    def tool_datanet_create_network(self, actor, p):
        if not self.r.host('document-present', actor=actor, document='preset:' + p['preset']):
            raise ValueError('Enter the network channel for this preset first')
        self.r.emit('network/before-create', actor=actor, arguments=p)
        result = self.r.rpc('create_network', actor=actor, strength=self.r.state(actor)['strength'], options=self.r.state(actor)['grant']['framework'].get('datanet_create_network', {}), **p)
        self.r.emit('network/created', actor=actor, arguments=p, result=result)
        structure = result.get('structure', result.get('items', [{}])[0].get('structure'))
        if structure:
            compact = dict(management='\n'.join(n['management_parent_id'] + ' → ' + n['node_id'] for n in structure['nodes'] if n['management_parent_id']))
            for direction in ('read', 'write'):
                rows = {}
                for edge in structure['attachment_interfaces'] + structure['interfaces']:
                    if edge['direction'] == direction:
                        rows.setdefault(edge['source_node_id'], []).append(edge['target_node_id'])
                compact[direction] = '\n'.join(source + ' → ' + ', '.join(dict.fromkeys(targets)) for source, targets in rows.items())
            if 'structure' in result:
                result['structure'] = compact
            else:
                result['items'][0]['structure'] = compact
        self.r.emit('graph/changed', actor=actor)
        self.r.rpc('save')
        return result
