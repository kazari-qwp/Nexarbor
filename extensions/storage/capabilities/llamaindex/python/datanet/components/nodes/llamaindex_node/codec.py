from pathlib import Path
from datanet.components.nodes.llamaindex_node.llamaindex_node import LlamaIndexNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    if node.embedding_config is None:
        raise ValueError('保存LlamaIndex节点需要显式embedding_config，不能序列化模型对象')
    embedding = dict(node.embedding_config)
    embedding['model_path'] = _path_string(Path(embedding['model_path']), base)
    parameters = {'storage_path': _path_string(node.storage_path, base), 'embedding': embedding}
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields(params, ('storage_path', 'embedding'), 'LlamaIndex节点参数')
    embedding = dict(params['embedding'])
    embedding['model_path'] = str(base / _string(embedding['model_path'], 'model_path'))
    node = LlamaIndexNode(node_id, name, base / _string(params['storage_path'], 'storage_path'), embedding_config=embedding)
    node.data_kind = kind
    return node

def register():
    register_node(NodeCodec('llamaindex', LlamaIndexNode, encode, decode, parameter_fields=['storage_path', 'embedding'], description='文档语义检索节点。基于 LlamaIndex 导入文档、分块并建立向量索引，支持增量更新及语义搜索，返回相关文本片段与来源。适合资料库和长文档检索；需要配置嵌入模型，只检索片段，不自行生成回答。', resource_directories=('storage_path',), references={}, local_write=True))
