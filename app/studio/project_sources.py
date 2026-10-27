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
