"""项目源码入口与发布内容缓存；项目运行直接读取本地源码。"""
import os
from pathlib import Path
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
    """只从项目 modules/ 读取；同名资源由本地文件决定，缓存不作为回退来源。"""
    from .service import sources,digest,read_json
    from .contract import manifest
    root=Path(os.environ.get('DATANET_PROJECT_DIRECTORY',studio.backend.directory)).resolve()/'modules'
    metadata=read_json(root.parent/'nexarbor.json',{}).get('resources',{}).get('modules',{})
    result={};errors=[];studio.source_issues={}
    if not root.is_dir():return result
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith('.'):continue
        try:
            if not folder.resolve().is_relative_to(root.resolve()):raise ValueError('模块不能链接到项目目录之外')
            missing=[name for name in ('module.json','module.py') if not (folder/name).is_file()]
            if missing:
                studio.source_issues[folder.name]='模块源码缺失：'+folder.name+'（'+', '.join(missing)+'）'
                continue
            spec=manifest(folder);name=spec['id']
            if folder.name!=name:raise ValueError('模块目录名必须与 module.json 的 id 一致')
            files=sources(folder);defaults=read_json(folder/'example.json',{})
            result[name]=dict(id=name,version=spec['version'],digest=digest(files),folder=str(folder.resolve()),manifest=spec,defaults=defaults.get('config',{}),mount_defaults=defaults,origin_kind=metadata.get(name,{}).get('origin_kind','module'),display_folder=metadata.get(name,{}).get('display_folder'),origin='project')
        except Exception as error:studio.source_issues[folder.name]='模块文件无法读取：'+folder.name+'；'+(str(error) or type(error).__name__).splitlines()[0][:220]
    if errors:raise ValueError('项目模块读取失败：'+'；'.join(errors))
    return result

def load(studio):
    before=studio.library.copy()
    try:
        studio.library=studio.select_releases(studio.library)
        studio._load_releases()
    except Exception:
        studio.library=before
        raise
    added=[name for name,release in studio.library.items() if release.get('origin')=='project' and before.get(name)!=release]
    if studio.library!=before:studio.persist_library()
    return dict(imported=added,errors=[])
