"""Bounded asynchronous breadth-first execution, with one barrier per layer."""
import asyncio
import inspect
import time
from contextvars import Context
from dataclasses import dataclass
from copy import deepcopy
from types import SimpleNamespace
from .access_budget import active_agent,current_access
from .interface import validate_strength,validate_signal
from .signals import Signal,SignalDelivery,SignalContext
from .json_values import freeze,thaw
from .signal_work import LayerWork,current_work

@dataclass
class _Binding:
    handler:object
    access_strength:object

class SignalRuntime:
    def __init__(self,network,*,checkpoint=None,history_limit=100):
        if type(history_limit) is not int or history_limit<1:raise ValueError('Invalid history_limit')
        self.network=network;self.checkpoint=checkpoint;self.history_limit=history_limit
        self.bindings={};self._active={};self._node_locks={}

    def bind(self,node_id,handler,*,access_strength=0):
        if node_id not in self.network.nodes:raise KeyError(node_id)
        if not callable(handler):raise TypeError('A signal handler is required')
        if not callable(access_strength):validate_strength(access_strength)
        self.bindings[node_id]=_Binding(handler,access_strength)

    def unbind(self,node_id):self.bindings.pop(node_id,None)

    async def _save(self):
        if self.checkpoint:
            result=self.checkpoint()
            if inspect.isawaitable(result):await result

    def _authorize(self,signal):
        if signal.origin not in self.network.nodes:raise ValueError('Signal origin does not exist')
        acting=active_agent.get()
        frame=current_access.get()
        if frame and frame['network'] is self.network:
            if signal.origin!=frame['node_id'] or signal.strength>frame['strength']:raise PermissionError('Nested signal exceeds current access budget')
            if not set(signal.channels)<=set(frame['channels']):raise PermissionError('Nested signal exceeds current channel grant')
        elif acting and (acting[1]!=signal.origin or signal.strength>acting[0].max_signal_strength):raise PermissionError('Signal exceeds sender identity or strength')

    def _snapshot(self,signal):
        # Snapshot nodes and interfaces before any handler runs. New topology applies next signal.
        return self.network.routing_snapshot()

    async def _process(self,node,delivery,signal,record):
        lock=self._node_locks.setdefault(node.node_id,asyncio.Lock())
        async with lock:
            locks = getattr(self.network, 'node_locks', None)
            if locks:
                async with locks.access([node.node_id]):
                    return await self._process_owned(node,delivery,signal,record)
            return await self._process_owned(node,delivery,signal,record)

    async def _return_to_origin(self,node,delivery,signal,record,deadline):
        locks=getattr(self.network,'node_locks',None)
        if not locks:return dict(status='returned')
        try:
            left=min(signal.node_timeout_seconds,deadline-time.monotonic())
            if left<=0:raise TimeoutError('Signal deadline exceeded')
            async def enter():
                async with locks.access([node.node_id],mutable=False):return dict(status='returned')
            return await asyncio.wait_for(enter(),left)
        except (TimeoutError,asyncio.TimeoutError):return dict(status='timed_out',error='Return node lock deadline exceeded')

    async def _process_owned(self,node,delivery,signal,record):
        binding=self.bindings.get(node.node_id)
        if binding:
            strength=binding.access_strength() if callable(binding.access_strength) else binding.access_strength
            validate_strength(strength)
        else:strength=0
        # A receiver executes under its own host-granted authority, never the sender's.
        principal=active_agent.set((SimpleNamespace(max_signal_strength=strength),node.node_id))
        frame=current_access.set(None)
        try:
            context=SignalContext(signal,delivery,self.network)
            from .component_registry import node_enabled
            if not node_enabled(node):raise PermissionError('Signal target component is disabled')
            if not binding:
                return dict(status='relay')
            value=binding.handler(context)
            if not inspect.isawaitable(value):raise TypeError('Signal handlers must be asynchronous')
            result=await value
            return dict(status='processed',value=thaw(freeze(result)))
        finally:
            current_access.reset(frame);active_agent.reset(principal)

    async def _bounded(self,node,delivery,signal,record,deadline):
        try:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('Signal deadline exceeded')
            return await asyncio.wait_for(self._process(node,delivery,signal,record),min(signal.node_timeout_seconds,left))
        except (asyncio.TimeoutError,TimeoutError):return dict(status='timed_out',error='Node processing deadline exceeded')
        except asyncio.CancelledError:raise
        except Exception as error:return dict(status='failed',error=str(error))

    def emit(self, signal):
        if not isinstance(signal, Signal): raise TypeError('Expected Signal')
        self._authorize(signal)
        existing = self.network.signal_runs.get(signal.signal_id)
        if existing:
            if existing['signal'] != signal.to_dict(): raise ValueError('Signal ID was reused with different content')
            if existing['status'] in ('running', 'queued', 'interrupted'):
                raise RuntimeError('Signal already running or requires reconciliation')
            return dict(signal_id=signal.signal_id, status=existing['status'])
        self.network.signal_runs[signal.signal_id] = dict(signal=signal.to_dict(), status='queued',
            returned=False, deliveries=[], layers=[], started_at=time.time())
        # A new context severs the originating callback's lease and caller cancellation.
        task = asyncio.create_task(self._propagate(signal), context=Context())
        self._active[signal.signal_id] = task
        def finished(done):
            record = self.network.signal_runs[signal.signal_id]
            if done.cancelled() and record['status'] == 'queued':
                record.update(status='cancelled', finished_at=time.time())
            if not done.cancelled(): done.exception()  # retrieve detached failures
            self._active.pop(signal.signal_id, None)
        task.add_done_callback(finished)
        return dict(signal_id=signal.signal_id, status='queued')

    def status(self, signal_id): return deepcopy(self.network.signal_runs[signal_id])

    async def wait(self, signal_id):
        task = self._active.get(signal_id)
        if task: await asyncio.shield(task)
        return self.status(signal_id)

    async def propagate(self, signal):
        self.emit(signal)
        return await self.wait(signal.signal_id)

    async def _propagate(self,signal):
        nodes,links,divergences=self._snapshot(signal)
        record=dict(signal=signal.to_dict(),status='running',returned=False,deliveries=[],layers=[],started_at=time.time())
        self.network.signal_runs[signal.signal_id]=record
        self._active[signal.signal_id]=asyncio.current_task()
        deadline=time.monotonic()+signal.timeout_seconds
        visited={signal.origin};returned=False;depth=0;count=0
        frontier=[SignalDelivery(signal.origin,0,signal.strength,(signal.origin,),())]
        try:
            await self._save()
            while frontier:
                pending={}
                for source in frontier:
                    for edge in links[source.node_id]:
                        target=edge.target_node_id
                        is_return=target==signal.origin and signal.close_loop and not returned
                        if target in visited and not is_return:continue
                        if not edge.carries(signal.channels,strength=source.strength):continue
                        if target not in nodes:raise ValueError('Signal interface target does not exist: '+target)
                        incoming=source.strength*edge.metadata.multiplier;validate_strength(incoming)
                        if target not in pending:pending[target]=[incoming,source.path+(target,),[source.node_id]]
                        else:
                            item=pending[target]
                            if incoming>item[0]:item[0],item[1]=incoming,source.path+(target,)
                            if source.node_id not in item[2]:item[2].append(source.node_id)
                if not pending:break
                if depth>=signal.max_hops or count+len(pending)>signal.max_deliveries:
                    record['status']='budget_exhausted';record['error']='Signal hop or delivery budget exceeded';break
                if time.monotonic()>=deadline:
                    record['status']='timed_out';break
                depth+=1;count+=len(pending);layer=[];required=[];jobs=[]
                work=LayerWork(signal,deadline,record);work_token=current_work.set(work)
                for target,(incoming,path,parents) in pending.items():
                    remaining=incoming+divergences[target];validate_signal(remaining)
                    if remaining<0:continue
                    delivery=SignalDelivery(target,depth,remaining,path,tuple(parents))
                    visited.add(target)
                    entry=dict(node_id=target,depth=depth,strength=remaining,path=list(path),parents=parents,status='processing')
                    record['deliveries'].append(entry);layer.append(entry)
                    if target==signal.origin:
                        returned=True
                        required.append((delivery,entry))
                        jobs.append(asyncio.create_task(self._return_to_origin(nodes[target],delivery,signal,record,deadline)))
                        continue
                    required.append((delivery,entry))
                    jobs.append(asyncio.create_task(self._bounded(nodes[target],delivery,signal,record,deadline)))
                try:
                    outcomes=await asyncio.gather(*jobs)
                    await work.drain()
                except BaseException:
                    for job in jobs:job.cancel()
                    await asyncio.gather(*jobs,return_exceptions=True)
                    await work.cancel()
                    raise
                finally:current_work.reset(work_token)
                frontier=[]
                for (delivery,entry),outcome in zip(required,outcomes):
                    entry.update(outcome)
                    if outcome['status']=='returned':record['returned']=True
                    if outcome['status'] in ('processed','relay'):frontier.append(delivery)
                record['layers'].append([e['node_id'] for e in layer])
                await self._save()
                failures=[e for e in layer if e['status'] in ('failed','timed_out')]
                if failures and signal.failure_policy=='stop':
                    record['status']='timed_out' if all(e['status']=='timed_out' for e in failures) else 'failed';break
            if record['status']=='running':
                record['status']='partial' if any(e['status'] in ('failed','timed_out') for e in record['deliveries']) else 'completed'
        except asyncio.CancelledError:
            record['status']='cancelled'
            for entry in record['deliveries']:
                if entry['status']=='processing':entry['status']='cancelled'
            raise
        except Exception as error:
            record.update(status='failed',error=str(error))
            for entry in record['deliveries']:
                if entry['status']=='processing':entry.update(status='failed',error=str(error))
            raise
        finally:
            record['finished_at']=time.time();self._active.pop(signal.signal_id,None)
            self._prune()
            await self._save()
        return deepcopy(record)

    async def cancel(self,signal_id):
        task=self._active.get(signal_id)
        if task:task.cancel()
        return task is not None

    def _prune(self):
        # Compact old detail, not identity: an old ID must never silently re-execute.
        completed=[key for key in self.network.signal_runs if key not in self._active]
        for key in completed[:-self.history_limit]:
            record=self.network.signal_runs[key]
            record['deliveries']=[];record['layers']=[];record['compacted']=True

    async def close(self):
        active=[task for task in self._active.values() if task is not asyncio.current_task()]
        for task in active:task.cancel()
        if active:await asyncio.gather(*active,return_exceptions=True)
        await self._save()
