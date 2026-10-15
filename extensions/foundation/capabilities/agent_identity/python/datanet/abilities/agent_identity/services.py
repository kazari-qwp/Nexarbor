from datanet.core.agent_node import AgentNode
def validate_binding(backend,p):
    if p['target']=='root' and (p.get('kind')!='root' or p.get('manager_id') is not None or p.get('creator_node_id') is not None):raise ValueError('Root binding is reserved')
def register(services):
    services.binding_validators.append(validate_binding)
    services.statusters.insert(0,lambda b:{'groups':{},'feedback':[]})
