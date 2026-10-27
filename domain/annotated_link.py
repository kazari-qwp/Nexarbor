"""连接的应用属性；传播仍使用基础 Link 行为。"""

from dataclasses import dataclass, field

from domain.core import Link
from domain.json_values import freeze


@dataclass(eq=False)
class AnnotatedLink(Link):
    attributes: dict = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        self.attributes = freeze(self.attributes)
