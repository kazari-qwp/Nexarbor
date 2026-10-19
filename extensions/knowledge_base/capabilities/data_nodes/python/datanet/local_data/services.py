"""客户端内置数据模板；所有默认数据均内嵌在独立资源快照中。"""
import sqlite3
from datanet.core.resource_data import encode_bytes

def templates():
    result=[]
    kinds=[('value','JSON 数据节点','少量 JSON 数据，值随节点完整复制。'),('csv','CSV 数据节点','独立 CSV 文档，支持主键、字段过滤与写入。'),('sqlite','SQLite 数据节点','独立 SQLite 数据库，按字段查询与主键写入。'),('rag','RAG 文档节点','独立文档、版本和向量索引；语义检索须配置本地嵌入模型。'),('wiki','Wiki 数据节点','独立 Wiki 页面、链接、来源和历史版本。')]
    for kind,name,description in kinds:
        id='template-'+kind;folder='data/'+id;files={}
        if kind=='value':parameters=dict(value={})
        elif kind=='csv':parameters=dict(file_path=folder+'/records.csv',key_column='id',dtype={'id':'string','text':'string'});files[parameters['file_path']]='id,text\n'
        elif kind=='sqlite':
            parameters=dict(db_path=folder+'/records.sqlite3',table_name='records',key_column='id');db=sqlite3.connect(':memory:')
            try:db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,text TEXT)');files[parameters['db_path']]=encode_bytes(db.serialize())
            finally:db.close()
        else:parameters=dict(directory=folder,storage=kind,schema={},embedding=None,collection_id=None)
        node=dict(type=kind if kind in ('value','csv','sqlite') else 'knowledge_collection',node_id=id,name=name,description=description,management_parent_id='root',divergence=-1,data_kind=kind,parameters=parameters,connections={'interfaces':[]},agent=None,modules={'data.local':dict(config={'read_only':False},state={},access={'strength':0,'channels':['data','knowledge']})},offered_tools=[],toolboxes=[],expose=[],execution=None,inputs=None,context_cursor=None)
        if kind in ('rag','wiki'):node['modules']['data.knowledge']=dict(config={},state={},access={'strength':0,'channels':['data','knowledge']})
        result.append(dict(id=kind,name=name,description=description,mode='internal',snapshot=dict(nodes=[node],files=files,positions={id:dict(x=0,y=0)})))
    return result

def register(services):
    from .preview import preview
    from .clear import clear_live
    services.rpc('data_templates',lambda b,p:templates())
    services.rpc('data_preview',preview)
    services.rpc('data_clear',clear_live)
