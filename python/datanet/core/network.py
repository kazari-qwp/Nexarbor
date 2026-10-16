"""按连接门槛与可见性访问；读取聚合，写入只命中指定目标。"""
from datanet.core.node import NodeResult
from datanet.core.interface import validate_strength, validate_signal
from datanet.core.access_budget import current_access, access_context, active_agent

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

    def walk(self, node_id, *, direction='read', strength=0, scope='network'):
        for node, path, remaining in self.walk_states(node_id, direction=direction, strength=strength, scope=scope):
            yield (node, path)

    def walk_states(self, node_id, *, direction='read', strength=0, scope='network'):
        validate_strength(strength)
        if scope not in ('local', 'network'):
            raise ValueError('scope 必须为 local 或 network')
        if direction not in ('read', 'write'):
            raise ValueError('direction 必须为 read 或 write')
        if not isinstance(node_id, str):
            raise TypeError('起点编号必须为字符串')
        if node_id not in self.nodes:
            raise ValueError(f'起点不存在：{node_id}')
        frame = current_access.get()
        inherited = frame is not None and frame['network'] is self
        if inherited:
            if node_id != frame['node_id']:
                raise ValueError('嵌套访问必须从当前执行节点出发')
            strength = frame['strength']
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
                for interface in getattr(node, direction + '_interfaces'):
                    if interface.target_node_id in visited:
                        continue
                    if not interface.allows(origin_node_id=node_id, source_node_id=current, strength=remaining):
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
                layer.append((target_id, path, remaining))

    def read(self, node_id, request, scope='network', data_kind=None, *, strength=0):
        from datanet.core.read_request import validate_request
        request = validate_request(request)
        validate_strength(strength)
        if scope not in ('local', 'network'):
            raise ValueError('scope 必须为 local 或 network')
        if not isinstance(node_id, str):
            raise TypeError('起点编号必须为字符串')
        if node_id not in self.nodes:
            return NodeResult(status='error', errors=[f'节点不存在：{node_id}'])
        result, successful, supported = (NodeResult(), False, False)
        try:
            for node, path, remaining in self.walk_states(node_id, strength=strength, scope=scope):
                if data_kind is not None and node.data_kind != data_kind:
                    continue
                with access_context(self, node.node_id, remaining, path):
                    local = node.read(request)
                if local is None:
                    continue
                if local.status == 'unsupported':
                    if scope == 'local':
                        return local
                    result.skipped.append({'node_id': node.node_id, 'reason': 'unsupported', 'retrieval_path': path.copy()})
                else:
                    supported = True
                if local.status == 'ok':
                    successful = True
                elif local.status not in ('unsupported', 'not_found'):
                    result.errors.extend(local.errors or [f'节点 {node.node_id} 读取失败：{local.status}'])
                result.items.extend(local.items)
                result.sources.extend(({**source, 'retrieval_path': path.copy(), 'remaining_strength': remaining} for source in local.sources))
                result.skipped.extend(local.skipped)
        except ValueError as error:
            result.errors.append(str(error))
        result.status = 'error' if result.errors else 'ok' if successful else 'unsupported' if result.skipped and (not supported) else 'not_found'
        return result

    def write(self, node_id, target_node_id, key, value, *, strength=0, mode='upsert', scope='network'):
        from datanet.core.write_support import validate_write
        validate_write(key, mode, allow_append=True)
        validate_strength(strength)
        if scope not in ('local', 'network'):
            raise ValueError('scope 必须为 local 或 network')
        if not isinstance(node_id, str) or not isinstance(target_node_id, str):
            raise TypeError('起点和目标编号必须为字符串')
        if node_id not in self.nodes or target_node_id not in self.nodes:
            return NodeResult(status='error', errors=['起点或目标节点不存在'])
        try:
            for node, path, remaining in self.walk_states(node_id, direction='write', strength=strength, scope=scope):
                if node.node_id == target_node_id:
                    with access_context(self, node.node_id, remaining, path):
                        result = node.write(key, value, mode=mode)
                    result.sources = [{**source, 'write_path': path.copy()} for source in result.sources]
                    return result
        except ValueError as error:
            return NodeResult(status='error', errors=[str(error)])
        return NodeResult(status='forbidden', errors=['目标不在当前写入范围内'])
