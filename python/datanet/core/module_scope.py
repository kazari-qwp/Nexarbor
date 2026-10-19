"""Per-call identity and forwarded resource budget shared by the module runtime."""
from contextvars import ContextVar

executing_module=ContextVar('executing_node_module',default=None)
forward_strength=ContextVar('forward_module_strength',default=None)
