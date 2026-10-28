"""Node-owned files, including application-managed text backups."""
from domain.core import DataNode


def resource_roots(node):
    if not isinstance(node, DataNode):
        return []
    path = node.saver.path.resolve()
    roots = [(path, path.is_dir())]
    if node.saver.kind == "markdown":
        roots.append((path.with_name(path.name + ".bak"), False))
    return roots
