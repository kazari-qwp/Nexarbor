"""知识目录 DataNode 仅拥有集合登记、入库待办和路由。"""
from pathlib import Path
import sqlite3
from filelock import FileLock
from domain.core import DataNode, Dataer
from .files import DirectoryData, DirectorySaver

class CatalogDataer(Dataer):
    def __init__(self, data):self.data=data
    def read(self):
        database=self.data.path/'catalog.sqlite3'
        if not database.exists():return []
        with sqlite3.connect(database) as db:
            db.row_factory=sqlite3.Row
            return [dict(row) for row in db.execute('SELECT id,name,storage,description FROM collections ORDER BY name')]
    def write(self, value):raise PermissionError('集合登记通过 knowledge.catalog 操作')

class CatalogSaver(DirectorySaver):kind='knowledge_catalog'

class CatalogNode(DataNode):
    node_type='knowledge_catalog'
    def __init__(self, info, path, *, save_data=True):
        data=DirectoryData(Path(path))
        super().__init__(info,dataer=CatalogDataer(data),saver=CatalogSaver(data,FileLock(str(data.path/'.write.lock'),timeout=30)),save_data=save_data)
