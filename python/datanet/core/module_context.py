"""Node-local capability API for trusted Python, not a Python/OS sandbox."""
from dataclasses import dataclass
from .interface import validate_strength
from .json_values import freeze, names


def validate_access(value):
    if not isinstance(value, dict) or not {'strength', 'channels'} <= value.keys():
        raise ValueError('Module access requires strength and channels')
    if set(value) - {'strength', 'channels', 'extension', 'channel_mode'}:
        raise ValueError('Unknown module access field')
    if value['strength'] is not None:validate_strength(value['strength'])
    names(value['channels'], 'module channels')
    if 'extension' in value:
        policy = value['extension']
        if not isinstance(policy, dict) or set(policy) != {'operations', 'targets'}:
            raise ValueError('Extended access requires explicit operations and targets')
        names(policy['operations'], 'extended operations')
        names(policy['targets'], 'extended targets')
    from .channel_filters import mode
    mode(value.get('channel_mode','allow'))
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
        """Return reached node objects in BFS order; their tables/data read directly."""
        return self._request('nodes', channels=channels, strength=strength)
    def modules(self, module=None, *, channels=None, strength=None):
        return self._request('module_endpoints',module=module,channels=channels,strength=strength)
    def metadata(self, target, *, channels=None, strength=None):
        return self._request('metadata', target=target, channels=channels, strength=strength)
    def read(self, target, request, *, channels=None, strength=None):
        """Read a reachable node's data through the current channel/strength budget."""
        return self._request('node_read', target=target, request=request, channels=channels, strength=strength)
    def edges(self, target, *, channels=None, strength=None):
        return self._request('edges', target=target, channels=channels, strength=strength)
    def patch_edges(self, changes, *, channels=None, strength=None):
        return self._request('patch_edges', changes=changes, channels=channels, strength=strength)
    def tools(self, target, *, channels=None, strength=None):
        return self._request('tools', target=target, channels=channels, strength=strength)
    def invoke(self, target, tool, arguments=None, *, channels=None, strength=None):
        return self._request('invoke', target=target, tool=tool,
                             arguments={} if arguments is None else arguments, channels=channels, strength=strength)
    def call(self, target, module, operation, arguments=None, *, channels=None, strength=None, forward=False):
        return self._request('call', target=target, module=module, operation=operation,
                             arguments={} if arguments is None else arguments, channels=channels, strength=strength, forward=forward)
    def emit(self, *, channels=None, strength=None, content=None, **options):
        return self._request('emit', channels=channels, strength=strength,
                                   content=content, options=options)
    def post(self,target,module,operation,arguments=None,*,channels=None,strength=None):
        """当前信号层追踪的后续访问：立即返回，换层前等待完成。"""
        return self._request('post',target=target,module=module,operation=operation,arguments={} if arguments is None else arguments,channels=channels,strength=strength)
    def visit(self, target, *, channels=None, strength=None):
        return self._request('visit', target=target, channels=channels, strength=strength)
    def tool_sources(self, target, *, channels=None, strength=None):
        return self._request('tool_sources', target=target, channels=channels, strength=strength)
    def lock_nodes(self, nodes, *, channels=None, strength=None, timeout=30):
        """async with this scope: commit on success, restore internal state on error."""
        return self._request('lock_nodes', nodes=nodes, channels=channels, strength=strength, timeout=timeout)
    def signal_status(self, signal_id): return self._request('signal_status', signal_id=signal_id)
    def wait_signal(self, signal_id): return self._request('signal_wait', signal_id=signal_id)
    def cancel_signal(self, signal_id): return self._request('signal_cancel', signal_id=signal_id)


class ModuleLocal:
    __slots__=('_request',)
    def __init__(self,request):self._request=request
    def call(self,module,operation,arguments=None,*,target=None):
        return self._request('local_call',module=module,operation=operation,arguments={} if arguments is None else arguments,target=target)

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
    @property
    def state(self):
        from .node_locks import require_transaction_node
        require_transaction_node(self._node_id)
        return self._state
    network = property(lambda self: self._network)
    nodes = property(lambda self: self._request('nodes', channels=None, strength=None, reuse=True))
    local = property(lambda self: ModuleLocal(self._request))
    call_path = property(lambda self: self._request('call_path'))
    def resolve_channels(self,values,mode='allow'):return self._request('resolve_channels',values=list(values),mode=mode)
    def filter_channels(self, field, default=()):return self._request('filter_channels',field=field,default=list(default))
    signal_id = property(lambda self: self._request('signal_id'))
    caller_id = property(lambda self: self._request('caller'))
    requester_id = property(lambda self: self._request('requester'))
    def metadata(self): return self._request('local_metadata')
    def publish_metadata(self, fields): return self._request('publish_metadata', fields=fields)
    def schema(self): return self._request('schema')
    def read(self, request): return self._request('read', request=request)
    def write(self, key, value, *, mode='upsert'):
        return self._request('write', key=key, value=value, mode=mode)
    def update_inputs(self, patch): return self._request('inputs', patch=patch)


class ExtendedModuleContext(ModuleContext):
    """Only a host-registered official module gets this additional port."""
    __slots__ = ()
    def extended(self, operation, arguments=None):
        return self._request('extended', operation=operation,
                             arguments={} if arguments is None else arguments)
