"""显式、只读的项目文本文件端口。不会向模块暴露后端或任意文件句柄。"""
import os
from pathlib import Path

def read_text(project, name, extra_roots=()):
    root = Path(project).resolve()
    roots = [root] + [(Path(value) if Path(value).is_absolute() else root / value).resolve() for value in extra_roots]
    if not name or not isinstance(name, str): raise ValueError('请填写文本文件路径')
    path = Path(name)
    target = (path if path.is_absolute() else root / path).resolve()
    if not any(target.is_relative_to(folder) for folder in roots): raise PermissionError('文本路径越出项目和明确授权的目录')
    # 读操作有大小上限；resolve 也阻止通过目录链接逃逸。
    with target.open('rb') as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024: raise ValueError('文本文件超过 1 MiB')
    return {'text': content.decode('utf-8-sig'), 'path': str(target)}

def register(services):
    factory = services.module_types['context.assembler']
    async def extended(backend, actor, policy, operation, args):
        if operation != 'read_text': raise PermissionError('未声明的文件端口')
        return read_text(os.environ.get('DATANET_PROJECT_DIRECTORY') or backend.directory, args['path'], args.get('roots', []))
    services.module_extensions['context.assembler'] = (factory, extended)
