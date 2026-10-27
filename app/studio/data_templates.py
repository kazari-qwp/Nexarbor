"""原客户端的数据模板；只列出当前宿主已登记的数据类型和组件。"""
import sqlite3
from app.persistence.resource_data import encode_bytes

def templates(backend,library):
    if 'data.local' not in library:return []
    result=[]
    kinds=[('value','JSON 数据节点','少量 JSON 数据，值随节点完整复制。'),('csv','CSV 数据节点','独立 CSV 文档，支持主键、字段过滤与写入。'),('sqlite','SQLite 数据节点','独立 SQLite 数据库，按字段查询与主键写入。'),('wiki','Wiki 数据节点','独立 Wiki 页面、链接、来源和历史版本。')]
    for kind,name,description in kinds:
        node_type='knowledge_collection' if kind=='wiki' else kind
        if node_type not in backend.saver.node_types or kind=='wiki' and 'data.knowledge' not in library:continue
        id='template-'+kind;folder='data/'+id;files={};parameters={}
        if kind=='value':path=folder+'/value.json';files[path]='{}'
        elif kind=='csv':path=folder+'/records.csv';parameters=dict(key_column='id',dtype={'id':'string','text':'string'});files[path]='id,text\n'
        elif kind=='sqlite':
            path=folder+'/records.sqlite3';parameters=dict(table_name='records',key_column='id');db=sqlite3.connect(':memory:')
            try:db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,text TEXT)');files[path]=encode_bytes(db.serialize())
            finally:db.close()
        else:path=folder;parameters=dict(storage='wiki',schema={},embedding=None,collection_id=None)
        modules=[dict(module_id='data.local',config={'read_only':False},state={},strength=0,channels=['data','knowledge'])]
        if kind=='wiki':modules.append(dict(module_id='data.knowledge',config={},state={},strength=0,channels=['data','knowledge']))
        node=dict(type=node_type,node_id=id,name=name,description=description,bias=-1,aggregation='sum',data=dict(type=node_type,path=path,save_data=True,directory=kind=='wiki',parameters=parameters),links=[],tables={'modules':modules})
        result.append(dict(id=kind,name=name,description=description,mode='internal',snapshot=dict(nodes=[node],files=files,positions={id:dict(x=0,y=0)})))
    return result
