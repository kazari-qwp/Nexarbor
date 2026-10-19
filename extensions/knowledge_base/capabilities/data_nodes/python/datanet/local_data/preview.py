"""操作员编辑草稿数据：临时目录内重建一个节点，不修改运行中的原件。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from datanet.core.component_registry import active_codecs,resource_roots,resource_paths
from datanet.core.resource_data import write_data,read_data

def preview(backend,p):
    original=deepcopy(p['node']);kind=original['type'];op=p['operation'];args=p.get('arguments',{})
    from .clear import supports,clear_node,cleared_entry
    if not supports(original):raise ValueError('该节点没有本地数据编辑器')
    if kind not in ('value','csv','sqlite','knowledge_collection','text_file') and op!='clear':raise ValueError('该节点仅支持清空数据')
    if op not in ('inspect','read','query','write','put','history','remove','restore','index','search','fetch','clear'):raise ValueError('未知数据编辑操作')
    writing=op not in ('inspect','read','query','history','search','fetch')
    if writing and op!='clear' and original.get('modules',{}).get('data.local',{}).get('config',{}).get('read_only'):raise ValueError('此数据节点已配置为只读')
    parent=backend.directory/'studio/data-preview';parent.mkdir(parents=True,exist_ok=True)
    temporary=TemporaryDirectory(dir=parent)
    try:
        home=Path(temporary.name).resolve();codec=active_codecs()[kind]
        node=codec.decode((original['node_id'],original['name'],original.get('data_kind')),original['parameters'],home)
        node.modules=deepcopy(original.get('modules',{}))
        roots=resource_roots(node)
        if any(not path.is_relative_to(home) for _,path,_ in roots):raise ValueError('节点数据目录越界')
        for name,content in p.get('files',{}).items():
            target=(home/name).resolve()
            if not target.is_relative_to(home):raise ValueError('数据文件路径越界')
            if any(target==path or typ=='directory' and target.is_relative_to(path) for _,path,typ in roots):write_data(target,content)
        if op=='clear':
            clear_node(node,home);original=cleared_entry(original,node,home);result={'status':'ok','items':[]}
        elif op=='inspect':result=node.get_schema()
        elif op=='read':result=asdict(node.read({'method':'key','key':args['key']}))
        elif op=='query':result=asdict(node.read(args['request']))
        elif op=='write':result=asdict(node.write(args['key'],args['value'],mode=args.get('mode','upsert')))
        else:result=asdict(node.write('$command',{'operation':op,'arguments':args}))
        if isinstance(result,dict):
            for source in result.get('sources',[]):
                source.pop('backup_path',None)
                for label in ('file','file_path','database','storage_path'):
                    value=source.get(label)
                    if isinstance(value,str):
                        path=Path(value)
                        if path.is_absolute() and path.is_relative_to(home):source[label]=path.relative_to(home).as_posix()
        if op!='clear':original['parameters']=codec.encode(node,home)
        files={path.relative_to(home).as_posix():read_data(path) for _,_,path in resource_paths(node)}
        return dict(node=original,files=files,result=result,roots=[(path.relative_to(home).as_posix(),kind) for _,path,kind in roots])
    finally:
        if not Path(temporary.name).resolve().is_relative_to(parent.resolve()):raise ValueError('临时节点数据清理目录越界')
        temporary.cleanup()
