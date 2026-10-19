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

    def routing_snapshot(self):
        locks = getattr(self, 'node_locks', None)
        from contextlib import nullcontext
        with locks.condition if locks else nullcontext():
            nodes = dict(self.nodes)
            routes = {key: locks.routing(key) if locks else (tuple(node.interfaces),node.divergence)
                      for key,node in nodes.items()}
            links={key:value[0] for key,value in routes.items()}
            links=self.connection_views(links)
            return nodes,links,{key:value[1] for key,value in routes.items()}

    def validate_ownership(self):
        for node in self.nodes.values():
            if node.signal_type!='subnode':continue
            if node.parent_id is not None and node.parent_id not in self.nodes:raise ValueError('亚节点的归属不存在：'+node.node_id)
            if node.divergence!=0 or node.data_kind is not None:raise ValueError('亚节点不能配置散度或本地数据')
            self.family_root(node.node_id)

    def family_root(self,node_id):
        seen=set();current=node_id
        while current in self.nodes:
            if current in seen:raise ValueError('亚节点归属不能形成环')
            seen.add(current);node=self.nodes[current]
            parent=(self.node_locks.ownership(current)['parent_id'] if hasattr(self,'node_locks') else getattr(node,'parent_id',None)) if node.signal_type=='subnode' else None
            if parent is None:return current
            current=parent
        return node_id

    def resolve_reference(self,origin,target):
        if target=='$self':return origin
        if target=='$parent':
            parent=self.node_locks.ownership(origin)['parent_id'] if hasattr(self,'node_locks') else getattr(self.nodes[origin],'parent_id',None)
            if parent is None:raise ValueError('当前对象没有父对象')
            return parent
        return target

    def same_family(self,left,right):
        return left in self.nodes and right in self.nodes and self.family_root(left)==self.family_root(right)

    def local_family(self,node_id):
        return [id for id in self.nodes if self.same_family(node_id,id)]

    def connection_views(self,stored):
        # stored 中每张表来自各自节点/亚节点，从不将私有表写回父节点。
        from .subnode import Subnode
        attrs={id:self.node_locks.ownership(id) if hasattr(self,'node_locks') else {k:getattr(node,k,None) for k in ('parent_id','use_parent_links','share_links')} for id,node in self.nodes.items()}
        children={id:[] for id in self.nodes}
        for id,node in self.nodes.items():
            if isinstance(node,Subnode) and attrs[id]['parent_id'] in children:children[attrs[id]['parent_id']].append(id)
        owned_cache={};view_cache={}
        def unique(edges):return tuple(edge for i,edge in enumerate(edges) if edge not in edges[:i])
        def owned(id,seen):
            if id in seen:raise ValueError('亚节点归属不能形成环')
            if id in owned_cache:return owned_cache[id]
            edges=list(stored[id])
            for child in children[id]:
                if attrs[child]['share_links']:edges.extend(owned(child,seen|{id}))
            owned_cache[id]=unique(edges);return owned_cache[id]
        def view(id,seen):
            if id in seen:raise ValueError('亚节点归属不能形成环')
            if id in view_cache:return view_cache[id]
            edges=list(owned(id,set()));node=self.nodes[id]
            if isinstance(node,Subnode) and attrs[id]['use_parent_links'] and attrs[id]['parent_id'] in stored:edges.extend(view(attrs[id]['parent_id'],seen|{id}))
            view_cache[id]=unique(edges);return view_cache[id]
        return {id:view(id,set()) for id in stored}

    def channel_names(self):
        # 黑名单在访问开始时针对当前已声明频道求值，未排除的现有频道全部可匹配。
        found=set()
        def scan(value,key=''):
            if isinstance(value,dict):
                for name,item in value.items():scan(item,name)
            elif isinstance(value,(list,tuple)):
                if 'channels' in key:found.update(c for c in value if isinstance(c,str))
                else:
                    for item in value:scan(item,key)
        for node in self.nodes.values():
            scan(node.modules);scan(node.execution_binding or {});scan(node.offered_tools)
            for edge in node.interfaces:found.update(edge.metadata.channels)
            for spec in node.tool_definitions.values():found.update(spec['access_channels'])
        if hasattr(self,'module_channel_names'):found.update(self.module_channel_names())
        return tuple(sorted(found))

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
        nodes, links, divergences = self.routing_snapshot()
        layer = [(node_id, [node_id], strength)]
        visited = set()
        while layer:
            layer = [(current, path, remaining) for current, path, remaining in layer if current not in visited]
            visited.update((current for current, _, _ in layer))
            for current, path, remaining in layer:
                node = nodes[current]
                yield (node, path, remaining)
            if scope == 'local':
                return
            pending = {}
            for current, path, remaining in layer:
                for interface in links[current]:
                    if interface.target_node_id in visited:
                        continue
                    if not interface.allows(strength=remaining,channels=channels):
                        continue
                    target = nodes.get(interface.target_node_id)
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
                remaining = total + divergences[target_id]
                validate_signal(remaining)
                if remaining>=0:layer.append((target_id,path,remaining))
