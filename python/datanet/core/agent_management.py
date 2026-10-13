"""Agent management is private; parent management uses explicit owner-granted tools."""
from datanet.core.node import NodeResult

def attach_agent_management_tools(node):

    def restart():
        try:
            node.restart_agent(wait=False)
            return NodeResult(items=[{'node_id': node.node_id, 'restarted': True}])
        except (OSError, ValueError, RuntimeError) as error:
            return NodeResult(status='error', errors=[str(error)])

    def update_prompt(content, restart=True):
        try:
            result = node.update_agent_prompt(content, restart=restart)
            return NodeResult(items=[{'node_id': node.node_id, **result}])
        except (OSError, ValueError, RuntimeError) as error:
            return NodeResult(status='error', errors=[str(error)])
    node.register_agent_tool('restart_agent', restart, description='重建本节点Agent，重新加载提示词并清空会话；忙时拒绝', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False})
    node.register_agent_tool('update_agent_prompt', update_prompt, description='更新本节点绑定的提示词文件，保留上一版.bak；默认重启生效并清空会话；不能指定其他文件路径', parameters={'type': 'object', 'properties': {'content': {'type': 'string'}, 'restart': {'type': 'boolean'}}, 'required': ['content'], 'additionalProperties': False})
