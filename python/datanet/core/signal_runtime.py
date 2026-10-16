"""Bounded asynchronous breadth-first execution, with one barrier per layer."""
import asyncio
import inspect
import time
from dataclasses import dataclass
from copy import deepcopy
from types import SimpleNamespace
from .access_budget import active_agent,current_access
from .interface import validate_strength,validate_signal
from .signals import Signal,SignalDelivery,SignalContext
from .json_values import freeze,thaw,names

@dataclass
class _Binding:
    handler:object
    capabilities:object
    access_strength:object
    permission_checker:object=None

class SignalRuntime:
    def __init__(self,network,*,checkpoint=None,history_limit=100):
        if type(history_limit) is not int or history_limit<1:raise ValueError('Invalid history_limit')
        self.network=network;self.checkpoint=checkpoint;self.history_limit=history_limit
        self.bindings={};self._active={};self._notifications={};self._notification_ids={};self._node_locks={}

    def bind(self,node_id,handler,*,capabilities=(),access_strength=0,permission_checker=None):
        if node_id not in self.network.nodes:raise KeyError(node_id)
        if not callable(handler):raise TypeError('A signal handler is required')
        if not callable(capabilities):capabilities=names(capabilities,'capabilities')
        if not callable(access_strength):validate_strength(access_strength)
        if permission_checker is not None and not callable(permission_checker):raise TypeError('Invalid permission checker')
        self.bindings[node_id]=_Binding(handler,capabilities,access_strength,permission_checker)

    def unbind(self,node_id):self.bindings.pop(node_id,None)

    async def _save(self):
        if self.checkpoint:
            result=self.checkpoint()
            if inspect.isawaitable(result):await result

    def _authorize(self,signal):
        if signal.origin not in self.network.nodes:raise ValueError('Signal origin does not exist')
        acting=active_agent.get()
        if acting and (acting[1]!=signal.origin or signal.strength>acting[0].max_signal_strength):raise PermissionError('Signal exceeds sender identity or strength')
        frame=current_access.get()
        if frame and frame['network'] is self.network:
            if signal.origin!=frame['node_id'] or signal.strength>frame['strength']:raise PermissionError('Nested signal exceeds current access budget')

    def _snapshot(self,signal):
        # Snapshot nodes and interfaces before any handler runs. New topology applies next signal.
        nodes=dict(self.network.nodes)
        links={k:tuple(getattr(n,signal.direction+'_interfaces')) for k,n in nodes.items()}
        divergences={k:n.divergence for k,n in nodes.items()}
        return nodes,links,divergences

    async def _matches(self,node,binding,context):
        f=context.signal.activation
        if f.types:
            from .component_registry import codec_for_node
            aliases={node.signal_type,codec_for_node(node).type_id}
            if not aliases.intersection(f.types):return False
        if f.node_ids and node.node_id not in f.node_ids:return False
        capabilities=binding.capabilities() if binding and callable(binding.capabilities) else binding.capabilities if binding else ()
        if not set(f.required_tools).issubset(capabilities):return False
        for permission in f.permissions:
            if binding and binding.permission_checker:
                allowed=binding.permission_checker(node,permission)
                if inspect.isawaitable(allowed):allowed=await allowed
                if type(allowed) is not bool:raise TypeError('Permission checker must return a boolean')
                if not allowed:return False
            else:
                if not binding:return False
                strength=binding.access_strength() if callable(binding.access_strength) else binding.access_strength
                reachable=next((n for n,_,_ in self.network.walk_states(node.node_id,direction=permission.direction,strength=strength) if n.node_id==permission.target),None)
                if reachable is None:return False
                if permission.tool:
                    spec=reachable.tool_definitions.get(permission.tool)
                    if not spec or permission.tool not in reachable.expose or permission.tool not in reachable.tools:return False
                    if spec['read_only']!=(permission.direction=='read'):return False
        return True

    async def _process(self,node,delivery,signal,record):
        lock=self._node_locks.setdefault(node.node_id,asyncio.Lock())
        async with lock:
            return await self._process_owned(node,delivery,signal,record)

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
            if not await self._matches(node,binding,context):return dict(status='filtered')
            from .component_registry import node_enabled
            if not node_enabled(node):raise PermissionError('Signal target component is disabled')
            if not binding:
                if node.signal_type=='agent':raise RuntimeError('Agent has no host signal handler')
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

    async def _notify(self,node,delivery,signal,record,entry,deadline):
        try:
            entry.update(await self._bounded(node,delivery,signal,record,deadline))
        except asyncio.CancelledError:
            entry.update(status='cancelled');raise

    async def propagate(self,signal):
        if not isinstance(signal,Signal):raise TypeError('Expected Signal')
        self._authorize(signal)
        existing=self.network.signal_runs.get(signal.signal_id)
        if existing:
            if existing['signal']!=signal.to_dict():raise ValueError('Signal ID was reused with different content')
            if signal.signal_id in self._active:raise RuntimeError('Signal is already running')
            if existing['status'] in ('running','interrupted'):raise RuntimeError('Interrupted signal requires reconciliation; it is not replayed automatically')
            return deepcopy(existing)
        nodes,links,divergences=self._snapshot(signal)
        record=dict(signal=signal.to_dict(),status='running',returned=False,deliveries=[],layers=[],started_at=time.time())
        self.network.signal_runs[signal.signal_id]=record
        self._active[signal.signal_id]=asyncio.current_task()
        self._notifications[signal.signal_id]=set();self._notification_ids[signal.signal_id]={}
        deadline=time.monotonic()+signal.timeout_seconds
        visited={signal.origin};returned=False;depth=0;count=0
        frontier=[SignalDelivery(signal.origin,0,signal.strength,(signal.origin,),(),True)]
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
                        if target not in pending:pending[target]=[incoming,source.path+(target,),[source.node_id],edge.metadata.wait_for_completion]
                        else:
                            item=pending[target]
                            if incoming>item[0]:item[0],item[1]=incoming,source.path+(target,)
                            if source.node_id not in item[2]:item[2].append(source.node_id)
                            item[3]=item[3] or edge.metadata.wait_for_completion
                if not pending:break
                if depth>=signal.max_hops or count+len(pending)>signal.max_deliveries:
                    record['status']='budget_exhausted';record['error']='Signal hop or delivery budget exceeded';break
                if time.monotonic()>=deadline:
                    record['status']='timed_out';break
                depth+=1;count+=len(pending);layer=[];required=[];jobs=[]
                for target,(incoming,path,parents,wait) in pending.items():
                    remaining=incoming+divergences[target];validate_signal(remaining)
                    if remaining<0:continue
                    delivery=SignalDelivery(target,depth,remaining,path,tuple(parents),wait)
                    visited.add(target)
                    entry=dict(node_id=target,depth=depth,strength=remaining,path=list(path),parents=parents,wait_for_completion=wait,status='processing')
                    record['deliveries'].append(entry);layer.append(entry)
                    if target==signal.origin:
                        returned=True;record['returned']=True;entry['status']='returned';continue
                    if not wait:
                        # Non-ready subscriptions are terminal notifications, not timing relays.
                        entry['status']='notified'
                        task=asyncio.create_task(self._notify(nodes[target],delivery,signal,record,entry,deadline))
                        self._notifications[signal.signal_id].add(task);self._notification_ids[signal.signal_id][target]=task
                        continue
                    required.append((delivery,entry))
                    jobs.append(asyncio.create_task(self._bounded(nodes[target],delivery,signal,record,deadline)))
                try:outcomes=await asyncio.gather(*jobs)
                except BaseException:
                    for job in jobs:job.cancel()
                    await asyncio.gather(*jobs,return_exceptions=True)
                    raise
                frontier=[]
                for (delivery,entry),outcome in zip(required,outcomes):
                    entry.update(outcome)
                    if outcome['status'] in ('processed','filtered','relay'):frontier.append(delivery)
                record['layers'].append([e['node_id'] for e in layer])
                await self._save()
                failures=[e for e in layer if e['wait_for_completion'] and e['status'] in ('failed','timed_out')]
                if failures and signal.failure_policy=='stop':
                    record['status']='timed_out' if all(e['status']=='timed_out' for e in failures) else 'failed';break
            if record['status']=='running':
                record['status']='partial' if any(e['wait_for_completion'] and e['status'] in ('failed','timed_out') for e in record['deliveries']) else 'completed'
        except asyncio.CancelledError:
            record['status']='cancelled'
            for entry in record['deliveries']:
                if entry['status']=='processing':entry['status']='cancelled'
            await self.cancel_notifications(signal.signal_id)
            raise
        except Exception as error:
            record.update(status='failed',error=str(error));raise
        finally:
            record['finished_at']=time.time();self._active.pop(signal.signal_id,None)
            self._prune()
            await self._save()
        return deepcopy(record)

    async def drain_notifications(self,signal_id):
        tasks=self._notifications.get(signal_id,set())
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        await self._save()
        return deepcopy(self.network.signal_runs[signal_id])

    async def cancel_notifications(self,signal_id):
        tasks=self._notifications.get(signal_id,set())
        for task in tasks:
            if not task.done():task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

    async def cancel(self,signal_id):
        task=self._active.get(signal_id)
        if task:task.cancel()
        await self.cancel_notifications(signal_id)
        return task is not None

    def _prune(self):
        # Compact old detail, not identity: an old ID must never silently re-execute.
        completed=[key for key in self.network.signal_runs
                   if key not in self._active and not any(not t.done() for t in self._notifications.get(key,()))]
        for key in completed[:-self.history_limit]:
            record=self.network.signal_runs[key]
            record['deliveries']=[];record['layers']=[];record['compacted']=True
            self._notifications.pop(key,None);self._notification_ids.pop(key,None)

    async def close(self):
        active=[task for task in self._active.values() if task is not asyncio.current_task()]
        for task in active:task.cancel()
        if active:await asyncio.gather(*active,return_exceptions=True)
        for signal_id in list(self._notifications):await self.cancel_notifications(signal_id)
        await self._save()
