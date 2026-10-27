"""已取得节点引用上的连接批量变更；由当前节点事务提供隔离与回滚。"""

from app.transactions.locks import require_transaction_node


def _same(left, right):
    return (left.target_id, left.channels, left.threshold, left.processor, left.channel_mode, getattr(left, 'attributes', {})) == (right.target_id, right.channels, right.threshold, right.processor, right.channel_mode, getattr(right, 'attributes', {}))


def apply_edges(changes):
    pending = {}
    for node, action, edge in changes:
        require_transaction_node(node.info.node_id)
        edges = pending.setdefault(node, list(node.links))
        if action == 'remove':edges[:] = [existing for existing in edges if not _same(existing, edge)]
        elif not any(_same(existing, edge) for existing in edges):edges.append(edge)
    for node, edges in pending.items():node.links._links[:] = edges
