"""节点数据操作的抽象接口。"""

from abc import ABC, abstractmethod


class Dataer(ABC):
    """由具体实现提供读取与写入能力。"""

    @abstractmethod
    def read(self):
        pass

    @abstractmethod
    def write(self, value):
        pass
