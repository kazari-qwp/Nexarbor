"""按频道交集与强度访问；工具调用采用可信声明的频道。"""
from datanet.core.interface import validate_strength, validate_signal
from datanet.core.access_budget import current_access, active_agent

class Network:

    def __init__(self):
        from .metadata import MetadataRegistry
        self.metadata_registry = MetadataRegistry()
        self.nodes = {}
        self.delegation_permissions = {}
        self.signal_runs = {}

    @property
    def signals(self):
        if not hasattr(self,'_signal_runtime'):
            from .signal_runtime import SignalRuntime
            self._signal_runtime=SignalRuntime(self)
        return self._signal_runtime

    async def propagate(self,signal):
        return await self.signals.propagate(signal)

    def add_node(self, node):
        if node.node_id in self.nodes:
            raise ValueError(f'节点编号重复：{node.node_id}')
        self.nodes[node.node_id] = node
        node._metadata_registry = self.metadata_registry
        if hasattr(node, 'bind_network'):
            node.bind_network(self)

    def get_metadata(self, node_id):return self.nodes[node_id].get_metadata()

    def use_metadata_registry(self, registry):
        self.metadata_registry = registry
        for node in self.nodes.values():node._metadata_registry = registry

    def walk(self, node_id, *, channels=(), strength=0, scope='network'):
        for node, path, remaining in self.walk_states(node_id, channels=channels, strength=strength, scope=scope):
            yield (node, path)

    def walk_states(self, node_id, *, channels=(), strength=0, scope='network'):
        validate_strength(strength)
        if scope not in ('local', 'network'):
            raise ValueError('scope 必须为 local 或 network')
        from .json_values import names
        channels=names(channels,'channels')
        if not isinstance(node_id, str):
            raise TypeError('起点编号必须为字符串')
        if node_id not in self.nodes:
            raise ValueError(f'起点不存在：{node_id}')
        frame = current_access.get()
        inherited = frame is not None and frame['network'] is self
        if inherited:
            if node_id != frame['node_id']:
                raise ValueError('嵌套访问必须从当前执行节点出发')
            strength = min(strength, frame['strength'])
            if not set(channels)<=set(frame['channels']):raise ValueError('嵌套访问不能扩大访问频道')
        else:
            acting = active_agent.get()
            if acting is not None:
                agent, origin = acting
                if node_id != origin:
                    raise ValueError('Agent 主动访问必须从所属节点出发')
                if strength > agent.max_signal_strength:
                    raise ValueError(f'主动请求强度 {strength} 超过 Agent 上限 {agent.max_signal_strength}')
        layer = [(node_id, [node_id], strength)]
        visited = set()
        if inherited:
            visited.update(frame['visited'] - {node_id})
        while layer:
            layer = [(current, path, remaining) for current, path, remaining in layer if current not in visited]
            visited.update((current for current, _, _ in layer))
            for current, path, remaining in layer:
                node = self.nodes[current]
                yield (node, path, remaining)
            if scope == 'local':
                return
            pending = {}
            for current, path, remaining in layer:
                node = self.nodes[current]
                for interface in node.interfaces:
                    if interface.target_node_id in visited:
                        continue
                    if not interface.allows(strength=remaining,channels=channels):
                        continue
                    target = self.nodes.get(interface.target_node_id)
                    if target is None:
                        raise ValueError(f'接口目标不存在：{interface.target_node_id}')
                    signal = remaining * interface.metadata.multiplier
                    validate_strength(signal)
                    if target.node_id not in pending:
                        pending[target.node_id] = [0, [*path, target.node_id]]
                    pending[target.node_id][0] += signal
                    validate_strength(pending[target.node_id][0])
            layer = []
            for target_id, (total, path) in pending.items():
                remaining = total + self.nodes[target_id].divergence
                validate_signal(remaining)
                if remaining>=0:layer.append((target_id,path,remaining))
