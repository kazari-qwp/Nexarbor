"""工作台的模板、宿主工具与向量服务路由；沿用原服务接口。"""
from copy import deepcopy
from app.runtime.ports import DEFINITIONS
from app.templates.service import DEFINITION
from jsonschema import Draft202012Validator

CHANNELS={'agent_run':['runtime.agent'],'checkpoint':['runtime.checkpoint'],'read_text':['runtime.text']}

def register(transport,project):
    backend=transport.backend
    transport.routes['ping']=lambda p:{'ok':True}
    transport.routes['runtime_catalog']=lambda p:[dict(**item,ref='runtime:'+item['name'],provider='runtime',channels=CHANNELS[item['name']]) for item in DEFINITIONS]
    transport.routes['templates_register']=lambda p:project.templates.configure(p['templates'])
    transport.routes['templates_catalog']=lambda p:[dict(**DEFINITION,ref='templates:instantiate',provider='templates',channels=['runtime.template'])]
    transport.routes['studio_official_needed']=lambda p:any(offer['ref'].startswith('harness:') for value in backend.extension_state.get('node_properties',{}).values() for offer in value.get('offered_ports',[]))
    from projects.knowledge_archive.nodes.vector.startup import status,close
    transport.routes['studio_vector_status']=lambda p:status()
    transport.routes['studio_vector_close']=lambda p:close()
    if not hasattr(project,'host_tools'):return
    def official_register(p):
        names={item['name'] for item in p['tools']}
        for name,contract in p.get('contracts',{}).items():
            if name not in names or contract.get('format')!='harness-tool-result/v1':raise ValueError('官方工具返回契约无效')
            Draft202012Validator.check_schema(contract['value_schema'])
        definitions={'harness:'+item['name']:deepcopy(item) for item in p['tools']}
        contracts={'harness:'+name:deepcopy(contract) for name,contract in p.get('contracts',{}).items()}
        project.host_tools.definitions.update(definitions)
        backend.studio.port_contracts.update(contracts)
        backend.extension_state.setdefault('port_definitions',{}).update(definitions)
        backend.extension_state.setdefault('port_contracts',{}).update(contracts)
        project.register_properties(backend.extension_state.get('node_properties',{}))
        for node in backend.network:
            for tool in node.tools:
                reference=getattr(tool,'_host_ref',None)
                if reference in definitions:
                    tool.parameters=deepcopy(definitions[reference]['parameters'])
                    tool.description=node.info.node_id+' · '+definitions[reference]['description']
        return p['tools']
    transport.routes['official_register']=official_register
