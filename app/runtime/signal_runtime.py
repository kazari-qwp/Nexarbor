"""Bounded asynchronous breadth-first execution, with one barrier per layer."""
import asyncio
import inspect
import time
from contextvars import Context
from dataclasses import dataclass
from copy import deepcopy
from contextlib import nullcontext
from .requester import as_requester, requester_id
from .signal_authority import current_authority, signal_authority
from domain.signals import validate_strength,validate_signal
from domain.signals import Signal,SignalDelivery,SignalContext
from domain.json_values import freeze,thaw
from .signal_work import LayerWork,current_work

@dataclass
class _Binding:
    handler:object
    access_strength:object

class SignalRuntime:
    def __init__(self,network,*,records=None,locks=None,checkpoint=None,history_limit=100,enabled=None):
        if type(history_limit) is not int or history_limit<1:raise ValueError('Invalid history_limit')
        self.network=network;self.checkpoint=checkpoint;self.history_limit=history_limit
        self.records={} if records is None else records
        self.locks=locks
        self.enabled=enabled if enabled is not None else lambda node:True
        self.bindings={};self._active={};self._node_locks={}

    def bind(self,node_id,handler,*,access_strength=0):
        if self.network.get(node_id) is None:raise KeyError(node_id)
        if not callable(handler):raise TypeError('A signal handler is required')
        if not callable(access_strength):validate_strength(access_strength)
        self.bindings[node_id]=_Binding(handler,access_strength)

    def unbind(self,node_id):self.bindings.pop(node_id,None)

    async def _save(self):
        if self.checkpoint:
            result=self.checkpoint()
            if inspect.isawaitable(result):await result

    def _authorize(self,signal):
        if self.network.get(signal.origin) is None:raise ValueError('Signal origin does not exist')
        acting=current_authority.get()
        requester=requester_id.get()
        if requester is not None and requester!=signal.origin:
            raise PermissionError('Signal exceeds sender identity')
        if acting is not None:
            if signal.origin!=acting.node_id or signal.strength>acting.strength:
                raise PermissionError('Signal exceeds sender identity or strength')
            if acting.channels is not None and not set(signal.channels)<=set(acting.channels):
                raise PermissionError('Nested signal exceeds current channel grant')

    def _scope(self,node_id,*,mutable=False):
        return nullcontext() if self.locks is None else self.locks.access([node_id],mutable=mutable)

    async def _process_owned(self,node,delivery,signal):
        binding=self.bindings.get(node.info.node_id)
        strength=binding.access_strength() if binding and callable(binding.access_strength) else binding.access_strength if binding else 0
        validate_strength(strength)
        with signal_authority(node.info.node_id,strength),as_requester(node.info.node_id):
            if not self.enabled(node):raise PermissionError('Signal target component is disabled')
            if binding is None:return dict(status='relay')
            value=binding.handler(SignalContext(signal,delivery))
            if not inspect.isawaitable(value):raise TypeError('Signal handlers must be asynchronous')
            result=await value
            return dict(status='processed',value=thaw(freeze(result)))

    async def _deliver(self,signal,incoming,entry):
        node_id=entry['node_id']
        lock=self._node_locks.setdefault(node_id,asyncio.Lock())
        async with lock,self._scope(node_id,mutable=node_id!=signal.origin):
            node=self.network.get(node_id)
            if node is None:raise ValueError('Signal interface target does not exist: '+node_id)
            remaining=validate_strength(node.aggregation.combine(incoming))+node.bias
            validate_signal(remaining)
            if remaining<0:return None
            entry['strength']=remaining
            delivery=SignalDelivery(node_id,entry['depth'],remaining,tuple(entry['path']),tuple(entry['parents']))
            if node_id==signal.origin:return delivery,dict(status='returned')
            return delivery,await self._process_owned(node,delivery,signal)

    async def _bounded(self,signal,incoming,entry,deadline):
        try:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('Signal deadline exceeded')
            return await asyncio.wait_for(self._deliver(signal,incoming,entry),min(max(86400,signal.node_timeout_seconds),left))
        except (asyncio.TimeoutError,TimeoutError):return None,dict(status='timed_out',error='Node processing deadline exceeded')
        except asyncio.CancelledError:raise
        except Exception as error:return None,dict(status='failed',error=str(error))

    async def _expand(self,source,signal,visited,returned):
        async with self._scope(source.node_id):
            node=self.network.get(source.node_id)
            if node is None:return []
            outgoing=[]
            for edge in node.links:
                target=edge.target_id
                is_return=target==signal.origin and signal.close_loop and not returned
                if target in visited and not is_return:continue
                channel=next((channel for channel in signal.channels if edge.allows(source.strength,channel)),None)
                if channel is None:continue
                incoming=edge.transmit(source.strength,channel)
                if incoming is not None:outgoing.append((target,validate_strength(incoming),source))
            return outgoing

    def emit(self, signal):
        if not isinstance(signal, Signal): raise TypeError('Expected Signal')
        self._authorize(signal)
        existing = self.records.get(signal.signal_id)
        if existing:
            if existing['signal'] != signal.to_dict(): raise ValueError('Signal ID was reused with different content')
            if existing['status'] in ('running', 'queued', 'interrupted'):
                raise RuntimeError('Signal already running or requires reconciliation')
            return dict(signal_id=signal.signal_id, status=existing['status'])
        self.records[signal.signal_id] = dict(signal=signal.to_dict(), status='queued',
            returned=False, deliveries=[], layers=[], started_at=time.time())
        # A new context severs the originating callback's lease and caller cancellation.
        task = asyncio.create_task(self._propagate(signal), context=Context())
        self._active[signal.signal_id] = task
        def finished(done):
            record = self.records[signal.signal_id]
            if done.cancelled() and record['status'] == 'queued':
                record.update(status='cancelled', finished_at=time.time())
            if not done.cancelled(): done.exception()  # retrieve detached failures
            self._active.pop(signal.signal_id, None)
        task.add_done_callback(finished)
        return dict(signal_id=signal.signal_id, status='queued')

    def status(self, signal_id): return deepcopy(self.records[signal_id])

    async def wait(self, signal_id):
        task = self._active.get(signal_id)
        if task: await asyncio.shield(task)
        return self.status(signal_id)

    async def propagate(self, signal):
        self.emit(signal)
        return await self.wait(signal.signal_id)

    async def _propagate(self,signal):
        record=dict(signal=signal.to_dict(),status='running',returned=False,deliveries=[],layers=[],started_at=time.time())
        self.records[signal.signal_id]=record
        self._active[signal.signal_id]=asyncio.current_task()
        deadline=time.monotonic()+max(86400,signal.timeout_seconds)
        visited={signal.origin};returned=False;depth=0;count=0
        frontier=[SignalDelivery(signal.origin,0,signal.strength,(signal.origin,),())]
        try:
            await self._save()
            while frontier:
                branches=await asyncio.gather(*(self._expand(source,signal,visited,returned) for source in frontier))
                pending={}
                for branch in branches:
                    for target,incoming,source in branch:
                        if target not in pending:pending[target]=[[incoming],source.path+(target,),[source.node_id]]
                        else:
                            item=pending[target];item[0].append(incoming)
                            if source.node_id not in item[2]:item[2].append(source.node_id)
                if not pending:break
                if depth>=signal.max_hops or count+len(pending)>signal.max_deliveries:
                    record['status']='budget_exhausted';record['error']='Signal hop or delivery budget exceeded';break
                if time.monotonic()>=deadline:
                    record['status']='timed_out';break
                depth+=1;count+=len(pending);layer=[];jobs=[]
                work=LayerWork(signal,deadline,record);work_token=current_work.set(work)
                for target,(incoming,path,parents) in pending.items():
                    entry=dict(node_id=target,depth=depth,strength=None,path=list(path),parents=parents,status='processing')
                    record['deliveries'].append(entry);layer.append(entry)
                    jobs.append(asyncio.create_task(self._bounded(signal,incoming,entry,deadline)))
                try:
                    outcomes=await asyncio.gather(*jobs)
                    await work.drain()
                except BaseException:
                    for job in jobs:job.cancel()
                    await asyncio.gather(*jobs,return_exceptions=True)
                    await work.cancel()
                    raise
                finally:current_work.reset(work_token)
                frontier=[];accepted=[]
                for entry,result in zip(layer,outcomes):
                    if result is None:
                        record['deliveries'].remove(entry)
                        continue
                    delivery,outcome=result
                    entry.update(outcome);accepted.append(entry);visited.add(entry['node_id'])
                    if entry['node_id']==signal.origin:returned=True
                    if outcome['status']=='returned':record['returned']=True
                    if outcome['status'] in ('processed','relay'):frontier.append(delivery)
                layer=accepted
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
        completed=[key for key in self.records if key not in self._active]
        for key in completed[:-self.history_limit]:
            record=self.records[key]
            record['deliveries']=[];record['layers']=[];record['compacted']=True

    async def close(self):
        active=[task for task in self._active.values() if task is not asyncio.current_task()]
        for task in active:task.cancel()
        if active:await asyncio.gather(*active,return_exceptions=True)
        await self._save()
