"""不可变发布内容缓存；沿用原按内容寻址的 blob 与硬链接存储。"""
import os
from hashlib import sha256

def materialize(folder,files,root):
    blobs=root/'blobs';blobs.mkdir(parents=True,exist_ok=True)
    for name,text in files.items():
        target=(folder/name).resolve()
        if not target.is_relative_to(folder.resolve()):raise ValueError('源码路径越界')
        data=text.encode('utf-8');blob=blobs/sha256(data).hexdigest()
        try:
            with blob.open('xb') as f:f.write(data)
        except FileExistsError:pass
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=data:raise ValueError('不可变发布文件已被改动')
            continue
        try:os.link(blob,target)
        except OSError:target.write_bytes(data)


def scan(studio):
    from .service import read_json,sources,digest
    from .contract import manifest
    studio.source_issues={}
    if studio.project_directory is None:return {}
    project=studio.project_directory;metadata=read_json(project/'nexarbor.json',{})
    result={}
    for name,entry in metadata.get('resources',{}).get('modules',{}).items():
        if entry.get('builtin'):
            if name in studio.standard_releases:result[name]=studio.standard_releases[name]
            continue
        folder=(project/entry['folder']).resolve()
        try:
            if not folder.is_relative_to(project):raise ValueError('模块资源越出项目目录')
            spec=manifest(folder)
            if spec['id']!=name:raise ValueError('模块声明与项目清单 ID 不符')
            files=sources(folder);defaults=read_json(folder/'example.json',{})
            result[name]=dict(id=name,version=spec['version'],folder=str(folder),digest=digest(files),manifest=spec,defaults=defaults.get('config',{}),mount_defaults=defaults,origin='project',origin_kind=entry.get('origin_kind','module'),display_folder=entry.get('display_folder'))
        except Exception as error:studio.source_issues[name]='模块文件无法读取：'+name+'；'+str(error).splitlines()[0][:220]
    return result

def load(studio):
    before=studio.library.copy()
    try:studio.library=studio.select_releases(studio.library);studio._load_releases()
    except BaseException:studio.library=before;raise
    if studio.library!=before:studio.persist_library()
    return dict(imported=[name for name,release in studio.library.items() if release.get('origin')=='project' and before.get(name)!=release],errors=list(studio.source_issues.values()))
