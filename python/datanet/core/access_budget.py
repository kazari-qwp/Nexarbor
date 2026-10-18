"""Nested network operations inherit a budget and visited nodes."""
from contextvars import ContextVar
from contextlib import contextmanager
current_access = ContextVar('current_network_access', default=None)
active_agent = ContextVar('active_network_agent', default=None)

def current_agent_id():
    principal=active_agent.get()
    return principal[1] if principal is not None else None

@contextmanager
def access_context(network, node_id, strength, path, *, channels=None):
    previous = current_access.get()
    # A call stack, not a global blacklist: siblings can reuse an endpoint after
    # return, while recursive calls cannot walk back through their ancestors.
    visited = set(previous['visited']) if previous is not None and previous['network'] is network else set()
    if channels is None:channels=previous['channels'] if previous is not None and previous['network'] is network else ()
    if previous is not None and previous['network'] is network and not set(channels)<=set(previous['channels']):raise ValueError('嵌套访问不能扩大访问频道')
    visited.update(path)
    token = current_access.set({'network': network, 'node_id': node_id, 'strength': strength, 'visited': visited,'channels':tuple(channels)})
    try:
        yield
    finally:
        current_access.reset(token)
