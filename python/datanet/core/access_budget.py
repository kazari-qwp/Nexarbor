"""Nested network operations inherit a budget and visited nodes."""
from contextvars import ContextVar
from contextlib import contextmanager
current_access = ContextVar('current_network_access', default=None)
active_agent = ContextVar('active_network_agent', default=None)

@contextmanager
def access_context(network, node_id, strength, path):
    previous = current_access.get()
    visited = previous['visited'] if previous is not None and previous['network'] is network else set()
    visited.update(path)
    token = current_access.set({'network': network, 'node_id': node_id, 'strength': strength, 'visited': visited})
    try:
        yield
    finally:
        current_access.reset(token)
