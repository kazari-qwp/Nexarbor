"""本地项目组件入口与不可变执行缓存；不改核心协议。"""
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

def load(studio):
    from .service import sources,digest,read_json
    from .contract import manifest
    root=Path(os.environ.get('DATANET_PROJECT_DIRECTORY',studio.backend.directory)).resolve()/'modules'
    errors=[];added=[];before=studio.library.copy()
    if not root.is_dir():return dict(imported=[],errors=[])
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'module.json').is_file():continue
        try:
            if not folder.resolve().is_relative_to(root.resolve()):raise ValueError('模块不能链接到项目目录之外')
            spec=manifest(folder);name=spec['id']
            files=sources(folder);fingerprint=digest(files)
            if studio.library.get(name,{}).get('digest')==fingerprint:continue
            destination=studio.root/'releases'/name/spec['version']/fingerprint
            materialize(destination,files,studio.root)
            defaults=read_json(destination/'example.json',{})
            studio.library[name]=dict(id=name,version=spec['version'],digest=fingerprint,folder=str(destination.relative_to(studio.root)),manifest=spec,defaults=defaults.get('config',{}),mount_defaults=defaults,origin_kind='module',origin='project');added.append(name)
        except Exception as error:errors.append(folder.name+'：'+str(error))
    try:studio._load_releases()
    except Exception as error:studio.library=before;studio._load_releases();errors.append(str(error));added=[]
    if added:studio.persist_library()
    return dict(imported=added,errors=errors)
