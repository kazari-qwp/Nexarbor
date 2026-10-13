from datanet.core.component_registry import attach_local_tools, codec_for_node
def install(node):
    if 'local_data' in node.toolboxes:
        attach_local_tools(node)
        if codec_for_node(node).local_write and 'write' not in node.tool_definitions and hasattr(node, 'write'):
            node.register_tool('write', node.write, description='写入本节点数据', parameters={'type': 'object', 'properties': {'key': {'type': 'string'}, 'value': {}, 'mode': {'type': 'string', 'enum': ['insert', 'update', 'upsert', 'append']}}, 'required': ['key', 'value'], 'additionalProperties': False}, read_only=False)

def register():
    from datanet.core.component_registry import register_toolbox
    register_toolbox("local_data",install)
