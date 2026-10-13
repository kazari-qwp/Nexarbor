from pathlib import Path
from datanet.components.nodes.discussion_board_node.discussion_board_node import DiscussionBoardNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    parameters = {'file_path': _path_string(node.file_path, base), 'members': node.members, **{label: getattr(node, label) for label in ('leader_id', 'recorder_id', 'project_id', 'notebook_id', 'output_id')}, 'project_ids': node.project_ids}
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields({k: v for k, v in params.items() if k != 'project_ids'}, ('file_path', 'members', 'leader_id', 'recorder_id', 'project_id', 'notebook_id', 'output_id'), '讨论黑板参数')
    node = DiscussionBoardNode(*common, base / _string(params['file_path'], 'file_path'), project_ids=params.get('project_ids'), **{label: params[label] for label in ('members', 'leader_id', 'recorder_id', 'project_id', 'notebook_id', 'output_id')})
    return node

def register():
    register_node(NodeCodec('discussion_board', DiscussionBoardNode, encode, decode, parameter_fields=['file_path', 'members', 'leader_id', 'recorder_id', 'project_id', 'notebook_id', 'output_id'], description='公共讨论黑板。读取上轮快照、仅追加本轮发言，内置run_discussion执行成员轮次和归档清空，返回Recorder最终成果节点；需要网络配置成员、文档接口和委托许可。', resources=('file_path', 'previous_path'), references={'leader_id': 'one', 'recorder_id': 'one', 'project_id': 'one', 'notebook_id': 'one', 'output_id': 'one', 'members': 'many', 'project_ids': 'many'}, local_write=False, local_read=False))
