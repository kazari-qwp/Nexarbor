"""信号发起身份与预算；不提供图访问入口。"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from domain.signals import validate_strength


@dataclass(frozen=True)
class SignalAuthority:
    node_id: str
    strength: float
    channels: tuple | None = None


current_authority = ContextVar('signal_authority', default=None)


@contextmanager
def signal_authority(node_id, strength, channels=None):
    authority = SignalAuthority(node_id, validate_strength(strength), None if channels is None else tuple(channels))
    token = current_authority.set(authority)
    try:
        yield
    finally:
        current_authority.reset(token)
