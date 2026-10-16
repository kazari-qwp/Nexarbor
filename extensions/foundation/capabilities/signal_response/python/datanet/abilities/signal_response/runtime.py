"""Channel-matched node workflows; no application-specific activation rules."""
import asyncio
import inspect
from copy import deepcopy
from dataclasses import asdict
from datanet.core.application import Component,checked
from datanet.core.json_values import freeze,thaw
from .services import validate


def resolve(value,data):
    if isinstance(value,dict):
        if set(value)=={'$ref'}:
            pointer=value['$ref']
            if not isinstance(pointer,str) or not pointer.startswith('/'):raise ValueError('Parameter reference must be a JSON Pointer')
            current=data
            for raw in pointer[1:].split('/'):
                key=raw.replace('~1','/').replace('~0','~')
                if isinstance(current,list):current=current[int(key)]
                elif isinstance(current,dict):current=current[key]
                else:raise ValueError('Parameter reference enters a scalar')
            return deepcopy(current)
        return {k:resolve(v,data) for k,v in value.items()}
    if isinstance(value,list):return [resolve(v,data) for v in value]
    return value


class Plugin(Component):
    def install(self):self.tools={};self.workers={}

    def bind(self,node_id,responders,tools,*,access_strength=0,on_error=None):
        rules=validate(responders)
        if any(not callable(fn) for fn in tools.values()):raise TypeError('Response tool must be callable')
        if any(step['tool'] not in tools for rule in rules for step in rule['steps']):raise PermissionError('Response references a tool not granted to this node')
        saved=self.r.backend.extension_state.get('signal_response',{}).get(node_id)
        if saved!=rules:self.r.rpc('signal_response_configure',actor='root',target=node_id,responders=rules)
        self.tools[node_id]=dict(tools)
        # A new binding captures configuration and grants; the signal cannot choose tools.
        async def handle(context):
            try:return await self.dispatch(context,rules,dict(tools))
            except BaseException as error:
                if on_error:
                    try:await on_error(context,error)
                    except Exception as cleanup_error:error.add_note('Response cleanup failed: '+str(cleanup_error))
                raise
        self.r.backend.signals.bind(node_id,handle,access_strength=access_strength)

    async def call(self,node,fn,context,arguments):
        if inspect.iscoroutinefunction(fn):return await fn(context,**arguments)
        worker=asyncio.create_task(asyncio.to_thread(fn,context,**arguments));self.workers[node]=worker
        def done(task):
            if self.workers.get(node) is task:self.workers.pop(node,None)
            if not task.cancelled():task.exception()
        worker.add_done_callback(done)
        result=await asyncio.shield(worker)
        return await result if inspect.isawaitable(result) else result

    async def dispatch(self,context,rules,tools):
        node=context.delivery.node_id;previous=self.workers.get(node)
        if previous and not previous.done():raise RuntimeError('Previous response tool is still stopping')
        completed=[];channels=set(context.signal.channels)
        for rule in rules:
            if not channels.intersection(rule['channels']):continue
            steps=[]
            for index,step in enumerate(rule['steps']):
                data=dict(signal=context.signal.to_dict(),delivery=asdict(context.delivery),steps=steps,responders=completed)
                try:
                    arguments=resolve(step['arguments'],data)
                    value=checked(await self.call(node,tools[step['tool']],context,arguments))
                    steps.append(dict(tool=step['tool'],value=thaw(freeze(value))))
                except asyncio.CancelledError:raise
                except Exception as error:raise RuntimeError(f"Responder {rule['id']} step {index+1} ({step['tool']}) failed: {error}") from error
            completed.append(dict(id=rule['id'],steps=steps))
        return dict(matched=len(completed),responders=completed)
