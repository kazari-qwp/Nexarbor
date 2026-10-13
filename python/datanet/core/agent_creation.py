"""显式授权的 Agent 创建工具：按管理归属挂载 Agent，不创建节点。"""
from copy import copy, deepcopy
from pathlib import Path
import shutil
from threading import RLock
from uuid import uuid4
from datanet.core.agent_configuration import assemble_agents, validate_config
from datanet.core.network import Network
from datanet.core.node import NodeResult
from datanet.core.management import SCOPES, resolve_managed
from datanet.core.packages.agent import load_agent_package
from datanet.core.serialization import save_network

def attach_agent_creation_tools(network, owner, *, storage_dir, presets=None, allow_custom=False, client=None, max_signal_strength=0, scope='self'):
    """工具与节点创建能力分别授权；挂载按管理范围授权，普通访问另行校验。

    presets: {id: Agent package.json路径}。新 Agent 不继承创建工具。
    """
    if network.nodes.get(owner.node_id) is not owner:
        raise ValueError('工具所属节点必须已登记在网络中')
    if type(allow_custom) is not bool:
        raise TypeError('allow_custom 必须为 bool')
    from datanet.core.interface import validate_strength
    validate_strength(max_signal_strength)
    if scope not in SCOPES:
        raise ValueError('Invalid management scope')
    presets = {key: load_agent_package(path) for key, path in (presets or {}).items()}
    storage_dir = Path(storage_dir).resolve()
    lock = RLock()

    def catalog():
        return NodeResult(items=[{'allow_custom': allow_custom, 'presets': [{'id': key, 'description': package.description} for key, package in presets.items()]}])

    def assemble_preset_agents(configs, directory):
        """供同一owner的一键建网复用；只接受获准配置，不检查新网络内部写路由。"""
        for node_id in configs:
            resolve_managed(network, owner.node_id, node_id, scope)
        approved = [package.configure() for package in presets.values()]
        for config in configs.values():
            comparable = {key: value for key, value in config.items() if key != 'node_bindings'}
            matches = any((comparable == {key: value for key, value in candidate.items() if key != 'node_bindings'} for candidate in approved))
            if not matches and (not allow_custom or config['max_signal_strength'] > max_signal_strength):
                raise PermissionError('网络包含未获准的Agent配置；请登记对应Agent预设，或明确授权自定义及信号上限')
        runtime_client = client if client is not None else getattr(owner.agent, 'client', None)
        if configs and runtime_client is None:
            raise ValueError('创建Agent需要宿主客户端或创建者已有Agent')
        for node_id, config in configs.items():
            isolated = directory / uuid4().hex
            isolated.mkdir(parents=True)
            copied = deepcopy(config)
            prompt = Path(config['prompt_path']).read_text(encoding='utf-8')
            (isolated / 'prompt.md').write_text(prompt, encoding='utf-8')
            copied['prompt_path'] = str(isolated / 'prompt.md')
            if config['tools_path'] is not None:
                (isolated / 'tools.json').write_bytes(Path(config['tools_path']).read_bytes())
                copied['tools_path'] = str(isolated / 'tools.json')
            network.nodes[node_id].agent_config = validate_config(copied, isolated)
        assemble_agents(network, runtime_client, node_ids=set(configs))
    owner._agent_creation_service = assemble_preset_agents

    def create_agent(target_node_id, agent_spec, strength=1):
        with lock:
            folder = None
            target = None
            original = None
            try:
                if not isinstance(target_node_id, str) or not isinstance(agent_spec, dict):
                    raise TypeError('target_node_id 必须为字符串，agent_spec 必须为字典')
                target = resolve_managed(network, owner.node_id, target_node_id, scope)
                if target.agent is not None or target.agent_config is not None:
                    return NodeResult(status='conflict', errors=['目标已有 Agent 或 Agent 配置'])
                bindings = agent_spec.get('node_bindings', {})
                if not isinstance(bindings, dict) or any((not isinstance(key, str) or not key or key in ('self', 'parent') or (not isinstance(value, str)) or (value not in network.nodes) for key, value in bindings.items())):
                    raise ValueError('node_bindings 必须引用已有节点，不能覆盖 self、parent')
                bindings = {**bindings, 'self': target_node_id, 'parent': owner.node_id}
                if 'preset' in agent_spec:
                    if set(agent_spec) - {'preset', 'node_bindings'}:
                        raise ValueError('预设 Agent 仅接受 preset、node_bindings')
                    key = agent_spec['preset']
                    if not isinstance(key, str) or key not in presets:
                        raise ValueError('未登记的 Agent 预设')
                    config = presets[key].configure(node_bindings=bindings)
                    prompt = Path(config['prompt_path']).read_text(encoding='utf-8')
                    tools = None if config['tools_path'] is None else Path(config['tools_path']).read_text(encoding='utf-8')
                else:
                    if not allow_custom:
                        return NodeResult(status='forbidden', errors=['不允许自定义 Agent'])
                    if set(agent_spec) - {'prompt', 'model', 'max_rounds', 'max_tokens', 'thinking', 'node_bindings'}:
                        raise ValueError('未知的 Agent 配置字段')
                    prompt = agent_spec.get('prompt')
                    if not isinstance(prompt, str) or not prompt.strip():
                        raise ValueError('必须提供非空 prompt')
                    config = {'model': agent_spec.get('model'), 'prompt_path': 'prompt.md', 'tools_path': None, 'max_signal_strength': max_signal_strength, 'max_rounds': agent_spec.get('max_rounds', 5), 'max_tokens': agent_spec.get('max_tokens', 1000), 'thinking': agent_spec.get('thinking', False), 'node_bindings': bindings}
                    tools = None
                runtime_client = client if client is not None else getattr(owner.agent, 'client', None)
                if runtime_client is None:
                    raise ValueError('需要宿主提供客户端或创建者已有 Agent')
                validate_config(config, storage_dir)
                folder = storage_dir / uuid4().hex
                folder.mkdir(parents=True)
                (folder / 'prompt.md').write_text(prompt, encoding='utf-8')
                config['prompt_path'] = str(folder / 'prompt.md')
                config['tools_path'] = None
                if tools is not None:
                    (folder / 'tools.json').write_text(tools, encoding='utf-8')
                    config['tools_path'] = str(folder / 'tools.json')
                original = (target.agent, target.agent_config, target.tools.copy(), deepcopy(target.tool_definitions))
                target.agent_config = validate_config(config, folder)
                assemble_agents(network, runtime_client, node_ids={target_node_id})
                detached = copy(target)
                detached.read_interfaces = []
                detached.write_interfaces = []
                detached.management_parent_id = None
                fragment = Network()
                fragment.add_node(detached)
                save_network(fragment, folder / 'node.json')
                if target_node_id != owner.node_id:
                    grants = network.delegation_permissions.setdefault(owner.node_id, [])
                    if target_node_id not in grants:
                        grants.append(target_node_id)
                return NodeResult(items=[{'node_id': target_node_id, 'has_agent': True, 'configuration_path': str(folder / 'node.json'), 'prompt_path': str(folder / 'prompt.md')}])
            except Exception as error:
                if original is not None:
                    target.agent, target.agent_config, target.tools, target.tool_definitions = original
                if folder is not None and folder.parent == storage_dir and folder.exists():
                    shutil.rmtree(folder)
                return NodeResult(status='forbidden' if isinstance(error, PermissionError) else 'error', errors=[str(error)])
    owner.register_agent_tool('list_agent_presets', catalog, description='查看获准使用的 Agent 预设及自定义开关。', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False})
    owner.register_agent_tool('create_agent', create_agent, description='为已有且位于管理范围内的节点创建 Agent；不创建节点、不覆盖已有 Agent。先查看 list_agent_presets。提示词复制到独立目录，成功后允许创建者委托目标。', parameters={'type': 'object', 'properties': {'target_node_id': {'type': 'string'}, 'agent_spec': {'type': 'object', 'description': '{preset:id,node_bindings?} 或 {prompt,model,max_rounds?,max_tokens?,thinking?,node_bindings?}。自动绑定 self 和 parent（创建者）；额外别名只提供提示词地址，不授予访问权限。'}}, 'required': ['target_node_id', 'agent_spec'], 'additionalProperties': False})
    return {name: deepcopy(owner.agent_tool_definitions[name]) for name in ('list_agent_presets', 'create_agent')}
