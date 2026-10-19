"""Portable text/binary node resources; model files are not owned node data."""
import base64
from pathlib import Path
import sqlite3


def encode_bytes(content):
    if content is None:return None
    try:
        text=content.decode('utf-8')
        if '\x00' not in text:return text
    except UnicodeDecodeError:pass
    return dict(encoding='base64',data=base64.b64encode(content).decode('ascii'))


def decode_data(content):
    if content is None:return None
    if isinstance(content,str):return content.encode('utf-8')
    if not isinstance(content,dict) or set(content)!={'encoding','data'} or content['encoding']!='base64' or not isinstance(content['data'],str):raise ValueError('资源必须是文本或 base64 二进制对象')
    try:return base64.b64decode(content['data'],validate=True)
    except (ValueError,TypeError) as error:raise ValueError('无效的 base64 资源') from error


def read_bytes(path):
    path=Path(path)
    if not path.exists():return None
    with path.open('rb') as stream:header=stream.read(16)
    if header==b'SQLite format 3\x00':
        # Include committed WAL pages, without copying a live journal or changing the source.
        source=sqlite3.connect(Path(str(path).removeprefix('\\\\?\\')).as_uri()+'?mode=ro',uri=True);target=sqlite3.connect(':memory:')
        try:source.backup(target);return target.serialize()
        finally:target.close();source.close()
    return path.read_bytes()


def read_data(path):return encode_bytes(read_bytes(path))


def write_data(path,content):
    path=Path(path);data=decode_data(content)
    if data is None:path.unlink(missing_ok=True);return
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.resource.tmp')
    temporary.write_bytes(data);temporary.replace(path)
