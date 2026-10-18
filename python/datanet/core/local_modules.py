"""Node-local modules. Raw host objects stay on this side of the API."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import inspect
from .json_values import freeze, thaw, names
from .module_context import ModuleContext, ExtendedModuleContext, ModuleSignalContext, validate_access
from .access_budget import current_access, active_agent, access_context
from .interface import validate_strength

_executing = ContextVar('executing_node_module', default=None)


def json_copy(value):
    return thaw(freeze(asdict(value) if is_dataclass(value) else value))


def validate_modules(value):
    if not isinstance(value, dict): raise ValueError('Node modules must be an object')
    for name, spec in value.items():
        if not isinstance(name, str) or not name: raise ValueError('Invalid node module name')
        if not isinstance(spec, dict) or set(spec) != {'config', 'state', 'access'}:
            raise ValueError('Local modules require config, state and access; old modules are not supported')
        if not isinstance(spec['config'], dict) or not isinstance(spec['state'], dict):
            raise ValueError('Module config/state must be objects')
        validate_access(spec['access'])
    freeze(value)
    return deepcopy(value)


class NodeModule:
    def __init__(self, context):
        if not isinstance(context, ModuleContext): raise TypeError('NodeModule requires a local ModuleContext')
        self.context = context
        self.config, self.state = context.config, context.state
        self.active = True
        self.owned_tools, self.operations, self.receivers = set(), {}, []
    def install(self): pass
    def close(self): self.active = False
    def unmount(self): self.close()
    def tool(self, name, function, **definition): self.context.register_tool(name, function, **definition)
    def operation(self, name, function, *, channels=()): self.context.register_operation(name, function, channels=channels)
    def receive(self, channels, function): self.context.receive(channels, function)


class NodeModules:
    def __init__(self, backend, factories):
        self.backend, self.factories = backend, factories
        self.instances, self._access, self._published, self._generations = {}, {}, {}, {}
        self._owners, self._nodes = {}, {}
        self._bindings = []

    def _check(self, key, generation=None):
        if generation is not None and self._generations.get(key) is not generation:
            raise PermissionError('Module instance has been replaced')
        instance = self.instances.get(key)
        if instance is None or not instance.active: raise PermissionError('Node module is not active')
        owner = self._owners.get(key)
        if owner and owner not in self.backend.components.enabled:
            raise PermissionError('Node module component is disabled')
        return instance

    def _scope(self, key):
        self._check(key)
        frame = _executing.get()
        if not frame or frame['key'] != key or not frame['lease']['active']:
            raise PermissionError('Module APIs require their own active callback')
        self._check(key, frame['generation'])
        return frame

    @contextmanager
    def _enter(self, key, generation):
        self._check(key, generation)
        grant, incoming = self._access[key], current_access.get()
        strength, channels = grant['strength'], grant['channels']
        if incoming is not None and incoming['network'] is self.backend.network:
            if incoming['node_id'] != key[0]: raise PermissionError('Module must enter through an authorized endpoint')
            strength = min(strength, incoming['strength'])
            channels = tuple(c for c in channels if c in incoming['channels'])
        identity = active_agent.get()
        parent = _executing.get()
        caller = identity[1] if identity else parent['caller'] if parent and parent['lease']['active'] else key[0]
        lease = {'active': True}
        token = _executing.set(dict(key=key, generation=generation, lease=lease, strength=strength, channels=channels,
                                   caller=caller))
        try:
            with access_context(self.backend.network, key[0], strength, [key[0]], channels=channels): yield
        finally:
            lease['active'] = False
            _executing.reset(token)

    def _run(self, key, function, *args, **kwargs):
        generation = self._generations.get(key)
        if inspect.iscoroutinefunction(function):
            async def run():
                with self._enter(key, generation):
                    result = await function(*args, **kwargs)
                    self._check(key, generation)
                    return json_copy(result)
            return run()
        with self._enter(key, generation): result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            async def finish():
                with self._enter(key, generation):
                    result_value = await result
                    self._check(key, generation)
                    return json_copy(result_value)
            return finish()
        self._check(key, generation)
        return json_copy(result)

    def create(self, name, node, spec):
        key = (node.node_id, name)
        extension = self._extension(name)
        if spec['access'].get('extension') is not None and extension is None:
            raise PermissionError('Only host-registered modules may receive extended access')
        self._access[key] = freeze(spec['access'])
        generation = self._generations[key] = object()
        self._owners[key] = self.backend.components.module_owners.get(name)
        self._nodes[key] = node
        cls = ExtendedModuleContext if extension else ModuleContext
        def request(operation, /, **params):
            self._check(key, generation)
            return self._request(key, operation, params)
        context = cls(request,
                      node.node_id, name, spec['config'], spec['state'])
        try:
            instance = self.factories[name](context)
            if not isinstance(instance, NodeModule) or instance.context is not context:
                raise TypeError('Module factory must accept one ModuleContext and return its NodeModule')
            instance.owner = self.backend.components.module_owners.get(name)
            return instance
        except BaseException:
            self._access.pop(key, None)
            self._generations.pop(key, None)
            self._owners.pop(key, None); self._nodes.pop(key, None)
            raise

    def _extension(self, name):
        registration = getattr(self.backend.components, 'module_extensions', {}).get(name)
        if registration is None: return None
        factory, handler = registration
        if factory is not self.factories.get(name):
            raise PermissionError('Reserved extended module factory cannot be replaced')
        return handler

    def get(self, node_id, name):
        """Host-only lifecycle lookup; not exposed to modules."""
        return self.instances[(node_id, name)]

    def call(self, node_id, name, operation, arguments=None):
        """Host entry. Modules use await context.network.call instead."""
        key = (node_id, name); instance = self._check(key)
        if operation not in instance.operations: raise ValueError('Module operation is not declared: ' + operation)
        function, _ = instance.operations[operation]
        return self._run(key, function, **json_copy({} if arguments is None else arguments))

    def _budget(self, key, params):
        frame = self._scope(key)
        strength = frame['strength'] if params.get('strength') is None else validate_strength(params['strength'])
        channels = frame['channels'] if params.get('channels') is None else names(params['channels'], 'channels')
        if strength > frame['strength'] or not set(channels) <= set(frame['channels']):
            raise PermissionError('Module request exceeds its channel or strength grant')
        return strength, channels

    def _route(self, key, target, strength, channels):
        if not isinstance(target, str): raise TypeError('Target must be a node ID')
        incoming = current_access.get()
        if target != key[0] and incoming and target in incoming['visited']:
            raise PermissionError('Cannot revisit a node in a nested module call')
        for node, path, remaining in self.backend.network.walk_states(key[0], strength=strength, channels=channels):
            if node.node_id == target: return node, path, remaining
        raise PermissionError('Target is outside this module network view')

    def _request(self, key, operation, p):
        frame = self._scope(key); instance = self._check(key)
        node, network = self.backend.network.nodes[key[0]], self.backend.network
        if operation == 'caller': return frame['caller']
        if operation == 'local_metadata': return json_copy(node.get_metadata())
        if operation == 'publish_metadata':
            if not isinstance(p['fields'], dict): raise ValueError('Metadata fields must be an object')
            self._published[key] = json_copy(p['fields'])
            network.metadata_registry.register('module:' + repr(key),
                lambda target: self._metadata_fields(key, target))
            return None
        if operation == 'read': return json_copy(node.read(json_copy(p['request'])))
        if operation == 'write': return json_copy(node.write(p['key'], json_copy(p['value']), mode=p['mode']))
        if operation == 'inputs':
            def reject_files(value):
                if isinstance(value, dict):
                    if 'file' in value: raise PermissionError('Modules cannot load arbitrary document paths')
                    for item in value.values(): reject_files(item)
                elif isinstance(value, (list, tuple)):
                    for item in value: reject_files(item)
            patch = json_copy(p['patch']); reject_files(patch)
            if not hasattr(node, 'inputs'): raise TypeError('Only Agent nodes have input surfaces')
            return json_copy(node.inputs.update('module:' + key[1], patch))
        if operation == 'register_tool':
            name, function, definition = p['name'], p['function'], dict(p['definition'])
            if name in node.tools: raise ValueError('Module tool conflicts: ' + name)
            refusal = definition.pop('refusal', None)
            generation = self._generations[key]
            if inspect.iscoroutinefunction(function):
                async def guarded(**args):
                    self._check(key, generation)
                    return await self._run(key, function, **args)
            else:
                def guarded(**args):
                    self._check(key, generation)
                    return self._run(key, function, **args)
            def guarded_refusal(actor, reason):
                self._check(key, generation)
                return self._run(key, refusal, actor, reason)
            node.register_tool(name, guarded, refusal=guarded_refusal if refusal else None, **definition)
            instance.owned_tools.add(name)
            if name not in node.expose: node.expose.append(name)
            return None
        if operation == 'register_operation':
            name = p['name']
            if not isinstance(name, str) or not name or name in instance.operations or not callable(p['function']):
                raise ValueError('Invalid or duplicate module operation')
            instance.operations[name] = (p['function'], names(p['channels'], 'operation channels'))
            return None
        if operation == 'receive':
            if not callable(p['function']): raise TypeError('Signal receiver must be callable')
            instance.receivers.append((names(p['channels'], 'signal channels', allow_empty=False), p['function']))
            return None
        if operation == 'extended':
            handler = self._extension(key[1])
            policy = self._access[key].get('extension')
            if not handler or not policy or p['operation'] not in policy['operations']:
                raise PermissionError('Extended operation was not explicitly granted')
            return json_copy(handler(self.backend, key[0], policy, p['operation'], json_copy(p['arguments'])))
        if operation in ('call', 'invoke'):
            # Defer the whole authorization and endpoint lookup until actually awaited.
            async def invoke():
                strength, channels = self._budget(key, p)
                target, _, _ = self._route(key, p['target'], strength, channels)
                if operation == 'call':
                    target_key = (p['target'], p['module'])
                    callee = self._check(target_key)
                    entry = callee.operations.get(p['operation'])
                    if entry is None: raise PermissionError('No accessible module operation')
                    function, declared = entry
                else:
                    if p['tool'] not in target.expose or p['tool'] not in target.tool_definitions:
                        raise PermissionError('No accessible node tool')
                    definition = target.tool_definitions[p['tool']]
                    declared = definition['access_channels']
                    from .tool_access import validate_arguments
                    validate_arguments(p['arguments'], definition['parameters'])
                    function = target.tools[p['tool']]
                selected = tuple(c for c in channels if c in declared)
                if (declared or p['target'] != key[0]) and not selected:
                    raise PermissionError('Endpoint channel is not granted')
                _, path, remaining = self._route(key, p['target'], strength, selected)
                with access_context(network, p['target'], remaining, path, channels=selected):
                    if operation == 'call': result = self._run(target_key, function, **json_copy(p['arguments']))
                    else: result = function(**json_copy(p['arguments']))
                    if inspect.isawaitable(result): result = await result
                    self._scope(key)
                    return json_copy(result)
            return invoke()
        strength, channels = self._budget(key, p)
        if operation in ('nodes', 'metadata'):
            if operation == 'metadata':
                target, _, _ = self._route(key, p['target'], strength, channels)
                return json_copy(target.get_metadata())
            return [dict(metadata=json_copy(target.get_metadata()), path=path, strength=remaining)
                    for target, path, remaining in network.walk_states(key[0], channels=channels, strength=strength)]
        if operation == 'tools':
            target, _, _ = self._route(key, p['target'], strength, channels)
            result = []
            for name, definition in target.tool_definitions.items():
                if name not in target.expose or name not in target.tools: continue
                selected = tuple(c for c in channels if c in definition['access_channels'])
                if (definition['access_channels'] or p['target'] != key[0]) and not selected: continue
                try: _, path, remaining = self._route(key, p['target'], strength, selected)
                except PermissionError: continue
                result.append(dict(**json_copy(definition), path=path, remaining_strength=remaining))
            return result
        if operation == 'emit':
            from .signals import Signal
            allowed = {'kind', 'sequence', 'close_loop', 'failure_policy', 'max_hops', 'max_deliveries',
                       'timeout_seconds', 'node_timeout_seconds', 'parent_id'}
            if set(p['options']) - allowed: raise PermissionError('Module cannot override signal identity')
            signal = Signal(key[0], channels, strength, content=p['content'], **p['options'])
            async def emit():
                self._budget(key, p)
                result = await self.backend.signals.propagate(signal)
                return dict(signal_id=signal.signal_id, status=result['status'], returned=result['returned'])
            return emit()
        raise ValueError('Unknown local module request: ' + operation)

    @contextmanager
    def transaction(self, *node_ids):
        """Host-only rollback, not a module capability."""
        with self.backend._transaction_lock:
            states = [(m.state, deepcopy(m.state)) for (node, _), m in self.instances.items() if not node_ids or node in node_ids]
            try: yield
            except BaseException:
                for target, snapshot in states: target.clear(); target.update(snapshot)
                raise

    def find(self, name): return [m for (_, module), m in self.instances.items() if module == name]
    def refresh(self): self.bind_signals()

    def _metadata_fields(self, key, target):
        if target != key[0] or key not in self._published: return {}
        try: self._check(key)
        except PermissionError: return {}
        return {key[1]: self._published[key]}

    def _remove(self, key, *, unmount=False):
        instance = self.instances[key]
        try:
            # Teardown may release its own resources; API authority is not reactivated.
            (instance.unmount if unmount else instance.close)()
        finally:
            instance.active = False
            node = self._nodes[key]
            for name in instance.owned_tools:
                node.tools.pop(name, None); node.tool_definitions.pop(name, None); node.tool_refusals.pop(name, None)
                node.expose[:] = [item for item in node.expose if item != name]
            self._published.pop(key, None)
            self.backend.network.metadata_registry.unregister('module:' + repr(key))
            self._access.pop(key, None)
            self._generations.pop(key, None)
            self._owners.pop(key, None); self._nodes.pop(key, None)

    def clear(self):
        for node, runtime in self._bindings: runtime.unbind(node)
        self._bindings = []
        errors = []
        for key in reversed(list(self.instances)):
            try: self._remove(key)
            except BaseException as error: errors.append(error)
            finally: self.instances.pop(key, None)
        if errors: raise errors[0]

    def restore(self):
        self.clear()
        try:
            for node in self.backend.network.nodes.values():
                validate_modules(node.modules)
                for name, spec in node.modules.items():
                    if name not in self.factories: raise ValueError('Missing node module component: ' + name)
                    self.instances[(node.node_id, name)] = self.create(name, node, spec)
            for key, instance in self.instances.items(): self._run(key, instance.install)
            self.bind_signals()
        except BaseException:
            self.clear()
            raise

    def mount(self, node_id, name, config=None, state=None, *, access=None):
        with self.backend._transaction_lock:
            node = self.backend.network.nodes[node_id]
            if name in node.modules: raise ValueError('Module already mounted')
            spec = validate_modules({name: dict(config={} if config is None else config,
                state={} if state is None else state, access={'strength': 0, 'channels': []} if access is None else access)})[name]
            if name not in self.factories: raise ValueError('Missing node module component: ' + name)
            instance = self.create(name, node, spec); key = (node_id, name)
            node.modules[name] = spec; self.instances[key] = instance
            try:
                self._run(key, instance.install)
                self.bind_signals()
            except BaseException:
                try: self._remove(key)
                finally:
                    node.modules.pop(name); self.instances.pop(key)
                raise
            return instance

    def unmount(self, node_id, name):
        with self.backend._transaction_lock:
            key = (node_id, name)
            spec = self.backend.network.nodes[node_id].modules[name]
            try: self._remove(key, unmount=True)
            finally:
                self.instances.pop(key)
                self.backend.network.nodes[node_id].modules.pop(name)
                self.bind_signals()
            return spec

    def bind(self, application):
        # Application stays on the host side; modules receive no event bus object.
        self.bind_signals()

    def bind_signals(self):
        runtime = self.backend.network.signals
        old = {node for node, bound in self._bindings if bound is runtime}
        for key, module in self.instances.items():
            if module.active and module.receivers and key[0] in runtime.bindings and key[0] not in old:
                raise ValueError('Node already has a host signal handler')
        for node, runtime in self._bindings: runtime.unbind(node)
        self._bindings = []; runtime = self.backend.network.signals
        for node in self.backend.network.nodes.values():
            keys = [key for key, m in self.instances.items() if key[0] == node.node_id and m.active and m.receivers]
            if not keys: continue
            if node.node_id in runtime.bindings: raise ValueError('Node already has a host signal handler')
            generations = {key:self._generations[key] for key in keys}
            async def receive(context, keys=tuple(keys), generations=generations):
                results = []; delivered = ModuleSignalContext(context.signal, context.delivery)
                for key in keys:
                    module = self._check(key, generations[key])
                    for channels, function in tuple(module.receivers):
                        if set(channels).intersection(context.signal.channels):
                            result = self._run(key, function, delivered)
                            if inspect.isawaitable(result): result = await result
                            results.append(result)
                return results
            runtime.bind(node.node_id, receive, access_strength=max(self._access[key]['strength'] for key in keys))
            self._bindings.append((node.node_id, runtime))
