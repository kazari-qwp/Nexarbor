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
    """旧独立执行器入口已停用；运行由 DeepSeek Harness 宿主装配。"""
    raise RuntimeError('独立 Python Agent 执行器已移除。请在 Nexarbor 工作台通过 DeepSeek Harness 运行 Agent。')


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
