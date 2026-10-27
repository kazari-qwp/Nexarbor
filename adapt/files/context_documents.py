"""原上下文文件端口：项目目录、显式授权根目录与 1 MiB 上限。"""

from pathlib import Path


def read_text(project, name, extra_roots=()):
    root = Path(project).resolve()
    roots = [root] + [(Path(value) if Path(value).is_absolute() else root / value).resolve() for value in extra_roots]
    if not name or not isinstance(name, str):
        raise ValueError("请填写文本文件路径")
    path = Path(name)
    target = (path if path.is_absolute() else root / path).resolve()
    if not any(target.is_relative_to(folder) for folder in roots):
        raise PermissionError("文本路径越出项目和明确授权的目录")
    with target.open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("文本文件超过 1 MiB")
    return {"text": content.decode("utf-8-sig"), "path": str(target)}
