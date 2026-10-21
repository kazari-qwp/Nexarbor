"""Nonblocking diagnostics for configuration that may break on graph placement."""
def reference_warnings(document,definitions,limit=8):
    ids={node['node_id'] for node in document['network']['nodes']};warnings=[]
    def visit(value,schema,path,node):
        key=path.rsplit('/',1)[-1].lower()
        if key in ('channels','channel_modes') or key.endswith(('_channel','_channels')) or 'enum' in schema or 'const' in schema:return
        # Diagnose likely identity fields, not arbitrary labels that happen to
        # equal an ID (for example role=leader or a channel named discussion).
        identity=schema.get('_identity_item',False) or key in ('id','node','nodes','source','sources','target','targets','parent','address','clock','actor','member','members','requester','integrator','board') or key.endswith(('_id','_ids','_node','_nodes','_target','_source'))
        if isinstance(value,str) and identity and value in ids and schema.get('format') not in ('node-id','node-reference'):
            if len(warnings)<limit:warnings.append(dict(code='untyped_node_reference',node=node,path=path,message='配置值等于局部节点编号，但未声明节点引用，复制时不会重映射。若是节点身份须声明 format:node-id；逻辑身份则应由上游明确映射，不能直接等同请求者编号。'))
        elif isinstance(value,list):
            for index,item in enumerate(value):
                item_schema=dict(schema.get('items',{}))
                if identity:item_schema['_identity_item']=True
                visit(item,item_schema,path+'/'+str(index),node)
        elif isinstance(value,dict):
            extra=schema.get('additionalProperties',{});extra=extra if isinstance(extra,dict) else {}
            for key,item in value.items():visit(item,schema.get('properties',{}).get(key,extra),path+'/'+key.replace('~','~0').replace('/','~1'),node)
    for index,node in enumerate(document['network']['nodes']):
        for name,mount in node.get('modules',{}).items():
            definition=definitions.get(name)
            if definition is None:continue
            visit(mount.get('config',{}),definition.config_schema,f'/network/nodes/{index}/modules/'+name.replace('~','~0').replace('/','~1')+'/config',node['node_id'])
    return warnings
