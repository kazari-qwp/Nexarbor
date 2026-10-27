"""操作员数据清空；保留原节点事务、存储边界和草稿重定位规则。"""
from copy import deepcopy
from pathlib import Path
import csv
import io
import shutil
import sqlite3
from app.persistence.resource_data import read_data,write_data,resource_files
from domain.core import DataNode

RESERVED={'studio','node_presets','network_presets','desktop-profile','.git','checkpoints.sqlite3','runtime.lock','editor-library.json','editor-connection.json'}

def modules(record):return {item['module_id']:item for item in record.get('tables',{}).get('modules',[])}
def supports(record):return record.get('type')!='agent' and bool(record.get('data')) or 'knowledge.collection' in modules(record)
def binding(record):
    data=record.get('data',{});parameters=data.get('parameters',{})
    return record['type'],data.get('type'),str(data.get('path','')).replace('\\','/'),data.get('directory',False),parameters.get('table_name'),parameters.get('key_column')
def owned(name,roots):
    path=Path(name)
    return any(path==Path(root) or kind=='directory' and path.is_relative_to(Path(root)) for root,kind in roots)
def roots(node,home):
    if not isinstance(node,DataNode):return []
    path=node.saver.path.resolve();result=[(path,'directory' if path.is_dir() else 'file')]
    if node.saver.kind=='markdown':result.append((path.with_name(path.name+'.bak'),'file'))
    return result

def validate_roots(node,home):
    home=Path(home).resolve()
    for path,kind in roots(node,home):
        if not path.is_relative_to(home) or path==home or path.relative_to(home).parts[0].casefold() in RESERVED:raise ValueError('节点数据清空范围越界，或指向工作区管理文件')
        if kind=='directory' and path.exists():
            for child in path.rglob('*'):
                if child.is_symlink() or getattr(child,'is_junction',lambda:False)() or not child.resolve().is_relative_to(path):raise ValueError('数据目录包含外部链接，不能整体清空')

def empty_directory(path):
    if path.exists():
        for child in path.iterdir():
            if child.is_dir():shutil.rmtree(child)
            else:child.unlink()
    path.mkdir(parents=True,exist_ok=True)

def clear_node(node,home):
    validate_roots(node,home)
    if not isinstance(node,DataNode):return
    kind=node.saver.kind;dataer=node.dataer
    if kind=='value':dataer.write('value',None)
    elif kind=='markdown':dataer.write('')
    elif kind=='csv':
        fields=next(csv.reader(io.StringIO(dataer.file_path.read_text('utf-8-sig'))),[]) if dataer.file_path.exists() else [dataer.key_column,*[key for key in dataer.dtype if key!=dataer.key_column]]
        content=io.StringIO(newline='');csv.writer(content).writerow(fields);write_data(dataer.file_path,content.getvalue())
    elif kind=='sqlite':
        if dataer.db_path.exists():
            from projects.knowledge_archive.nodes.sqlite import quote_identifier
            db=sqlite3.connect(dataer.db_path)
            try:
                db.execute('PRAGMA secure_delete=ON')
                with db:db.execute('DELETE FROM '+quote_identifier(dataer.table_name))
                db.execute('VACUUM');db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            finally:db.close()
    elif kind=='knowledge_collection':
        collections=dataer.store.catalog(limit=1000) if (dataer.directory/'catalog.sqlite3').exists() else []
        empty_directory(dataer.directory);dataer.resources_restored()
        if collections:
            from projects.knowledge_archive.storage.knowledge import KnowledgeStore,encoded
            store=KnowledgeStore(dataer.directory,embedding_config=dataer.embedding)
            with store.connection() as db:
                for collection in collections:
                    store._initialize_storage(collection)
                    db.execute('INSERT INTO collections VALUES(?,?,?,?,?,?)',(collection['id'],collection['name'],collection['storage'],collection['description'],encoded(collection['schema']),encoded(collection['tags'])))
            dataer._store=store
    elif kind=='llamaindex':
        empty_directory(dataer.storage_path);dataer.resources_restored()
    else:raise ValueError('此节点不是文本或数据节点')

def cleared_entry(original):
    result=deepcopy(original);module=modules(result).get('knowledge.collection')
    if module is not None:module['state'].update(documents={},idempotency={})
    return result

def node_files(node,home):return {path.relative_to(home).as_posix():read_data(path) for root,_ in roots(node,home) for path in resource_files(root)}

async def clear_live(backend,p):
    original=deepcopy(p['node'])
    if not supports(original):raise ValueError('此节点不是文本或数据节点')
    node_id=original['node_id'];node=backend.network.get(node_id)
    actual=backend.saver._encode_node(node,backend.directory,None,'network_data') if node else None
    if actual is None or binding(actual)!=binding(original):
        from .data_preview import preview
        return dict(preview(backend,{**p,'operation':'clear'}),scope='draft')
    def validate():
        if backend.store.head!=p.get('expected_commit'):raise ValueError('网络已变化，请刷新后清空数据')
        current=backend.saver._encode_node(node,backend.directory,None,'network_data')
        if backend.network.get(node_id) is not node or binding(current)!=binding(original):raise ValueError('节点存储配置已变化，请刷新后重试')
        validate_roots(node,backend.directory)
    relative=[(path.relative_to(backend.directory).as_posix(),kind) for path,kind in roots(node,backend.directory)]
    tracked=[];baseline=backend.store.read(p['expected_commit']) if p.get('expected_commit')==backend.store.head else None
    backup=node.saver.path.with_name(node.saver.path.name+'.bak') if isinstance(node,DataNode) and node.saver.kind=='markdown' else None
    backup_data=None;started=False
    try:
        async with backend.node_locks.transaction([node_id],validate=validate):
            if backup:
                if any(backup==path or kind=='directory' and backup.is_relative_to(path) for other in backend.network if other is not node for path,kind in roots(other,backend.directory)):raise ValueError('文本备份由其他节点使用，不能单独清空')
                backup_data=read_data(backup)
            tracked=[name for name in backend.extension_state.get('document_resources',[]) if owned(name,relative)];started=True
            clear_node(node,backend.directory)
            module=node.modules.get('knowledge.collection')
            if module is not None:module.state.update(documents={},idempotency={})
            if backup:write_data(backup,None)
            backend.extension_state['document_resources']=[name for name in backend.extension_state.get('document_resources',[]) if not owned(name,relative)]
            result=dict(node=cleared_entry(original),files=node_files(node,backend.directory),roots=relative)
    except BaseException:
        backend.extension_state['document_resources']=sorted(set(backend.extension_state.get('document_resources',[]))|set(tracked))
        if started and backup:write_data(backup,backup_data)
        raise
    def unrelated(snapshot):
        if snapshot is None:return None
        network=deepcopy(snapshot['network']);network['nodes']=[entry for entry in network['nodes'] if entry['node_id']!=node_id]
        return network,{name:value for name,value in snapshot['files'].items() if not owned(name,relative)}
    with backend.store.mutex:
        commit=backend.store.head;rebase_safe=unrelated(baseline)==unrelated(backend.store.read(commit))
    return dict(result,scope='live',commit=commit,rebase_safe=rebase_safe)
