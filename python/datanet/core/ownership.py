"""Containment and independent connection tables; no scheduling or module policy."""
class Ownership:
    def __init__(self,network):
        self.network=network

    def validate(self):
        for node in self.network.nodes.values():
            if node.signal_type!='subnode':continue
            if node.parent_id is not None and node.parent_id not in self.network.nodes:raise ValueError('亚节点的归属不存在：'+node.node_id)
            if node.divergence!=0 or node.data_kind is not None:raise ValueError('亚节点不能配置散度或本地数据')
            self.family_root(node.node_id)

    def family_root(self,node_id):
        seen=set();current=node_id
        while current in self.network.nodes:
            if current in seen:raise ValueError('亚节点归属不能形成环')
            seen.add(current);node=self.network.nodes[current]
            parent=(self.network.node_locks.ownership(current)['parent_id'] if hasattr(self.network,'node_locks') else getattr(node,'parent_id',None)) if node.signal_type=='subnode' else None
            if parent is None:return current
            current=parent
        return node_id

    def resolve_reference(self,origin,target):
        if target=='$self':return origin
        if target=='$parent':
            parent=self.network.node_locks.ownership(origin)['parent_id'] if hasattr(self.network,'node_locks') else getattr(self.network.nodes[origin],'parent_id',None)
            if parent is None:raise ValueError('当前对象没有父对象')
            return parent
        return target

    def same_family(self,left,right):
        return left in self.network.nodes and right in self.network.nodes and self.family_root(left)==self.family_root(right)

    def local_family(self,node_id):
        return [id for id in self.network.nodes if self.same_family(node_id,id)]

    def connection_views(self,stored):
        # stored 中每张表来自各自节点/亚节点，从不将私有表写回父节点。
        from .subnode import Subnode
        attrs={id:self.network.node_locks.ownership(id) if hasattr(self.network,'node_locks') else {k:getattr(node,k,None) for k in ('parent_id','use_parent_links','share_links')} for id,node in self.network.nodes.items()}
        children={id:[] for id in self.network.nodes}
        for id,node in self.network.nodes.items():
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
            edges=list(owned(id,set()));node=self.network.nodes[id]
            if isinstance(node,Subnode) and attrs[id]['use_parent_links'] and attrs[id]['parent_id'] in stored:edges.extend(view(attrs[id]['parent_id'],seen|{id}))
            view_cache[id]=unique(edges);return view_cache[id]
        return {id:view(id,set()) for id in stored}
