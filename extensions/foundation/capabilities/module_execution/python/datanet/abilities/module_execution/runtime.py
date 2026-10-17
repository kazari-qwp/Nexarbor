"""Invocation-local module graphs; only host-granted operations can run."""
import asyncio
import inspect
from threading import RLock
from datanet.core.application import Component, checked
from datanet.core.json_values import freeze, thaw
from datanet.abilities.langgraph_backend.backend import compile_graph, validate


class Plugin(Component):
    def install(self):
        self.lock=RLock(); self.running=set(); self.workers={}

    async def execute(self,node,graph,operations,event,context=None):
        if self.id not in self.r.enabled: raise PermissionError('Module executor is disabled')
        graph=validate(graph,operations)
        if any(not callable(fn) for fn in operations.values()): raise TypeError('Operation must be callable')
        with self.lock:
            if node in self.running or self.workers.get(node): raise RuntimeError('Previous module execution is still running or stopping')
            self.running.add(node)
        try:
            async def invoke(name,arguments):
                if self.id not in self.r.enabled: raise PermissionError('Module executor is disabled')
                fn=operations[name]
                try:
                    if inspect.iscoroutinefunction(fn): value=await fn(context,**arguments)
                    else:
                        worker=asyncio.create_task(asyncio.to_thread(fn,context,**arguments))
                        with self.lock: self.workers.setdefault(node,set()).add(worker)
                        def done(task):
                            with self.lock:
                                self.workers[node].discard(task)
                                if not self.workers[node]:self.workers.pop(node,None)
                            if not task.cancelled():task.exception()
                        worker.add_done_callback(done)
                        value=await asyncio.shield(worker)
                        if inspect.isawaitable(value): value=await value
                    return thaw(freeze(checked(value)))
                except asyncio.CancelledError: raise
                except Exception as error: raise RuntimeError('Operation '+name+' failed: '+str(error)) from error
            compiled=compile_graph(graph,invoke)
            result=await compiled.ainvoke({'event':thaw(freeze(event)),'results':{}},{'recursion_limit':1024,'callbacks':[]})
            return dict(results=result['results'])
        finally:
            with self.lock:self.running.discard(node)
