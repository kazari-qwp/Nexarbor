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
        self.on('tool/available', self.available)
        self.on('tool/definition', self.definition)

    def bound(self, e):
        actor = e['actor']
        for name in CHANNELS & self.r.state(actor)['grant']['framework'].keys():
            self.r.state(actor)['dynamic'][name + '_channel'] = dict(owner=self.id, name=name + '_channel', description=self.r.tools[name]['description'], parameters={'type': 'object', 'properties': {'preset': {'type': 'string', 'enum': list(self.guides)}} if name == 'datanet_create_network' else {}, 'required': ['preset'] if name == 'datanet_create_network' else [], 'additionalProperties': False})

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
        target = args['target']
        with self.lock:
            if target in self.locks:
                raise RuntimeError('Target Agent is busy')
            self.locks.add(target)
        try:
            self.authorize(actor, target, name, args)
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
        grant = r.resolve(r.config.get('rootToolboxes', r.defaults.get('rootToolboxes', [])))
        r.rpc('bind_agent', target='root', **{**binding, 'session_id': session_id, 'kind': 'root', 'creator_node_id': None, 'manager_id': None, 'activity': 'idle'})
        root = r.rpc('root_network_info')
        prompt = Path(root['agent_config']['prompt_path']).read_text(encoding='utf-8') if root.get('agent_config') else ''
        r.bind('root', session_id, 'project_root', grant, prompt)
        r.state('root')['strength'] = r.config.get('maxSignalStrength', 4)
        for actor, saved in list(r.backend.agents.items()):
            if actor == 'root' or actor in r.states:
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
        grant = r.resolve(boxes or r.config.get('defaultAgentToolboxes', r.defaults.get('toolboxes', [])), None if binding else r.allowed, 'discussion' if role in ('leader', 'recorder', 'member') else role)
        path = r.directory / 'agents' / (target.encode().hex() + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding='utf-8')
        options = r.host('inspect', actor=parent).get('options', {})
        options = {k: options[k] for k in ('provider', 'model', 'maxTokens') if k in options}
        if r.config.get('provider'):
            options.update(provider=r.config['provider'], model=r.config.get('model'))
        options['maxTokens'] = r.config.get('agentMaxTokens', 4096)
        saved = {**(binding or {}), 'session_id': (binding or {}).get('session_id', 'datanet-' + str(uuid4())), 'kind': (binding or {}).get('kind', r.backend.agents.get(target, {}).get('kind', 'generic')), 'creator_node_id': (binding or {}).get('creator_node_id', parent), 'prompt': prompt, 'promptPath': str(path), 'toolboxes': grant['names'], 'maxStrength': strength, 'role': role, 'agentOptions': (binding or {}).get('agentOptions', options), 'status': (binding or {}).get('status', 'prepared')}
        saved.pop('target', None)
        r.rpc('bind_agent', target=target, **saved)
        mounted = r.host('create', actor=target, parent=parent, grant=grant, binding=r.backend.agents[target], resume=binding is not None)
        r.rpc('agent_progress', target=target, status='ready', activity='interrupted' if saved.get('activity') == 'running' else 'idle')
        r.bind(target, mounted['session_id'], role, grant, prompt)
        r.host('view-update', actor=target, view=r.view(target))
        return dict(node_id=target, manager_id=r.backend.agents[target].get('manager_id'), creator_node_id=saved['creator_node_id'], session_id=mounted['session_id'], prompt_path=str(path), toolboxes=grant['names'])

    def tool_datanet_create_agent(self, actor, p):
        if p['target'] == 'root':
            raise ValueError('Root already has a native Agent; create a child node and mount there')
        preset = self.r.presets.get(p.get('preset', 'worker'))
        if not preset:
            raise ValueError('Unknown Agent preset')
        prompt = p.get('prompt') or self.r.resource(preset['owner'], preset['prompt'])
        strength = p.get('max_signal_strength', preset.get('max_signal_strength', 2))
        if strength > self.r.state(actor)['strength']:
            raise PermissionError('Child signal limit exceeds creator grant')
        return self.create(p['target'], prompt, actor, strength, p.get('toolboxes', preset.get('toolboxes')), preset.get('experience_role', preset['id']))

    def reserve(self, actor, target, action):
        problem = self.r.plugins.get('toolboxes/problem_handling')
        if problem:
            problem.reserve(actor, target, action)

    def execute(self, actor, target, task, kind='agent', parent=None, round=None):
        r = self.r
        if target not in r.states:
            raise ValueError('Node has no mounted Agent')
        if r.host('inspect', actor=target)['status'] != 'idle':
            raise RuntimeError('Agent is already busy')
        self.reserve(actor, target, 'execute')
        reports = r.plugins.get('tools/reports')
        diagnostics = r.plugins.get('tools/execution_records')
        if diagnostics:
            diagnostics.start(actor)
        reference = reports.delegate(actor, target, task, kind, parent, round) if reports else None
        problem = r.plugins.get('toolboxes/problem_handling')
        previous = problem.latest(target) if problem else None
        r.state(target)['scheduled'] = True
        try:
            if diagnostics:
                diagnostics.start(target)
            response = r.host('run', actor=target, text=task, timeout_ms=r.config.get('turnTimeoutMs', 180000))
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
        self.r.rpc('agent_progress', target=target, prompt=prompt)
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
        return self.create(target, prompt, actor, binding['maxStrength'], state['grant']['names'], state['role'], saved)

    def tool_datanet_agent_capabilities(self, actor, p):
        return dict(agent_presets=[{**preset, 'promptPath': str(self.r.catalog[preset['owner']]['directory'] / preset['prompt'])} for preset in self.r.presets.values()], default=self.r.config.get('defaultAgentToolboxes', self.r.defaults.get('toolboxes', [])), toolboxes=[dict(id=name, description=self.r.boxes[name].get('description', name)) for name in self.r.allowed])

    def tool_datanet_presets(self, actor, p):
        if p.get('preset'):
            return dict(preset=p['preset'], instructions_added=self.r.load(actor, 'preset:' + p['preset'], self.guides[p['preset']]))
        return self.r.rpc('agent_capability', actor=actor, tool='list_node_presets', options=self.r.state(actor)['grant']['framework'].get('datanet_create_node', {}))

    def tool_datanet_interfaces(self, actor, p):
        args = dict(p['arguments'], action=p['action'])
        if p['action'] != 'list' and not args.get('target_node_id'):
            raise ValueError('target_node_id is required for add/update/remove')
        if args.get('interface'):
            args['interface'] = dict(threshold=0, multiplier=1, **args['interface'])
        result = self.r.rpc('agent_capability', actor=actor, tool='manage_interfaces', options=self.r.state(actor)['grant']['framework'].get('datanet_interfaces', {}), arguments=args)
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
