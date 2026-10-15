"""Agent 可持久化配置和运行时装配；客户端/密钥由应用提供。"""
import json
from pathlib import Path
from copy import deepcopy
from datanet.core.tool_access import attach_discovery_tools
FIELDS = {'model', 'prompt_path', 'tools_path', 'max_rounds', 'max_tokens', 'thinking', 'node_bindings', 'max_signal_strength'}

def validate_config(config, base):
    if config is None:
        return None
    if not isinstance(config, dict) or set(config) != FIELDS:
        raise ValueError(f"Agent 配置必须包含：{', '.join(sorted(FIELDS))}")
    bindings = config['node_bindings']
    if not isinstance(bindings, dict) or not all((isinstance(k, str) and k and isinstance(v, str) and v for k, v in bindings.items())):
        raise ValueError('node_bindings 必须为非空字符串到非空字符串的字典')
    for name in ('model', 'prompt_path'):
        if not isinstance(config[name], str) or not config[name]:
            raise ValueError(f'Agent {name} 必须为非空字符串')
    if config['tools_path'] is not None and (not isinstance(config['tools_path'], str) or not config['tools_path']):
        raise ValueError('tools_path 必须为空或非空路径字符串')
    for name in ('max_rounds', 'max_tokens'):
        if type(config[name]) is not int or config[name] < 1:
            raise ValueError(f'{name} 必须是正整数')
    if config['thinking'] is not None and type(config['thinking']) is not bool:
        raise ValueError('thinking 必须为 bool 或 null')
    from datanet.core.interface import validate_strength
    validate_strength(config['max_signal_strength'])
    result = deepcopy(config)
    result['prompt_path'] = str((base / config['prompt_path']).resolve())
    if result['tools_path'] is not None:
        result['tools_path'] = str((base / result['tools_path']).resolve())
    return result

def assemble_agents(network, client, *, model_override=None, node_ids=None):
    """工具已由应用装配；先构建全部实例，成功后统一绑定，不调用 API。"""
    from datanet.executors.minimal.agent import Agent
    from datanet.abilities.agent_identity.delegation import attach_delegation_tool
    prepared = {}
    for node in network.nodes.values():
        if node_ids is not None and node.node_id not in node_ids:
            continue
        config = node.agent_config
        if config is not None:
            from datanet.core.agent_node import AgentNode
            if not isinstance(node,AgentNode):raise TypeError('Agents require an Agent node')
        if config is None:
            continue
        config = validate_config(config, Path.cwd())
        if config['tools_path'] is not None:
            with Path(config['tools_path']).open(encoding='utf-8') as file:
                definitions = json.load(file)
        else:
            definitions = [{'type': 'function', 'function': {key: deepcopy(value) for key, value in definition.items() if key != 'read_only'}} for name, definition in node.tool_definitions.items() if name in node.tools and definition['read_only']]
        names_from_file = {d['function']['name'] for d in definitions}
        definitions.extend((deepcopy(d) for name, d in node.agent_tool_definitions.items() if name not in names_from_file))
        definitions.extend(attach_discovery_tools(network, node))
        definitions.append(attach_delegation_tool(network, node))
        names = [d['function']['name'] for d in definitions]
        if len(names) != len(set(names)):
            raise ValueError('Agent 工具定义名称重复')
        if set(names) - node.tools.keys():
            raise ValueError('Agent 配置包含未装配的工具')
        extra = None if config['thinking'] is None else {'thinking': {'type': 'enabled' if config['thinking'] else 'disabled'}}
        prepared[node.node_id] = Agent(client, model_override or config['model'], config['prompt_path'], definitions, config['max_rounds'], config['max_tokens'], extra, node_bindings=config['node_bindings'], max_signal_strength=config['max_signal_strength'])
    for node_id, agent in prepared.items():
        network.nodes[node_id].agent = agent
        from datanet.abilities.agent_identity.management import attach_agent_management_tools
        attach_agent_management_tools(network.nodes[node_id])


def encode_execution(node, base):
    from datanet.core.serialization import _path_string
    agent_config = node.agent_config
    if node.agent is not None and hasattr(node.agent, 'model'):
        if node.agent.extra_body not in (None, {'thinking': {'type': 'disabled'}}, {'thinking': {'type': 'enabled'}}):
            raise ValueError('Agent 配置只支持 thinking 开关，不保存其他 extra_body')
        agent_config = {'model': node.agent.model, 'prompt_path': str(node.agent.prompt_path), 'tools_path': (agent_config or {}).get('tools_path'), 'max_rounds': node.agent.max_rounds, 'max_tokens': node.agent.max_tokens, 'max_signal_strength': node.agent.max_signal_strength, 'thinking': None if node.agent.extra_body is None else node.agent.extra_body['thinking']['type'] == 'enabled', 'node_bindings': node.agent.node_bindings}
        if agent_config['tools_path'] is None:
            known = node.tool_definitions.keys() | node.agent_tool_definitions.keys() | {'list_nodes', 'list_tools', 'invoke_tool', 'ask_agent'}
            if any((d['function']['name'] not in known for d in node.agent.tool_definitions)):
                raise ValueError('保存 Agent 前需要配置工具定义文件或登记本地工具元数据')
    agent_config = validate_config(agent_config, base)
    if agent_config is not None:
        for label in ('prompt_path', 'tools_path'):
            if agent_config[label] is not None:
                agent_config[label] = _path_string(Path(agent_config[label]), base)
    return agent_config
