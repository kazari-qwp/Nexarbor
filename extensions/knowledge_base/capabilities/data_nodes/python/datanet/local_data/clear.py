"""操作员清空节点数据；运行节点使用现有节点锁，模板仅操作隔离副本。"""
from copy import deepcopy
from pathlib import Path
import csv
import io
import shutil
import sqlite3
from datanet.core.component_registry import codec_for_node, resource_roots, resource_paths
from datanet.core.resource_data import read_data, write_data

DATA_TYPES = ('text_file', 'value', 'csv', 'sqlite', 'knowledge_collection', 'llamaindex')
RESOURCE_FIELDS = ('file_path', 'db_path', 'directory', 'storage_path')
RESERVED = {'studio', 'node_presets', 'network_presets', 'desktop-profile', '.git', 'checkpoints.sqlite3', 'runtime.lock', 'editor-library.json', 'editor-connection.json'}

def supports(node):
    return node['type'] in DATA_TYPES or 'knowledge.collection' in node.get('modules', {})

def binding(node):
    p = node['parameters']
    return (node['type'], {k: str(p[k]).replace('\\', '/') for k in RESOURCE_FIELDS if k in p}, p.get('table_name'), p.get('key_column'))

def owned(name, roots):
    path = Path(name)
    return any(path == Path(root) or kind == 'directory' and path.is_relative_to(Path(root)) for root, kind in roots)

def validate_roots(node, home):
    home = Path(home).resolve()
    for _, path, kind in resource_roots(node):
        if not path.is_relative_to(home) or path == home or path.relative_to(home).parts[0].casefold() in RESERVED:
            raise ValueError('节点数据清空范围越界，或指向工作区管理文件')
        # 先核对整棵树，再进行任何删除；不跟随符号链接或 Windows 目录联接。
        if kind == 'directory' and path.exists():
            for child in path.rglob('*'):
                if child.is_symlink() or getattr(child, 'is_junction', lambda: False)() or not child.resolve().is_relative_to(path):
                    raise ValueError('数据目录包含外部链接，不能整体清空')

def empty_directory(path):
    # 调用方已验证绝对路径是节点独占的、工作区内的目录。
    if path.exists():
        for child in path.iterdir():
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink()
    path.mkdir(parents=True, exist_ok=True)

def clear_node(node, home):
    validate_roots(node, home)
    kind = codec_for_node(node).type_id
    if kind == 'value': node.value = None
    elif kind == 'text_file': write_data(node.file_path, '')
    elif kind == 'csv':
        fields = next(csv.reader(io.StringIO(node.file_path.read_text('utf-8-sig'))), []) if node.file_path.exists() else [node.key_column, *[k for k in (node.dtype or {}) if k != node.key_column]]
        content = io.StringIO(newline=''); csv.writer(content).writerow(fields)
        write_data(node.file_path, content.getvalue())
    elif kind == 'sqlite':
        if node.db_path.exists():
            from datanet.components.nodes.sqlite_node.sqlite_node import quote_identifier
            db = sqlite3.connect(node.db_path)
            try:
                db.execute('PRAGMA secure_delete=ON')
                with db: db.execute('DELETE FROM ' + quote_identifier(node.table_name))
                db.execute('VACUUM')
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            finally: db.close()
    elif kind == 'knowledge_collection':
        # 保存集合定义，移除所有正文、修订、来源、索引；重新建立空集合。
        collections = []
        if (node.directory / 'catalog.sqlite3').exists():
            collections = node.store.catalog(limit=1000)
        empty_directory(node.directory)
        node.resources_restored()
        if collections:
            from datanet.knowledge.store import KnowledgeStore, encoded
            store = KnowledgeStore(node.directory, embedding_config=node.embedding)
            with store.connection() as db:
                for c in collections:
                    store._initialize_storage(c)
                    db.execute('INSERT INTO collections VALUES(?,?,?,?,?,?)', (c['id'], c['name'], c['storage'], c['description'], encoded(c['schema']), encoded(c['tags'])))
            node._store = store
    elif kind == 'llamaindex':
        empty_directory(node.storage_path); node.resources_restored()
    elif 'knowledge.collection' not in node.modules:
        raise ValueError('此节点不是文本或数据节点')
    if 'knowledge.collection' in node.modules:
        state = node.modules['knowledge.collection']['state']
        state['documents'] = {}; state['idempotency'] = {}

