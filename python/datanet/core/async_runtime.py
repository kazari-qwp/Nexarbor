"""Backend-owned event loop, shared by access requests and detached waves."""
import asyncio
from threading import Thread, current_thread


class AsyncRuntime:
    def __init__(self):
        self.closed = False
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.loop.run_forever, name='nexarbor-core', daemon=True)
        self.thread.start()

    def run(self, awaitable, timeout=180):
        if self.closed:
            if hasattr(awaitable,'close'):awaitable.close()
            raise RuntimeError('Core runtime is closed')
        if current_thread() is self.thread: raise RuntimeError('Cannot block the core event loop')
        async def invoke(): return await awaitable
        future = asyncio.run_coroutine_threadsafe(invoke(), self.loop)
        try: return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise

    def close(self):
        if self.closed:return
        async def shutdown():
            tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.run(shutdown())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
        self.loop.close()
        self.closed = True
