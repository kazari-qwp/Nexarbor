"""Node business toolboxes; only expose is visible through interfaces."""
from datanet.core.component_registry import attach_local_tools, codec_for_node

def attach_node_toolboxes(node):
    from datanet.core.component_registry import toolboxes
    if not isinstance(node.toolboxes,list) or len(set(node.toolboxes))!=len(node.toolboxes):
        raise ValueError('Unknown or duplicate node toolbox')
    for name in node.toolboxes:
        installer=toolboxes().get(name)
        if installer is None:raise ValueError('Unknown node toolbox: '+name)
        installer(node)


def validate_exposure(node):
    if not isinstance(node.expose, list) or any((not isinstance(x, str) for x in node.expose)) or len(set(node.expose)) != len(node.expose):
        raise ValueError('expose must contain unique tool names')
    if set(node.expose) & node.agent_tool_definitions.keys():
        raise ValueError('Agent tools cannot be exposed as node services')
    missing = set(node.expose) - node.tool_definitions.keys()
    if missing:
        raise ValueError(f'Exposed tools are not installed: {sorted(missing)}')
