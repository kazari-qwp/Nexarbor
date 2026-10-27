"""数据节点组合访问器、保存器及随网络全量保存的开关。"""

from .dataer import Dataer
from .node import Node
from .node_info import NodeInfo
from .saver import Saver


class DataNode(Node):
    def __init__(
        self,
        info: NodeInfo,
        *,
        dataer: Dataer,
        saver: Saver,
        save_data: bool = False,
    ) -> None:
        if not isinstance(dataer, Dataer) or not isinstance(saver, Saver):
            raise TypeError("数据节点必须提供 Dataer 和 Saver 实例")
        if type(save_data) is not bool:
            raise TypeError("save_data 必须是布尔值")
        super().__init__(info)
        self.dataer = dataer
        self.saver = saver
        self.save_data = save_data
