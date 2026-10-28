"""草稿的新装配交给核心安装器；完整表直接恢复，不重新检查依赖。"""
from copy import deepcopy
from .testing import ModuleHarness

def assemble_document(document,backend,library,*,port_definitions=None,allow_missing=False):
    result=deepcopy(document);pending={}
    for record in result['network']['nodes']:
        tables=record.get('tables',{})
        requests=[item for item in tables.get('modules',[]) if 'tools' not in item]
        if requests:pending[record['node_id']]=requests
        if 'tools' not in tables:record.pop('tables',None)
        else:tables['modules']=[item for item in tables['modules'] if 'tools' in item]
    paths={name:backend.directory/'studio'/release['folder'] for name,release in library.items()}
    h=ModuleHarness(None,library=paths)
    try:
        h.modules.tolerate=allow_missing
        for label in ('node_types','agent_node_types','aggregation_types'):getattr(h.backend.saver,label).update(getattr(backend.saver,label))
        h.backend.saver.tables.tool_types.update(backend.saver.tables.tool_types)
        from app.projects.host_tools import host_tool_name
        h.definitions.update(port_definitions or {})
        for node,properties in result['network'].get('properties',{}).items():
            for offer in properties.get('offered_ports',[]):
                ref=offer['ref'];name=host_tool_name(node,ref)
                h.backend.saver.tables.tool_types[name]=lambda current,record,ref=ref:h.make_port(current.info.node_id,ref)
        h.backend.restore({'version':1,'agents':{},'node_properties':result['network'].get('properties',{}),**result})
        for node,requests in pending.items():
            for item in requests:
                h.mount(node,module=item['module_id'],config=item.get('config'),state=item.get('state'),access={key:item[key] for key in ('channels','strength','channel_mode') if key in item})
        from app.projects.host_tools import host_tool_name
        for node,properties in result['network'].get('properties',{}).items():
            for offer in properties.get('offered_ports',[]):
                name=host_tool_name(node,offer['ref'])
                if not any(tool.name==name for tool in h.network.get(node).tools):
                    h.definitions[offer['ref']]=(port_definitions or {})[offer['ref']]
                    h.offer(node,offer['ref'],offer['channels'])
        snapshot=h.backend.snapshot()
        for record in snapshot['network']['nodes']:
            for module in record.get('tables',{}).get('modules',[]):
                definition=h.modules.manifests.get(module['module_id'])
                if definition and record['type'] not in definition['node_types']:raise ValueError('模块不支持节点类型：'+module['module_id'])
        return {'network':{**result['network'],**snapshot['network']},'files':snapshot['files']}
    finally:h.backend.close();h._cleanup()
