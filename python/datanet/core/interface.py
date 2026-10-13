"""来源节点独立持有的不可变连接。private 是遍历边界，不是身份认证。"""
from dataclasses import dataclass
import math

def validate_signal(value):
    if type(value) not in (int, float) or (type(value) is float and (not math.isfinite(value))):
        raise ValueError('内部信号必须为有限数值')
    return value

def validate_strength(value):
    validate_signal(value)
    if value < 0:
        raise ValueError('访问强度必须为有限非负数')
    return value

@dataclass(frozen=True)
class Interface:
    target_node_id: str
    threshold: int = 0
    visibility: str = 'public'
    multiplier: float = 1

    def __post_init__(self):
        if not isinstance(self.target_node_id, str) or not self.target_node_id:
            raise ValueError('目标编号必须为非空字符串')
        validate_strength(self.threshold)
        if type(self.threshold) is not int:
            raise ValueError('连接门槛必须为非负整数')
        validate_strength(self.multiplier)
        if self.visibility not in ('public', 'private'):
            raise ValueError('visibility 必须为 public 或 private')

    def allows(self, *, origin_node_id, source_node_id, strength):
        validate_signal(strength)
        return strength >= self.threshold and (self.visibility == 'public' or origin_node_id == source_node_id)
