"""Agent 模板：配置、提示词和工具定义构成可复用配置包。"""
from copy import deepcopy
from datanet.abilities.agent_identity.configuration import FIELDS, validate_config
from datanet.core.packages.common import read_manifest
from datanet.core.serialization import _fields

class AgentPackage:

    def __init__(self, path):
        self.path, self._document = read_manifest(path, 'agent', ('kind', 'version', 'id', 'description', 'config'))
        _fields(self._document['config'], sorted(FIELDS - {'node_bindings'}), 'Agent 模板配置')
        validate_config({**self._document['config'], 'node_bindings': {}}, self.path.parent)

    @property
    def package_id(self):
        return self._document['id']

    @property
    def description(self):
        return self._document['description']

    def configure(self, *, node_bindings=None):
        """每次返回独立运行配置；客户端、密钥、历史不属于配置包。"""
        return validate_config({**deepcopy(self._document['config']), 'node_bindings': deepcopy(node_bindings or {})}, self.path.parent)

def load_agent_package(path):
    return AgentPackage(path)
