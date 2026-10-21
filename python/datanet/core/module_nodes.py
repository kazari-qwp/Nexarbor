"""Objects reached by one channel traversal. Reading their tables never routes again."""
import inspect
from collections.abc import Sequence
from .access_request import AccessRequest
from .module_values import json_copy
from .json_values import thaw


class ReachedModule:
    def __init__(self, node, name, instance):
        self.node, self.name, self.instance = node, name, instance

    @property
    def config(self): return thaw(self.instance.config)
    @property
    def state(self): return json_copy(self.instance.state)
    @property
    def operations(self): return tuple(self.instance.operations)

    def call(self, operation, arguments=None):
        return self.node._schedule(lambda: self.node._runtime.call(
            self.node.node_id, self.name, operation,
            {} if arguments is None else arguments))


class ReachedNode:
    """An actual reached node, with its local module and public tool tables.

    Graph channels/strength are evaluated by nodes(), once. Ordinary node locks
    still coordinate data access; there is no second path/permission query here.
    """
    def __init__(self, runtime, key, node, path, strength, channels, instances):
        self._runtime, self._key, self._node = runtime, key, node
        self.path, self.strength, self._channels = tuple(path), strength, tuple(channels)
        self.modules = {name: ReachedModule(self, name, instance) for name, instance in instances if instance.active}

    @property
    def node_id(self): return self._node.node_id
    @property
    def name(self): return self._node.name
    @property
    def node_type(self): return self._node.signal_type
    @property
    def metadata(self): return json_copy(self._node.get_metadata())

    @property
    def edges(self): return [json_copy(edge) for edge in self._node.interfaces]

    @property
    def tools(self):
        node = self._node
        result = [dict(ref=name, **json_copy(spec)) for name, spec in node.tool_definitions.items()
                  if name in node.expose and name in node.tools
                  and (set(spec['access_channels']).intersection(self._channels)
                       or not spec['access_channels'] and node.node_id == self._key[0])]
        external = getattr(self._runtime.backend, 'external_tools', None)
        if external:
            for offer in node.offered_tools:
                spec = external._catalog.get(offer['ref'])
                if spec is not None and set(offer['channels']).intersection(self._channels):
                    result.append(thaw(spec))
        for name, module in self.modules.items():
            definition = module.instance.definition
            for tool in definition.agent_tools.values():
                operation = definition.operations[tool['operation']]
                declared = operation['channels']
                if isinstance(declared, dict):
                    from .channel_filters import resolve
                    field = declared['config']
                    default = definition.config_schema.get('properties', {}).get(field, {}).get('default', [])
                    declared = resolve(module.config.get(field, default), module.config.get('channel_modes', {}).get(field, 'allow'), self._channels)
                if not set(declared).intersection(self._channels) and not (not declared and node.node_id == self._key[0]): continue
                result.append(dict(ref='module:'+name+'/'+tool['id'], name=tool['name'],
                    description=tool['description'], parameters=thaw(operation['parameters'])))
        return result

    def _schedule(self, function, *, mutable=True):
        frame = self._runtime._scope(self._key)
        async def run():
            async with self._runtime.backend.node_locks.access([self.node_id], mutable=mutable):
                value = function()
                if inspect.isawaitable(value): value = await value
                return json_copy(value)
        request = AccessRequest(run())
        frame['children'].append(request)
        return request

    def read(self, request):
        return self._schedule(lambda: self._node.read(request), mutable=False)

    def write(self, key, value, *, mode='upsert'):
        return self._schedule(lambda: self._node.write(key, value, mode=mode))

    def call(self, module, operation, arguments=None):
        return self.modules[module].call(operation, arguments)


class ReachedNodes(Sequence):
    """BFS order when iterated; node ID lookup without another network search."""
    def __init__(self, nodes):
        self._ordered = tuple(nodes)
        self._by_id = {node.node_id: node for node in self._ordered}
    def __len__(self): return len(self._ordered)
    def __iter__(self): return iter(self._ordered)
    def __getitem__(self, key):
        return self._by_id[key] if isinstance(key, str) else self._ordered[key]
    def get(self, key, default=None): return self._by_id.get(key, default)
    def values(self): return iter(self._ordered)
    def items(self): return self._by_id.items()
