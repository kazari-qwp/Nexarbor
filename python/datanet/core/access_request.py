"""Eager, structured access tasks with explicit result observation."""
import asyncio


class AccessRequest:
    def __init__(self, coroutine):
        self.task = asyncio.create_task(coroutine)
        self.observed = False

    def __await__(self):
        self.observed = True
        return self.task.__await__()

    def cancel(self): return self.task.cancel()
    def done(self): return self.task.done()
