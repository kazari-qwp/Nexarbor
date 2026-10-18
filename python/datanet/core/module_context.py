"""Node-local capability API for trusted Python, not a Python/OS sandbox."""
from dataclasses import dataclass
from .interface import validate_strength
from .json_values import freeze, names


def validate_access(value):
    if not isinstance(value, dict) or not {'strength', 'channels'} <= value.keys():
        raise ValueError('Module access requires strength and channels')
    if set(value) - {'strength', 'channels', 'extension'}:
        raise ValueError('Unknown module access field')
    validate_strength(value['strength'])
    names(value['channels'], 'module channels')
    if 'extension' in value:
        policy = value['extension']
        if not isinstance(policy, dict) or set(policy) != {'operations', 'targets'}:
            raise ValueError('Extended access requires explicit operations and targets')
        names(policy['operations'], 'extended operations')
        names(policy['targets'], 'extended targets')
    freeze(value)
    return value


@dataclass(frozen=True)
class ModuleSignalContext:
    """Delivered data only: deliberately has no Network reference."""
    signal: object
    delivery: object

    @property
    def receipt_id(self):
        return self.signal.signal_id + ':' + self.delivery.node_id


class ModuleNetwork:
    __slots__ = ('_request',)

    def __init__(self, request): self._request = request
    def nodes(self, *, channels=None, strength=None):
        return self._request('nodes', channels=channels, strength=strength)
    def metadata(self, target, *, channels=None, strength=None):
        return self._request('metadata', target=target, channels=channels, strength=strength)
    def tools(self, target, *, strength=None):
        return self._request('tools', target=target, strength=strength)
    async def invoke(self, target, tool, arguments=None, *, strength=None):
        return await self._request('invoke', target=target, tool=tool,
                             arguments={} if arguments is None else arguments, strength=strength)
    async def call(self, target, module, operation, arguments=None, *, strength=None):
        return await self._request('call', target=target, module=module, operation=operation,
                             arguments={} if arguments is None else arguments, strength=strength)
    async def emit(self, *, channels=None, strength=None, content=None, **options):
        return await self._request('emit', channels=channels, strength=strength,
                                   content=content, options=options)


class ModuleContext:
    __slots__ = ('_request', '_node_id', '_module_id', '_config', '_state', '_network')
    def __init__(self, request, node_id, module_id, config, state):
        self._request = request
        self._node_id, self._module_id = node_id, module_id
        self._config, self._state = freeze(config), state
        self._network = ModuleNetwork(request)
    node_id = property(lambda self: self._node_id)
    module_id = property(lambda self: self._module_id)
    config = property(lambda self: self._config)
    state = property(lambda self: self._state)
    network = property(lambda self: self._network)
    caller_id = property(lambda self: self._request('caller'))
    def metadata(self): return self._request('local_metadata')
    def publish_metadata(self, fields): return self._request('publish_metadata', fields=fields)
    def read(self, request): return self._request('read', request=request)
    def write(self, key, value, *, mode='upsert'):
        return self._request('write', key=key, value=value, mode=mode)
    def update_inputs(self, patch): return self._request('inputs', patch=patch)
    def register_tool(self, name, function, **definition):
        return self._request('register_tool', name=name, function=function, definition=definition)
    def register_operation(self, name, function, *, channels=()):
        return self._request('register_operation', name=name, function=function, channels=channels)
    def receive(self, channels, function):
        return self._request('receive', channels=channels, function=function)


class ExtendedModuleContext(ModuleContext):
    """Only a host-registered official module gets this additional port."""
    __slots__ = ()
    def extended(self, operation, arguments=None):
        return self._request('extended', operation=operation,
                             arguments={} if arguments is None else arguments)
