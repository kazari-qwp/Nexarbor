"""Transport-independent component host. Native sessions are accessed through a port."""
from collections import defaultdict
from importlib import import_module
from pathlib import Path
from threading import RLock, local
import json
from datanet.core.component_registry import enabled_components


def checked(value):
    from dataclasses import asdict, is_dataclass
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict) and value.get('status', 'ok') != 'ok':
        raise RuntimeError(json.dumps(value, ensure_ascii=False))
    return value


class Application:
    def __init__(self, backend, port, config):
        self.backend, self.port, self.config = backend, port, config
        self.catalog = backend.components.catalog
        self.enabled = backend.components.enabled
        self.directory = backend.directory
        self.listeners = defaultdict(list)
        self.plugins, self.states, self.tools, self.tool_owners = {}, {}, {}, {}
        self.lock, self.local = RLock(), local()
        self.errors = []
        self.boxes, self.presets = {}, {}
        self.defaults = {}
        for key, manifest in self.catalog.items():
            if key not in self.enabled:
                continue
            self.defaults.update(manifest.get('agentDefaults', {}))
            if manifest.get('box'):
                box = self.resource(key, manifest['box'], json_data=True)
                self.boxes[box['id']] = box
            if manifest.get('agentPreset'):
                preset = dict(manifest['agentPreset'])
                preset['owner'] = key
                self.presets[preset['id']] = preset
            if manifest.get('toolDefinitions'):
                for name, spec in self.resource(key, manifest['toolDefinitions'], json_data=True).items():
                    self.tools[name] = spec
                    self.tool_owners[name] = key
            module = manifest.get('python', {}).get('runtime')
            if module:
                self.plugins[key] = import_module(module).Plugin(self, manifest)
        self.boxes.update(config.get('toolboxes', {}))
        self.allowed = config.get('allowedAgentToolboxes', self.defaults.get('allowedToolboxes', []))
        for plugin in self.plugins.values():
            plugin.install()

    def resource(self, owner, relative, json_data=False):
        directory = self.catalog[owner]['directory'].resolve()
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('Component resource escapes its directory')
        text = path.read_text(encoding='utf-8')
        return json.loads(text) if json_data else text

    def on(self, owner, event, function):
        self.listeners[event].append((owner, function))

    def emit(self, event, **payload):
        for owner, function in list(self.listeners[event]):
            if owner in self.enabled:
                function(payload)

    def host(self, operation, **payload):
        payload.setdefault('execution_id', getattr(self.local, 'execution_id', None))
        return self.port(operation, payload)

    def rpc(self, method, **params):
        result = self.backend.dispatch(method, params)
        return result if method == 'report_feedback' else checked(result)

    def state(self, actor):
        return self.states[actor]

    def metadata(self, actor):
        binding = self.backend.agents.get(actor, {})
        state = self.state(actor)
        return dict(node_id=actor, session_id=state['session_id'], role=state.get('role'),
                    manager_id=binding.get('manager_id'), creator_node_id=binding.get('creator_node_id'),
                    toolboxes=state['grant']['names'])

    def resolve(self, names, allowed=None, role=None):
        if len(set(names)) != len(names):
            raise ValueError('Toolboxes must be unique IDs')
        policies = [m for key, m in self.catalog.items() if key in self.enabled and m.get('agentPolicy')]
        baselines = {m['id'].split('/')[1] for m in policies if m['agentPolicy'].get('baseline')}
        selected = [name for name in names if name not in baselines]
        for name in selected:
            if allowed is not None and name not in allowed:
                raise PermissionError('Toolbox is not granted: ' + name)
        selected += [m['id'].split('/')[1] for m in policies if m['agentPolicy'].get('baseline') and role not in m['agentPolicy'].get('exceptRoles', [])]
        active, done, expanded = set(), set(), []
        def visit(name):
            if name in active:
                raise ValueError('Cyclic toolbox includes: ' + name)
            if name in done:
                return
            if name not in self.boxes:
                raise ValueError('Unknown toolbox: ' + name)
            if 'toolboxes/' + name not in self.enabled:
                return
            active.add(name)
            for child in self.boxes[name].get('includes', []):
                visit(child)
            active.remove(name)
            done.add(name)
            expanded.append(name)
        for name in selected:
            visit(name)
        framework, official, skills, providers = {}, [], [], []
        all_skills = False
        policies_by_tool = {name: policy for m in self.catalog.values() for name, policy in m.get('toolPolicies', {}).items()}
        for name in expanded:
            box = self.boxes[name]
            for item in box.get('tools', []):
                tool = item['name']
                if item['source'] == 'harness':
                    if tool not in official:
                        official.append(tool)
                    continue
                if item['source'] != 'datanet':
                    raise ValueError('Unknown tool source')
                owner = self.tool_owners.get(tool)
                if owner and owner not in self.enabled:
                    continue
                policy = policies_by_tool.get(tool, {})
                options = {**policy.get('defaults', {}), **item.get('options', {})}
                for field, value in item.get('options', {}).items():
                    spec = policy.get('properties', {}).get(field)
                    types = {'boolean': bool, 'number': (float, int), 'string': str, 'array': list}
                    if not spec or not isinstance(value, types[spec['type']]):
                        raise ValueError('Invalid toolbox option: ' + field)
                    if spec.get('enum') and any(v not in spec['enum'] for v in (value if isinstance(value, list) else [value])):
                        raise ValueError('Invalid toolbox option: ' + field)
                if tool in framework and options != framework[tool]:
                    if name in baselines:
                        continue
                    if not policy.get('merge'):
                        raise ValueError('Conflicting toolbox options: ' + tool)
                    for field, method in policy['merge'].items():
                        options[field] = max(framework[tool].get(field, 0), options.get(field, 0)) if method == 'max' else bool(framework[tool].get(field) or options.get(field))
                framework[tool] = options
            if box.get('skills') == '*':
                all_skills = True
            else:
                skills.extend(box.get('skills', []))
            providers.extend(box.get('skillProviders', []))
        return dict(names=list(dict.fromkeys(selected)), expanded=expanded, framework=framework,
                    official=dict(tools=official, skills='*' if all_skills else list(dict.fromkeys(skills)), skillProviders=list(dict.fromkeys(providers))))

    def bind(self, actor, session_id, role=None, grant=None, prompt=None):
        state = self.states.setdefault(actor, dict(channels=set(), dynamic={}, sections={}))
        state.update(session_id=session_id, role=role, grant=grant, prompt=prompt or '', strength=self.backend.agents.get(actor, {}).get('maxStrength', self.config.get('maxSignalStrength', 4)))
        self.emit('agent/bound', actor=actor, state=state)
        self.refresh(actor)
        return self.view(actor)

    def section(self, actor, owner, name, text, order=85):
        self.state(actor)['sections'][name] = dict(owner=owner, name=name, text=text, order=order)

    def load(self, actor, document, text):
        return self.host('load-document', actor=actor, document=document, text=text)

    def view(self, actor):
        state = self.state(actor)
        sections = [{**s, 'text': s['text']() if callable(s['text']) else s['text']} for s in state['sections'].values() if s['owner'] in self.enabled]
        return dict(prompt=state['prompt'].replace('{{node:self}}', actor), sections=sections, grant=state['grant'])

    def definitions(self, actor):
        result = []
        state = self.state(actor)
        for name in state['grant']['framework']:
            owner = self.tool_owners.get(name)
            if owner not in self.enabled or name not in self.tools:
                continue
            spec = json.loads(json.dumps(self.tools[name]))
            payload = dict(actor=actor, name=name, spec=spec, allowed=True)
            self.emit('tool/definition', **payload)
            # Handlers mutate spec; availability is evaluated separately.
            if not self.available(actor, name):
                continue
            result.append(spec)
        for name, spec in state['dynamic'].items():
            if spec['owner'] in self.enabled:
                result.append({k: v for k, v in spec.items() if k != 'owner'})
        return result

    def available(self, actor, name):
        payload = dict(actor=actor, name=name, allowed=True)
        for owner, function in self.listeners['tool/available']:
            if owner in self.enabled:
                function(payload)
        return payload['allowed']

    def refresh(self, actor):
        self.host('tools', actor=actor, definitions=self.definitions(actor))

    def invoke(self, actor, name, arguments, execution_id=None):
        self.local.execution_id = execution_id
        state = self.state(actor)
        spec = state['dynamic'].get(name)
        owner = spec['owner'] if spec else self.tool_owners.get(name)
        if owner not in self.enabled or not self.available(actor, name):
            raise PermissionError('[DATANET_TOOL_PERMISSION_DENIED] ' + name + ' 当前已停用。')
        if not spec and name not in state['grant']['framework']:
            raise PermissionError('Tool is not granted')
        options = state['grant']['framework'].get(name, {})
        arguments = dict(arguments)
        if 'strength' in self.tools.get(name, {}).get('parameters', {}).get('properties', {}):
            arguments.setdefault('strength', state['strength'])
        if arguments.get('strength', arguments.get('arguments', {}).get('strength', state['strength'])) > state['strength']:
            raise PermissionError('Signal strength exceeds Agent grant')
        if options.get('actions') and arguments.get('action') and arguments['action'] not in options['actions']:
            raise PermissionError('Action is outside toolbox grant')
        if options.get('allow_custom') is False and arguments.get('prompt'):
            raise PermissionError('Custom prompts are outside toolbox grant')
        self.emit('tool/before', actor=actor, name=name, arguments=arguments, options=options)
        plugin = self.plugins[owner]
        try:
            result = plugin.invoke(actor, name, arguments)
            self.emit('tool/after', actor=actor, name=name, arguments=arguments, result=result)
            return result
        except Exception as error:
            self.emit('tool/error', actor=actor, name=name, arguments=arguments, error=str(error))
            raise

    def disable(self, component):
        removed = set()
        while component in self.enabled:
            self.enabled.remove(component)
            removed.add(component)
            dependent = next((key for key in self.enabled if any(dep not in self.enabled for dep in self.catalog[key].get('requires', []))), None)
            if dependent is None:
                break
            component = dependent
        enabled_components().difference_update(removed)
        for key in removed:
            plugin = self.plugins.get(key)
            if plugin and hasattr(plugin, 'close'):
                plugin.close()
            self.plugins.pop(key, None)
        for actor in self.states:
            self.refresh(actor)
        return sorted(removed)

    def event(self, actor, name, payload):
        self.emit(name, actor=actor, **payload)
        return self.view(actor)


class Component:
    def __init__(self, runtime, manifest):
        self.r, self.manifest, self.id = runtime, manifest, manifest['id']

    def on(self, event, function):
        self.r.on(self.id, event, function)

    def install(self):
        pass

    def invoke(self, actor, name, args):
        return getattr(self, 'tool_' + name)(actor, args)

    def section(self, actor, name, text, order=85):
        self.r.section(actor, self.id, name, text, order)
