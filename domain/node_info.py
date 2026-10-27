"""节点的基础信息。"""

from dataclasses import dataclass


@dataclass
class NodeInfo:
    node_id: str
    name: str
    description: str = ""
