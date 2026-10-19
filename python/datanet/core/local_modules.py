"""Node-local modules. Raw host objects stay on this side of the API."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import inspect
import asyncio
import time
import sys
from .access_request import AccessRequest
from .module_protocol import Activation, ComponentResult, require_definition
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
    """Core-owned bound instance. Component code provides only execute()."""
    def __init__(self, context, definition):
        self.context, self.definition = context, definition
        self.config, self.state = context.config, context.state
        self.active = True
        self.owned_tools, self.operations, self.receivers = set(), {}, []

    def close(self): self.active = False
    def unmount(self): self.close()
    def install(self):
        definition = self.definition
        if self.context.metadata()['node_type'] not in definition.node_types:
            raise ValueError('Component does not support this node type')
        definition.validate(self.config, definition.config_schema)
        definition.validate(self.state, definition.state_schema)
        for name, spec in definition.operations.items():
            async def call(_name=name, _spec=spec, /, **parameters):
                definition.validate(parameters, _spec['parameters'])
                return await self.execute(Activation('access', _name, parameters, self.context.caller_id), _spec['result'])
            self.operations[name] = (call, tuple(spec['channels']))
        signal_channels = names(self.config.get(definition.signals['config'], []), 'signal channels') if isinstance(definition.signals, dict) else definition.signals
        if signal_channels:
            async def receive(delivered):
                return await self.execute(Activation('signal', delivered.signal.kind, {}, delivered.signal.origin,
                    request_id=delivered.receipt_id, signal=delivered.signal, delivery=delivered.delivery))
            self.receivers.append((signal_channels, receive))

    async def execute(self, activation, schema=None):
        value = await self.definition.execute(self.context, activation)
        if type(value) is not ComponentResult: raise TypeError('execute must return ComponentResult')
        self.definition.validate(self.state, self.definition.state_schema)
        if value.status == 'ok' and schema is not None: self.definition.validate(value.data, schema)
        return dict(status=value.status, data=thaw(value.data), error=value.error)


class NodeModules:
    def __init__(self, backend, factories):
        self.backend, self.factories = backend, factories
        from .node_locks import NodeLocks
        if not hasattr(backend, 'node_locks'): backend.node_locks = NodeLocks(backend)
        backend.network.node_locks = backend.node_locks
        self.instances, self._access, self._published, self._generations = {}, {}, {}, {}
        self._owners, self._nodes = {}, {}
        self._bindings = []
        self.executing = 0

    def _check(self, key, generation=None):
        self.backend.node_locks._check()
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
        grant = self._access[key]
        strength, channels = self._strength(key), grant['channels']
        # A callee enters with its own grant, after the caller's path was checked.
        incoming_token = current_access.set(None)
        identity = active_agent.get()
        parent = _executing.get()
        caller = parent['key'][0] if parent and parent['lease']['active'] else identity[1] if identity else key[0]
        trace = parent['trace'] if parent and parent['lease']['active'] else dict(calls=0, deadline=time.monotonic()+180)
        lease = {'active': True}
        token = _executing.set(dict(key=key, generation=generation, lease=lease, strength=strength, channels=channels,
                                   caller=caller, requester=parent['requester'] if parent and parent['lease']['active'] else caller, children=[], trace=trace, scopes=[]))
        self.executing += 1
        try:
            with access_context(self.backend.network, key[0], strength, [key[0]], channels=channels): yield
        finally:
            lease['active'] = False
            self.executing -= 1
            _executing.reset(token)
            current_access.reset(incoming_token)

    def _run(self, key, function, /, *args, **kwargs):
        generation = self._generations.get(key)
        if inspect.iscoroutinefunction(function):
            async def run():
                async with self.backend.node_locks.access([key[0]]):
                    return await owned()
            async def owned():
                with self._enter(key, generation):
                    try:
                        result = await function(*args, **kwargs)
                        children = _executing.get()['children']
                        index = 0
                        while index < len(children):
                            batch = children[index:]; index = len(children)
                            outcomes = await asyncio.gather(*(child.task for child in batch), return_exceptions=True)
                            for child, outcome in zip(batch, outcomes):
                                if isinstance(outcome, BaseException) and not child.observed: raise outcome
                        instance = self._check(key, generation)
                        instance.definition.validate(instance.state, instance.definition.state_schema)
                    except BaseException:
                        children = _executing.get()['children']
                        for child in children:
                            if not child.done(): child.cancel()
                        await asyncio.gather(*(child.task for child in children), return_exceptions=True)
                        raise
                    finally:
                        abandoned = [scope for scope in _executing.get()['scopes'] if scope.group is not None and not scope.closed]
                        for scope in reversed(abandoned):
                            await scope.__aexit__(RuntimeError, RuntimeError('Unclosed node lock scope'), None)
                        if abandoned and not sys.exc_info()[0]:
                            raise RuntimeError('Unclosed node lock scope was rolled back')
                    self._check(key, generation)
                    return json_copy(result)
            return run()
        with self.backend.node_locks.access_sync([key[0]]):
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
        require_definition(self.factories[name])
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

    def _accessible(self, actor, target, module, operation, strength, channels):
        instance = self._check((target, module))
        declared = instance.operations[operation][1]
        selected = tuple(c for c in names(channels, 'access channels') if c in declared)
        if (declared or actor != target) and not selected: raise PermissionError('Operation channel is not granted')
        route = next(((path, left) for node, path, left in self.backend.network.walk_states(
            actor, strength=strength, channels=selected) if node.node_id == target), None)
        if route is None: raise PermissionError('Component is outside the current graph view')
        return selected, route

    def tool_sources(self, actor, target, *, strength, channels):
        """Expose only reachable, active declared tool provider endpoints."""
        with self.backend.node_locks.access_sync([target], mutable=False):
            return self._tool_sources(actor,target,strength=strength,channels=channels)

    def _tool_sources(self, actor, target, *, strength, channels):
        result = []
        for node, module in self.instances:
            if node != target: continue
            try:
                instance = self._check((node, module)); provider = instance.definition.tool_provider
                if instance.definition.agent_tools:
                    allowed=[]
                    for tool in instance.definition.agent_tools.values():
                        try:self._accessible(actor,target,module,tool['operation'],strength,channels);allowed.append(tool['id'])
                        except PermissionError:continue
                    if allowed:result.append(dict(node_id=node,module=module,static=True))
                    continue
                if not provider: continue
                for operation in provider.values(): self._accessible(actor, target, module, operation, strength, channels)
            except PermissionError: continue
            result.append(dict(node_id=node, module=module, **thaw(provider)))
        return result

    async def access(self, actor, target, module, operation, arguments=None, *, strength, channels):
        """Trusted host adapter entry; module code uses its scoped network.call."""
        from types import SimpleNamespace
        async with self.backend.node_locks.access([target]):
            selected, (path, left) = self._accessible(actor, target, module, operation, strength, channels)
            identity = active_agent.set((SimpleNamespace(max_signal_strength=strength), actor))
            try:
                with access_context(self.backend.network, target, left, path, channels=selected):
                    return await self.call(target, module, operation, arguments)
            finally: active_agent.reset(identity)

    def _strength(self,key):
        value=self._access[key]['strength']
        return self._nodes[key].module_strength if value is None else value

    def _budget(self, key, params):
        frame = self._scope(key)
        strength = frame['strength'] if params.get('strength') is None else validate_strength(params['strength'])
        channels = frame['channels'] if params.get('channels') is None else names(params['channels'], 'channels')
        if strength > frame['strength'] or not set(channels) <= set(frame['channels']):
            raise PermissionError('Module request exceeds its channel or strength grant')
        return strength, channels

    def _route(self, key, target, strength, channels):
        if not isinstance(target, str): raise TypeError('Target must be a node ID')
        for node, path, remaining in self.backend.network.walk_states(key[0], strength=strength, channels=channels):
            if node.node_id == target: return node, path, remaining
        raise PermissionError('Target is outside this module network view')

    def _request(self, key, operation, p):
        frame = self._scope(key); instance = self._check(key)
        node, network = self.backend.network.nodes[key[0]], self.backend.network
        if operation=='signal_id':
            from .signal_work import current_work
            work=current_work.get();return work.signal_id if work else None
        if operation=='post':
            from .signal_work import current_work
            work=current_work.get()
            if work is None:raise RuntimeError('Deferred access requires an active signal layer')
            strength,channels=self._budget(key,p);self._route(key,p['target'],strength,channels)
            generation=frame['generation'];arguments=json_copy(p['arguments'])
            self._accessible(key[0],p['target'],p['module'],p['operation'],strength,channels)
            async def later():
                self._check(key,generation)
                return await self.access(key[0],p['target'],p['module'],p['operation'],arguments,strength=strength,channels=channels)
            return work.post(later,p['target']+'/'+p['module']+'/'+p['operation'])
        if operation == 'lock_nodes':
            strength, channels = self._budget(key,p)
            start = len(frame['children'])
            async def finish(cancel):
                index = start
                while index < len(frame['children']):
                    batch = frame['children'][index:]; index = len(frame['children'])
                    if cancel:
                        for child in batch: child.cancel()
                    results = await asyncio.gather(*(child.task for child in batch), return_exceptions=True)
                    if not cancel:
                        for child, result in zip(batch,results):
                            if isinstance(result,BaseException) and not child.observed: raise result
            scope = self.backend.node_locks.transaction(key[0],p['nodes'],strength=strength,channels=channels,
                timeout=p['timeout'],validate=lambda:self._budget(key,p),finish=finish)
            frame['scopes'].append(scope)
            return scope
        if operation == 'patch_edges':
            from .edge_changes import edge_changes
            changes=edge_changes(json_copy(p['changes']));p=dict(p);p['strength'],p['channels']=self._budget(key,p)
            targets=tuple(dict.fromkeys(n for change in changes for n in (change['source'],change['edge'].target_node_id)))
            async def patch():
                async with self.backend.node_locks.access(targets):
                    strength,channels=self._budget(key,p)
                    with self.backend._transaction_lock:
                        for target in targets:self._route(key,target,strength,channels)
                        for change in changes:
                            if not set(change['edge'].metadata.channels)<=set(channels):raise PermissionError('连接频道不能超过模块授权')
                        pending={source:list(network.nodes[source].interfaces) for source in {c['source'] for c in changes}}
                        for change in changes:
                            edges=pending[change['source']];edge=change['edge']
                            if change['action']=='remove':edges[:]=[old for old in edges if old!=edge]
                            elif edge not in edges:edges.append(edge)
                        for source,edges in pending.items():network.nodes[source].interfaces=edges
                    return dict(changed=len(changes))
            request=AccessRequest(patch());frame['children'].append(request);return request
        if operation in ('nodes','metadata','edges','tools','visit','tool_sources'):
            p = dict(p); p['strength'],p['channels'] = self._budget(key,p)
            async def query():
                while True:
                    strength, channels = self._budget(key,p)
                    reached = list(network.walk_states(key[0],strength=strength,channels=channels))
                    targets = [n.node_id for n,_,_ in reached] if operation == 'nodes' else [p['target']]
                    if operation != 'nodes': self._route(key,p['target'],strength,channels)
                    async with self.backend.node_locks.access(targets,mutable=False):
                        self._scope(key)
                        with self.backend._transaction_lock:
                            if operation == 'nodes':
                                current = list(network.walk_states(key[0],strength=strength,channels=channels))
                                if {n.node_id for n,_,_ in current} != set(targets): continue
                                return [dict(metadata=json_copy(n.get_metadata()),path=path,strength=left) for n,path,left in current]
                            target,path,left = self._route(key,p['target'],strength,channels)
                            if operation == 'metadata': return json_copy(target.get_metadata())
                            if operation == 'edges': return [json_copy(edge) for edge in target.interfaces]
                            if operation == 'tool_sources': return self._tool_sources(key[0],p['target'],strength=strength,channels=channels)
                            offers = getattr(self.backend,'external_tools',None)
                            if operation == 'visit':
                                return dict(metadata=json_copy(target.get_metadata()),path=path,strength=left,
                                    tools=offers.visit(key[0],target.node_id,strength=strength,channels=channels) if offers else [])
                            return self._query_tools(key,p['target'],strength,channels)
            request = AccessRequest(query());frame['children'].append(request)
            return request
        if operation in ('signal_status', 'signal_wait', 'signal_cancel'):
            if operation == 'signal_wait' and self.backend.node_locks.current:
                raise RuntimeError('Wait for independent signals after releasing node locks')
            signal_id = p['signal_id']
            record = network.signal_runs.get(signal_id)
            if not record or record['signal']['origin'] != key[0]:
                raise PermissionError('Only the emitting node can manage its signal receipt')
            if operation == 'signal_status': return self.backend.signals.status(signal_id)
            async def manage():
                self._scope(key)
                if operation == 'signal_wait':return await self.backend.signals.wait(signal_id)
                return await self.backend.signals.cancel(signal_id)
            request = AccessRequest(manage())
            frame['children'].append(request)
            return request
        if operation == 'caller': return frame['caller']
        if operation == 'requester': return frame['requester']
        if operation == 'local_metadata': return json_copy(node.get_metadata())
        if operation == 'publish_metadata':
            self.backend.node_locks.require_mutable(key[0])
            if not isinstance(p['fields'], dict): raise ValueError('Metadata fields must be an object')
            self._published[key] = json_copy(p['fields'])
            network.metadata_registry.register('module:' + repr(key),
                lambda target: self._metadata_fields(key, target))
            return None
        if operation == 'schema': return json_copy(node.get_schema())
        if operation == 'read': return json_copy(node.read(json_copy(p['request'])))
        if operation == 'write':
            self.backend.node_locks.require_mutable(key[0])
            return json_copy(node.write(p['key'], json_copy(p['value']), mode=p['mode']))
        if operation == 'inputs':
            self.backend.node_locks.require_mutable(key[0])
            def reject_files(value):
                if isinstance(value, dict):
                    if 'file' in value: raise PermissionError('Modules cannot load arbitrary document paths')
                    for item in value.values(): reject_files(item)
                elif isinstance(value, (list, tuple)):
                    for item in value: reject_files(item)
            patch = json_copy(p['patch']); reject_files(patch)
            if not hasattr(node, 'inputs'): raise TypeError('Only Agent nodes have input surfaces')
            return json_copy(node.inputs.update('module:' + key[1], patch))
        if operation == 'extended':
            handler = self._extension(key[1])
            policy = self._access[key].get('extension')
            if not handler or not policy or p['operation'] not in policy['operations']:
                raise PermissionError('Extended operation was not explicitly granted')
            arguments=json_copy(p['arguments'])
            async def extended():
                targets=[arguments[field] for field in ('source','target') if isinstance(arguments.get(field),str)]
                if p['operation']=='nodes':targets=[n for n in network.nodes if '*' in policy['targets'] or n in policy['targets']]
                async with self.backend.node_locks.access(targets,mutable=p['operation'] in ('connect','disconnect')):
                    self._scope(key)
                    value=handler(self.backend,key[0],policy,p['operation'],arguments)
                    if inspect.isawaitable(value):value=await value
                    return json_copy(value)
            request=AccessRequest(extended());frame['children'].append(request);return request
        if operation in ('call', 'invoke'):
            p = dict(p)
            p['arguments'] = json_copy(p['arguments'])
            p['strength'], p['channels'] = self._budget(key, p)
            # Schedule immediately: independent requests overlap even before awaited.
            async def invoke():
                async with self.backend.node_locks.access([p['target']]):
                    return await entered()
            async def entered():
                strength, channels = self._budget(key, p)
                target, _, _ = self._route(key, p['target'], strength, channels)
                if operation == 'call':
                    target_key = (p['target'], p['module'])
                    callee = self._check(target_key)
                    entry = callee.operations.get(p['operation'])
                    if entry is None: raise PermissionError('No accessible module operation')
                    function, declared = entry
                else:
                    if p['tool'].startswith('module:'):
                        from .module_tools import ModuleTools
                        module,separator,tool_id=p['tool'][7:].partition('/')
                        if not separator:raise ValueError('模块工具引用无效')
                        value=await ModuleTools(self.backend).invoke(key[0],dict(node_id=p['target'],module=module,tool_id=tool_id),p['arguments'],strength=strength,channels=channels)
                        self._scope(key);return value
                    if ':' in p['tool']:
                        value = await self.backend.external_tools.invoke(key[0], p['target'], p['tool'],
                            p['arguments'], strength=strength, channels=channels)
                        self._scope(key)
                        return value
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
            trace = frame['trace']
            if trace['calls'] >= 1000 or time.monotonic() >= trace['deadline']:
                raise RuntimeError('Access request resource budget exhausted')
            trace['calls'] += 1
            task = AccessRequest(invoke())
            frame['children'].append(task)
            return task
        strength, channels = self._budget(key, p)
        if operation == 'emit':
            from .signals import Signal
            allowed = {'kind', 'sequence', 'close_loop', 'failure_policy', 'max_hops', 'max_deliveries',
                       'timeout_seconds', 'node_timeout_seconds', 'parent_id'}
            if set(p['options']) - allowed: raise PermissionError('Module cannot override signal identity')
            signal = Signal(key[0], channels, strength, content=p['content'], **p['options'])
            return self.backend.signals.emit(signal)
        raise ValueError('Unknown local module request: ' + operation)

    def _query_tools(self, key, target_id, strength, channels):
        target, _, _ = self._route(key, target_id, strength, channels)
        result = []
        for name, definition in target.tool_definitions.items():
            if name not in target.expose or name not in target.tools: continue
            selected = tuple(c for c in channels if c in definition['access_channels'])
            if (definition['access_channels'] or target_id != key[0]) and not selected: continue
            try: _, path, remaining = self._route(key, target_id, strength, selected)
            except PermissionError: continue
            result.append(dict(**json_copy(definition), path=path, remaining_strength=remaining))
        if getattr(self.backend, 'external_tools', None):
            result.extend(self.backend.external_tools.visit(key[0], target.node_id, strength=strength, channels=channels, acquire=False))
        for (node_id,module),instance in self.instances.items():
            if node_id!=target_id:continue
            for tool in instance.definition.agent_tools.values():
                try:self._accessible(key[0],target_id,module,tool['operation'],strength,channels)
                except PermissionError:continue
                operation=instance.definition.operations[tool['operation']]
                result.append(dict(ref='module:'+module+'/'+tool['id'],name=tool['name'],description=tool['description'],parameters=thaw(operation['parameters'])))
        return result

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
        self.backend.node_locks.lifecycle()
        self.backend.network.node_locks=self.backend.node_locks
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
            self.backend.node_locks.lifecycle(node_id)
            node = self.backend.network.nodes[node_id]
            if name in node.modules: raise ValueError('Module already mounted')
            spec = validate_modules({name: dict(config={} if config is None else config,
                state={} if state is None else state, access={'strength': None, 'channels': []} if access is None else access)})[name]
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
            self.backend.node_locks.lifecycle(node_id)
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
                jobs = []; delivered = ModuleSignalContext(context.signal, context.delivery)
                for key in keys:
                    module = self._check(key, generations[key])
                    for channels, function in tuple(module.receivers):
                        if set(channels).intersection(context.signal.channels):
                            jobs.append(self._run(key, function, delivered))
                return await asyncio.gather(*jobs)
            runtime.bind(node.node_id, receive, access_strength=lambda keys=tuple(keys):max(self._strength(key) for key in keys))
            self._bindings.append((node.node_id, runtime))
