"""Windows 深层真实节点资源的原子恢复和枚举，不改机器长路径设置。"""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from adapt.files.atomic import atomic_bytes
from adapt.files.storage_paths import storage_path
from app.persistence.resource_data import read_bytes,read_data,write_data,resource_files

ROOT=Path(__file__).resolve().parents[1]

class LongResourcePaths(unittest.TestCase):
    def test_deep_resource_atomic_replace_and_enumeration_keep_public_paths(self):
        with TemporaryDirectory(prefix='long-resources-',dir=ROOT/'build') as temp:
            root=Path(temp);parent=root/('node-'+'a'*55)/('index-'+'b'*55)/('version-'+'c'*55)
            file=parent/'default__vector_store.json';self.assertGreater(len(str(file))+len('.resource.tmp'),260)
            write_data(file,'原始索引');self.assertEqual(read_data(file),'原始索引')
            write_data(file,'更新索引');self.assertEqual(read_data(file),'更新索引')
            self.assertIn(file,resource_files(root));self.assertFalse(str(resource_files(root)[0]).startswith('\\\\?\\'))
            atomic_bytes(file,'原子写'.encode('utf-8'));self.assertEqual(read_bytes(file),'原子写'.encode('utf-8'))
            write_data(file,None);self.assertFalse(storage_path(file).exists())

    def test_sqlite_backup_can_read_deep_file_and_preserve_committed_rows(self):
        with TemporaryDirectory(prefix='long-sqlite-',dir=ROOT/'build') as temp:
            root=Path(temp);file=root/('node-'+'a'*55)/('index-'+'b'*55)/('version-'+'c'*55)/'catalog.sqlite3'
            storage_path(file.parent).mkdir(parents=True)
            db=sqlite3.connect(str(storage_path(file)))
            try:
                with db:db.execute('CREATE TABLE items(value)');db.execute('INSERT INTO items VALUES(7)')
            finally:db.close()
            data=read_bytes(file)
            copy=sqlite3.connect(':memory:')
            try:copy.deserialize(data);self.assertEqual(copy.execute('SELECT value FROM items').fetchone()[0],7)
            finally:copy.close()

if __name__=='__main__':unittest.main()
