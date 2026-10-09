"""节点的不可变地址引用；强弱与读写由持有者的连接列表表达。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Interface:
    target_node_id: str
