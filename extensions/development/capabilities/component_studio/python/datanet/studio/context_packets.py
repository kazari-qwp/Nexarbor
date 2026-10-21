"""Executor-facing context packet contract, shared by production and the test fixture."""


def apply_context_packet(backend,actor,source,packet):
    if not isinstance(packet,dict) or packet.get('format')!='nexarbor-context/v1':return False
    backend.network.nodes[actor].inputs.update(source,packet['patch'])
    backend.agents.setdefault(actor,{})['context_assembly_errors']=packet.get('errors',[])
    return True
