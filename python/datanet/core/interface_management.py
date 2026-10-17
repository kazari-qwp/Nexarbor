"""Private owner-granted topology management; never a remotely exposed service."""
from copy import deepcopy
from dataclasses import asdict, replace
from threading import RLock
from datanet.core.node import NodeResult
from datanet.core.management import SCOPES, resolve_managed, can_manage
from datanet.core.interface import Interface, metadata_schema

def attach_interface_management_tools(network, owner, *, scope='self', actions=('list', 'add', 'update', 'remove'), allow_external_targets=False):
    if network.nodes.get(owner.node_id) is not owner or scope not in SCOPES:
        raise ValueError('Invalid interface owner/scope')
    if not actions or set(actions) - {'list', 'add', 'update', 'remove'} or type(allow_external_targets) is not bool:
        raise ValueError('Invalid interface toolbox options')
    lock = RLock()
    permissions = {'scope': scope, 'actions': list(actions), 'allow_external_targets': allow_external_targets}

    def reachable(node_id, strength):
        return next((node for node, _, _ in network.walk_states(owner.node_id, channels=('access.write',), strength=strength) if node.node_id == node_id), None)

    def resolve(node_id, strength):
        return resolve_managed(network, owner.node_id, node_id, scope)

    def locate(links, target, index):
        if index is not None:
            if type(index) is not int or index < 0 or index >= len(links) or (links[index].target_node_id != target):
                raise ValueError('Interface index/target conflict')
            return index
        indices = [i for i, x in enumerate(links) if x.target_node_id == target]
        if len(indices) != 1:
            raise ValueError('Interface absent or ambiguous; query indices')
        return indices[0]

    def manage(action, node_id=None, target_node_id=None, interface=None, changes=None, interface_index=None, strength=0):
        try:
            with lock:
                if action not in actions:
                    raise PermissionError('Action is outside toolbox grant')
                node = resolve(node_id, strength)
                if action == 'list':
                    return NodeResult(items=[{'node_id': node.node_id, 'permissions': deepcopy(permissions), 'interfaces': [{'interface_index':i,**asdict(x)} for i,x in enumerate(node.interfaces)]}])
                if target_node_id not in network.nodes:
                    raise ValueError('Target node does not exist')
                links = node.interfaces
                if action == 'add':
                    if not allow_external_targets and (not can_manage(network, owner.node_id, target_node_id, scope)) and (reachable(target_node_id, strength) is None) and (not any((node.node_id == target_node_id for node, _, _ in network.walk_states(owner.node_id, channels=('access.read',), strength=strength)))):
                        raise PermissionError('Target is outside granted connection range')
                    options = {} if interface is None else interface
                    if not isinstance(options, dict) or set(options) - {'metadata'}:
                        raise ValueError('Invalid interface parameters')
                    link = Interface(target_node_id, **options)
                    if link in links:return NodeResult(status='conflict',errors=['Interface already exists'])
                    links.append(link)
                    return NodeResult(items=[{'node_id': node.node_id, 'interface_index': len(links) - 1, 'after': asdict(link)}])
                index = locate(links, target_node_id, interface_index)
                before = links[index]
                if action == 'remove':
                    links.pop(index)
                    return NodeResult(items=[{'node_id': node.node_id, 'removed': asdict(before)}])
                if not isinstance(changes, dict) or not changes or set(changes) - {'metadata'}:
                    raise ValueError('Invalid interface changes')
                after = replace(before, **changes)
                links[index] = after
                return NodeResult(items=[{'node_id': node.node_id, 'interface_index': index, 'before': asdict(before), 'after': asdict(after)}])
        except PermissionError as error:
            return NodeResult(status='forbidden', errors=[str(error)])
        except (ValueError, TypeError) as error:
            return NodeResult(status='error', errors=[str(error)])
    owner.register_agent_tool('manage_interfaces', manage, description='管理工具箱授权范围内的节点接口：list/add/update/remove。只供所属 Agent 使用。', parameters={'type': 'object', 'properties': {'action': {'type': 'string', 'enum': list(actions)}, 'node_id': {'type': 'string'}, 'target_node_id': {'type': 'string'}, 'interface': {'type':'object','properties':{'metadata':metadata_schema()},'required':['metadata'],'additionalProperties':False}, 'changes': {'type':'object','properties':{'metadata':metadata_schema()},'required':['metadata'],'additionalProperties':False}, 'interface_index': {'type': 'integer'}}, 'required': ['action'], 'additionalProperties': False})
    return deepcopy(owner.agent_tool_definitions['manage_interfaces'])
