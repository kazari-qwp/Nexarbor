"""On-demand text queries. Automatic context delivery belongs to the assembler."""
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
TEXT_PRESETS={'query_text':{'type':'text_file','name':'查询文本','data_kind':'text','description':'向读取者提供绑定本节点的查询工具，按需加载正文。','parameters':{'file_path':'document.md','delivery':'query'},'toolboxes':['local_data'],'expose':['get_schema','write','read']}}
def label(node):return '['+node.name+'：'+node.node_id+']'+('('+node.description+')' if node.description else '')
def bindings(backend,p):
    owner=backend.network.nodes[p['actor']]
    targets={e.target_node_id for e in owner.read_interfaces if e.allows(origin_node_id=owner.node_id,source_node_id=owner.node_id,strength=p.get('strength',0))}
    return [backend.network.nodes[x] for x in sorted(targets) if type(backend.network.nodes[x]) is TextFileNode and backend.network.nodes[x].delivery=='query']
def dispatch(backend,method,p):
    if method=='text_bindings':return {'read':[dict(node_id=n.node_id,name=n.name,description=n.description,delivery=n.delivery,label=label(n)) for n in bindings(backend,p)]}
    if method=='query_text':
        node=next((n for n in bindings(backend,p) if n.node_id==p['target']),None)
        if node is None:raise PermissionError('目标不在该节点的查询文本读取连接中')
        result=node.read(dict(method='key',key='content'))
        if result.status!='ok':return result
        return dict(node_id=node.node_id,text=label(node)+'\n'+result.items[0]['content'])
    raise ValueError(method)
def register(services):
    services.node_presets.update(TEXT_PRESETS)
    for method in ('text_bindings','query_text'):services.rpc(method,lambda b,p,m=method:dispatch(b,m,p))
