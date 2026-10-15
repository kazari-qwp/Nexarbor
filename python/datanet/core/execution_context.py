"""Executor-neutral context shared by nested tool and executor calls."""
from contextvars import ContextVar

call_chain = ContextVar('execution_call_chain', default=())
request_budget = ContextVar('execution_request_budget', default=None)
task_completion = ContextVar('execution_completion', default=None)
