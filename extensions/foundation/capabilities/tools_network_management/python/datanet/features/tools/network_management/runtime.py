"""Agent creation, delegation and capability channels, independent of Harness."""
from pathlib import Path
from threading import Lock
from uuid import uuid4
import json
from datanet.core.application import Component

CHANNELS = {'datanet_create_node', 'datanet_create_agent', 'datanet_manage_agent', 'datanet_interfaces', 'datanet_create_network'}


class Plugin(Component):
    def install(self):
        self.on('session/root', self.root_session)
        self.locks = set()
        self.lock = Lock()
        self.guides = {m['preset']: self.r.resource(key, m['guide']) for key, m in self.r.catalog.items() if key in self.r.enabled and m.get('preset') and m.get('guide') and 'network_presets/'+m['preset'] in self.r.enabled}
        self.on('agent/bound', self.bound)
        self.on('capabilities/changed', self.bound)
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
            allowed = self.r.plugins['capabilities/agent_runtime'].manages(actor, target, scope)
        else:
            method = 'check_delegation' if name == 'datanet_call_agent' else 'check_management'
            allowed = self.r.rpc(method, actor=actor, target=target, scope=scope, strength=args.get('strength', self.r.state(actor)['strength']))['allowed']
        if not allowed:
            raise PermissionError('Target is outside management grant')


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
        state['channels'].add(name)
        self.r.refresh(actor)
        return dict(tool=name, available=True, instructions_added=added)

    def root_session(self, event):
        event['view'] = self.bind_root(event['session_id'])

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
        lifecycle = r.plugins.get('capabilities/agent_lifecycle')
        if lifecycle:
            lifecycle.initial()
        for actor, saved in list(r.backend.agents.items()):
            if actor == 'root' or actor in r.states or actor not in r.backend.network.nodes:
                continue
            if saved.get('kind') == 'discussion' and 'capabilities/discussion_group' not in r.enabled:
                continue
            try:
                self.r.plugins['capabilities/agent_runtime'].create(actor, saved['prompt'], 'root', saved.get('maxStrength', r.config.get('discussionMaxSignalStrength', 2) if saved.get('kind') == 'discussion' else 2), saved.get('toolboxes', []), saved.get('role'), saved)
            except Exception as error:
                r.errors.append(dict(target=actor, error=str(error)))
        return r.view('root')


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
        result = self.r.plugins['capabilities/agent_runtime'].create(created['items'][0]['node_id'], prompt, actor, strength, p.get('toolboxes', preset.get('toolboxes')), preset.get('experience_role', preset['id']))
        self.r.emit('graph/changed', actor=actor)
        return result





    def tool_datanet_call_agent(self, actor, p):
        if self.r.backend.agents.get(p['target'], {}).get('kind') != 'generic':
            raise ValueError('Use discussion scheduling for discussion members')
        if not self.r.rpc('check_access', actor=actor, target=p['target'], channels=('access.read',), strength=p.get('strength', self.r.state(actor)['strength']))['allowed']:
            raise PermissionError('Target is outside permitted network path')
        queue = self.r.plugins.get('capabilities/agent_delegation')
        if queue:
            return queue.submit(actor, p['target'], p['task'])
        return self.r.plugins['capabilities/agent_runtime'].execute(actor, p['target'], p['task'])


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
            return self.r.plugins['capabilities/agent_runtime'].update_prompt(actor, target, p['prompt'])
        if binding['kind'] == 'discussion':
            raise ValueError('Discussion restart/reset is scheduler-managed')
        self.r.plugins['capabilities/agent_runtime'].reserve(actor, target, 'restart')
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
        return self.r.plugins['capabilities/agent_runtime'].create(target, prompt, actor, binding['maxStrength'], state['grant']['names'], state['role'], saved)

    def tool_datanet_agent_capabilities(self, actor, p):
        return dict(agent_presets=[{**preset, 'promptPath': str(self.r.catalog[preset['owner']]['directory'] / preset['prompt'])} for preset in self.r.presets.values()], default=self.r.config.get('defaultAgentToolboxes', self.r.defaults.get('toolboxes', [])), toolboxes=[dict(id=name, description=self.r.boxes[name].get('description', name)) for name in self.r.allowed])

    def tool_datanet_presets(self, actor, p):
        lifecycle = self.r.plugins.get('capabilities/agent_lifecycle')
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
        options = self.r.state(actor)['grant']['framework'].get('datanet_interfaces', {})
        lifecycle = self.r.plugins.get('capabilities/agent_lifecycle')
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
            rows={}
            for edge in structure['attachment_interfaces']+structure['interfaces']:
                rows.setdefault(edge['source_node_id'],[]).append(edge['target_node_id'])
            compact['interfaces']='\n'.join(source+' → '+', '.join(dict.fromkeys(targets)) for source,targets in rows.items())
            if 'structure' in result:
                result['structure'] = compact
            else:
                result['items'][0]['structure'] = compact
        self.r.emit('graph/changed', actor=actor)
        self.r.rpc('save')
        return result
