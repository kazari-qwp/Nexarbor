"""原发布库的修改副本与受控删除，路径只来自宿主登记。"""
import json
from pathlib import Path
import shutil
from uuid import uuid4


def fork(studio,p):
    from .service import GUIDES,sources,write_json
    release=studio.release_read(p);workspace=studio.create({'sample':'blank'});folder=studio.folder(workspace['id'])
    for name,content in release['files'].items():
        if name in GUIDES:continue
        target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    write_json(studio.root/'baselines'/f'{workspace["id"]}.json',sources(folder))
    write_json(folder/'workspace.json',{'label':release['id']+' · 修改副本','sample':'blank','display_folder':release['release'].get('display_folder')})
    return studio.read({'id':workspace['id']})


def delete_info(studio,p):
    from .service import read_json
    name=p.get('module');release=studio.library.get(name)
    if release is None:raise ValueError('组件已不在发布库中')
    if release.get('origin')=='standard':
        return dict(canDelete=False,reason='官方扩展模块，只可归档，不能删除',blockers=['官方扩展模块，只可归档，不能删除'],ownership='official',files=[])
    local=release.get('origin')=='project'
    root=(studio.project_directory/'modules').resolve() if local else (studio.root/'releases').resolve()
    registered=(studio.root/release['folder']).resolve()
    target=registered if local else (root/name).resolve()
    if target==root or not target.is_relative_to(root) or not target.is_dir():raise ValueError('组件文件不属于本工作区发布目录')
    if not registered.is_relative_to(target):raise ValueError('组件登记目录与组件编号不一致')
    files=[]
    for file in target.rglob('*'):
        if not file.resolve().is_relative_to(target):raise ValueError('组件发布目录含外部链接，不能删除')
        if file.is_file():files.append(str(file.relative_to(root)))
    blockers=[]
    for node in studio.backend.network:
        if node.modules.get(name) is not None:blockers.append('运行节点：'+node.info.node_id)
    draft=read_json(studio.root/'draft.json',{})
    if not draft.get('applied',False):
        for node in draft.get('document',{}).get('network',{}).get('nodes',[]):
            if any(item['module_id']==name for item in node.get('tables',{}).get('modules',[])):blockers.append('待应用草稿：'+node['node_id'])
    for key,other in studio.library.items():
        if key!=name and name in other['manifest']['requires']:blockers.append('依赖模块：'+key)
    if studio.running or studio.backend.node_locks.active or studio.backend.signals._active:blockers.append('网络中仍有组件或信号执行')
    return dict(canDelete=not blockers,reason='；'.join(blockers),blockers=blockers,ownership='workspace-release',path=str(target),files=files,
                scope='删除当前项目内此模块的源码；Git 中的已提交版本保留。' if local else '删除本工作区此模块的全部发布版本；独立工作副本和项目共享源码保留。')


def delete(studio,p):
    from .service import write_json
    studio.backend.node_locks.lifecycle();name=p.get('module')
    if p.get('confirm')!=name:raise ValueError('组件删除确认不匹配')
    with studio.lock:
        info=delete_info(studio,p)
        if not info['canDelete']:raise ValueError(info['reason'])
        target=Path(info['path']);root=target.parent;temporary=(root/('.deleting-'+uuid4().hex)).resolve()
        manifest_file=studio.project_directory/'nexarbor.json' if studio.library[name].get('origin')=='project' else None
        manifest_before=manifest_file.read_text(encoding='utf-8') if manifest_file is not None else None
        manifest=json.loads(manifest_before) if manifest_before is not None else None
        if manifest is not None:
            manifest['resources']['modules'].pop(name,None)
            manifest['resources']['tools']={ref:entry for ref,entry in manifest['resources'].get('tools',{}).items() if entry.get('module')!=name}
        if not target.is_relative_to(root) or not temporary.is_relative_to(root):raise ValueError('删除目标越出工作区')
        target.rename(temporary);old=studio.library.copy();removed=studio.removed.copy()
        try:
            studio.library.pop(name);studio.removed.add(name)
            write_json(studio.root/'removed-modules.json',sorted(studio.removed));write_json(studio.root/'library.json',studio.library)
            if manifest is not None:write_json(manifest_file,manifest)
            studio._load_releases()
        except BaseException:
            studio.library=old;studio.removed=removed
            if manifest_file is not None:manifest_file.write_text(manifest_before,encoding='utf-8')
            write_json(studio.root/'removed-modules.json',sorted(removed));write_json(studio.root/'library.json',old);temporary.rename(target);studio._load_releases();raise
        studio.backend.saver.tables.module_types.pop(name,None)
        # 两个绝对路径已核实位于当前项目模块或工作区发布目录中。
        shutil.rmtree(temporary)
        return dict(deleted=name,filesDeleted=len(info['files']))