def cleared_entry(original, node, home):
    result = deepcopy(original)
    actual = codec_for_node(node).encode(node, home)
    if node.signal_type == 'value': result['parameters']['value'] = actual['value']
    if 'knowledge.collection' in node.modules:
        result['modules']['knowledge.collection']['state'] = deepcopy(node.modules['knowledge.collection']['state'])
    return result

async def clear_live(backend, p):
    original = deepcopy(p['node'])
    if not supports(original): raise ValueError('此节点不是文本或数据节点')
    node_id = original['node_id']; node = backend.network.nodes.get(node_id)
    actual = dict(type=codec_for_node(node).type_id, parameters=codec_for_node(node).encode(node, backend.directory)) if node else None
    if actual is None or binding(actual) != binding(original):
        from .preview import preview
        return dict(preview(backend, dict(p, operation='clear')), scope='draft')
    def validate():
        if backend.store.head != p.get('expected_commit'): raise ValueError('网络已变化，请刷新后清空数据')
        if backend.network.nodes.get(node_id) is not node or binding(dict(type=codec_for_node(node).type_id, parameters=codec_for_node(node).encode(node, backend.directory))) != binding(original):
            raise ValueError('节点存储配置已变化，请刷新后重试')
        validate_roots(node, backend.directory)
    roots = [(path.relative_to(backend.directory).as_posix(), kind) for _, path, kind in resource_roots(node)]
    tracked = []
    baseline = backend.store.read(p['expected_commit']) if p.get('expected_commit') == backend.store.head else None
    # .bak 不是活动正文，清空时也清掉它；出错时随事务恢复。
    backup = node.backup_path if original['type'] == 'text_file' else None
    backup_data = None; started = False
    if backup: roots.append((backup.relative_to(backend.directory).as_posix(), 'file'))
    try:
        async with backend.node_locks.transaction(node_id, [node_id], validate=validate):
            if backup:
                if any(backup == path or kind == 'directory' and backup.is_relative_to(path) for other in backend.network.nodes.values() if other is not node for _, path, kind in resource_roots(other)):
                    raise ValueError('文本备份由其他节点使用，不能单独清空')
                backup_data = read_data(backup)
            tracked = [name for name in backend.extension_state.get('document_resources', []) if owned(name, roots)]
            started = True
            clear_node(node, backend.directory)
            if backup: write_data(backup, None)
            backend.extension_state['document_resources'] = [name for name in backend.extension_state.get('document_resources', []) if not owned(name, roots)]
            result = dict(node=cleared_entry(original, node, backend.directory), files={path.relative_to(backend.directory).as_posix(): read_data(path) for _, _, path in resource_paths(node)}, roots=roots)
    except BaseException:
        backend.extension_state['document_resources'] = sorted(set(backend.extension_state.get('document_resources', [])) | set(tracked))
        if started and backup: write_data(backup, backup_data)
        raise
    # 只允许把本次清空接到草稿基线上。其他节点若同时变化，保留旧基线，
    # 后续应用会要求刷新，不会把其他执行者的新数据覆盖为旧草稿。
    def unrelated(snapshot):
        if snapshot is None:return None
        network=deepcopy(snapshot['network']);network['nodes']=[n for n in network['nodes'] if n['node_id']!=node_id]
        return network,{name:value for name,value in snapshot['files'].items() if not owned(name,roots)}
    with backend.store.mutex:
        commit=backend.store.head
        rebase_safe=unrelated(baseline)==unrelated(backend.store.read(commit))
    return dict(result, scope='live', commit=commit, rebase_safe=rebase_safe)
