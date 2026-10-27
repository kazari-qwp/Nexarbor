"""调用链的原始请求者身份；不承载节点访问或路由权限。"""

from contextlib import contextmanager
from contextvars import ContextVar

requester_id = ContextVar("requester_id", default=None)


@contextmanager
def as_requester(node_id):
    token = requester_id.set(node_id)
    try:
        yield
    finally:
        requester_id.reset(token)


caller_id = ContextVar("caller_id", default=None)


@contextmanager
def as_caller(node_id):
    token = caller_id.set(node_id)
    try:
        yield
    finally:
        caller_id.reset(token)
