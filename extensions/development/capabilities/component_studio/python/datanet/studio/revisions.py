"""从咨询快照建立独立修订，不切换原发布条目或运行节点。"""
from copy import deepcopy
from uuid import uuid4
import json

def create(studio,p):
    from .service import write_json,read_json,sources,digest,GUIDES,TEXT
    kind=p.get('kind','module')
    reference=p.get('reference','')
    work=studio.create(dict(kind=kind,sample='blank',name='网络修改稿' if kind=='network' else '模块／工具修改稿',display_folder=p.get('display_folder'),reference_files={**p.get('reference_files',{}),'咨询记录.json':reference}))
    folder=studio.folder(work['id']);source=p.get('source')
    if kind=='network':
        document=deepcopy(p['document']);document['network']['signals']={}
        for node in document['network']['nodes']:
            node['context_cursor']=None
            if node['type']=='pulse':node.get('parameters',{}).pop('state',None)
        write_json(folder/'network.json',document)
        write_json(folder/'runtime.json',dict(templates=(p.get('runtime') or {}).get('templates',[])))
    elif source:
        for name,content in source['files'].items():
            if name in GUIDES or name.startswith(('reference/','dependencies/','lessons/')):continue
            target=(folder/name).resolve()
            if not target.is_relative_to(folder.resolve()) or target.suffix not in TEXT or not isinstance(content,str):raise ValueError('修改来源文件无效')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    from .git_baselines import save as save_baseline
    baseline=sources(folder);write_json(studio.root/'baselines'/f'{work["id"]}.json',save_baseline(studio,work['id'],baseline))
    metadata=read_json(folder/'workspace.json',{});metadata['origin']=p.get('origin',{});metadata['immutable_revision']=True
    if kind!='network':
        manifest=read_json(folder/'module.json',{});original=manifest['id']
        if not p.get('preserve_identity',False):
            manifest['id']=original[:65].rstrip('.-_')+'.rev_'+uuid4().hex[:10]
            version=manifest.get('version','0.1.0').split('.');manifest['version']='.'.join(version[:2]+[str(int(version[2])+1)])
        metadata['branch_module']=manifest['id'];metadata['label']=(manifest.get('name') or original)+' · 修改副本'
        write_json(folder/'module.json',manifest)
    write_json(folder/'workspace.json',metadata)
    return dict(studio.read(dict(id=work['id'])),origin=metadata['origin'],branch_module=metadata.get('branch_module'))
