"""沿用原隔离编辑器：只在临时目录操作实际Dataer，不修改正式节点。"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from app.persistence.resource_data import write_data
from domain.core import MarkdownDataer
from .data_clear import supports,modules,roots,clear_node,cleared_entry,node_files

def preview(backend,p):
    original=deepcopy(p['node']);kind=original['type'];operation=p['operation'];arguments=p.get('arguments',{})
    if not supports(original):raise ValueError('该节点没有本地数据编辑器')
    if kind not in ('value','csv','sqlite','knowledge_collection','markdown') and operation!='clear':raise ValueError('该节点仅支持清空数据')
    if operation not in ('inspect','read','query','write','put','history','remove','restore','index','search','fetch','clear'):raise ValueError('未知数据编辑操作')
    writing=operation not in ('inspect','read','query','history','search','fetch')
    if writing and operation!='clear' and modules(original).get('data.local',{}).get('config',{}).get('read_only'):raise ValueError('此数据节点已配置为只读')
    if kind=='markdown' and writing and operation!='clear':raise ValueError('Markdown旧写入备份语义尚待迁移')
    parent=backend.directory/'studio/data-preview';parent.mkdir(parents=True,exist_ok=True)
    if not parent.resolve().is_relative_to(backend.directory):raise ValueError('临时数据目录越出工作区')
    with TemporaryDirectory(dir=parent) as temporary:
        home=Path(temporary).resolve();data=original.get('data',{});path=(home/data.get('path','')).resolve()
        if data and (not path.is_relative_to(home) or path==home):raise ValueError('节点数据目录越界')
        directory=data.get('directory',False)
        for name,content in p.get('files',{}).items():
            target=(home/name).resolve()
            if not target.is_relative_to(home):raise ValueError('数据文件路径越界')
            if data and (target==path or directory and target.is_relative_to(path) or kind=='markdown' and target==path.with_name(path.name+'.bak')):write_data(target,content)
        record=deepcopy(original);record.pop('tables',None);record['links']=[]
        node=backend.saver.build({'nodes':[record]},home).get(record['node_id'])
        if any(not root.is_relative_to(home) for root,_ in roots(node,home)):raise ValueError('节点数据目录越界')
        if operation=='clear':
            clear_node(node,home);original=cleared_entry(original)
            if kind=='markdown':write_data(path.with_name(path.name+'.bak'),None)
            result={'status':'ok','items':[]}
        elif isinstance(node.dataer,MarkdownDataer):
            if operation=='inspect':result={'kind':'markdown','key':'content','encoding':'utf-8','file_path':str(node.saver.path)}
            elif operation=='read':result={'status':'ok','items':[{'content':node.dataer.read()}]} if arguments['key']=='content' else {'status':'not_found','items':[]}
            else:raise ValueError('Markdown节点只支持按content主键读取')
        elif operation=='inspect':result=node.dataer.get_schema()
        elif operation=='read':result=asdict(node.dataer.read({'method':'key','key':arguments['key']}))
        elif operation=='query':result=asdict(node.dataer.read(arguments['request']))
        elif operation=='write':result=asdict(node.dataer.write(arguments['key'],arguments['value'],mode=arguments.get('mode','upsert')))
        else:result=asdict(node.dataer.write('$command',{'operation':operation,'arguments':arguments}))
        if isinstance(result,dict):
            for source in result.get('sources',[]):
                source.pop('backup_path',None)
                for label in ('file','file_path','database','storage_path'):
                    value=source.get(label)
                    if isinstance(value,str) and Path(value).is_absolute() and Path(value).is_relative_to(home):source[label]=Path(value).relative_to(home).as_posix()
        return dict(node=original,files=node_files(node,home),result=result,roots=[(root.relative_to(home).as_posix(),kind) for root,kind in roots(node,home)])
