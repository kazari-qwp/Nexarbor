from datanet.core.agent_node import AgentNode

def ensure_agent_node(self, p):
    target = p['target']
    node = self.network.nodes.get(target)
    if node is None:
        raise ValueError('Agent node does not exist')
    if not isinstance(node, AgentNode):
        raise ValueError('Only Agent nodes may host an Agent')
    return {'node_id': target}


def register(services):
    services.rpc('ensure_agent_node', ensure_agent_node, mutation=True)
