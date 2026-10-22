"""Module capability dispatch; lifecycle and callback admission stay in local_modules."""
import asyncio
import inspect
import time
from .access_request import AccessRequest
from .access_budget import access_context
from .module_values import json_copy
from .module_scope import forward_strength
from .module_queries import QUERY_OPERATIONS,query_request

def dispatch_request(runtime,key,operation,p):
    frame = runtime._scope(key); instance = runtime._check(key)
    node, network = runtime.backend.network.nodes[key[0]], runtime.backend.network
    if isinstance(p.get('target'),str):p=dict(p,target=network.resolve_reference(key[0],p['target']))
    if operation=='call_path':return json_copy(frame['call_path'])
    if operation=='resolve_channels':
        from .channel_filters import resolve
        return [c for c in resolve(p['values'],p['mode'],network.channel_names() if p['mode']=='deny' else ()) if c in frame['channels']]
    if operation=='filter_channels':
        from .channel_filters import resolve
        field=p['field'];mode=instance.config.get('channel_modes',{}).get(field,'allow');selected=resolve(instance.config.get(field,p['default']),mode,network.channel_names() if mode=='deny' else ())
        return [c for c in selected if c in frame['channels']]
    if operation=='local_call':
        local=p.get('target')
        if local is None:
            candidates=[n for n in network.local_family(key[0]) if (n,p['module']) in runtime.instances]
            if (key[0],p['module']) in runtime.instances:local=key[0]
            elif len(candidates)==1:local=candidates[0]
            else:raise ValueError('本地模块不存在或有多个实例，请指定 target')
        if not network.same_family(key[0],local):raise PermissionError('本地调用只能访问同一归属树')
        target_key=(local,p['module']);callee=runtime._check(target_key)
        if p['operation'] not in callee.operations:raise PermissionError('本地模块未声明该操作')
        if frame['trace']['calls']>=frame['trace'].get('max_calls',1000000) or time.monotonic()>=frame['trace']['deadline']:raise RuntimeError('Access request resource budget exhausted')
        frame['trace']['calls']+=1
        request=AccessRequest(runtime._run(target_key,callee.operations[p['operation']][0],**json_copy(p['arguments'])))
        frame['children'].append(request);return request
    if operation=='signal_id':
        from .signal_work import current_work
        work=current_work.get();return work.signal_id if work else None
    if operation=='post':
        from .signal_work import current_work
        work=current_work.get()
        if work is None:raise RuntimeError('Deferred access requires an active signal layer')
        strength,channels=runtime._budget(key,p);runtime._route(key,p['target'],strength,channels)
        generation=frame['generation'];arguments=json_copy(p['arguments'])
        runtime._accessible(key[0],p['target'],p['module'],p['operation'],strength,channels)
        async def later():
            runtime._check(key,generation)
            return await runtime.access(key[0],p['target'],p['module'],p['operation'],arguments,strength=strength,channels=channels)
        return work.post(later,p['target']+'/'+p['module']+'/'+p['operation'])
    if operation == 'lock_nodes':
        strength, channels = runtime._budget(key,p)
        start = len(frame['children'])
        async def finish(cancel):
            index = start
            while index < len(frame['children']):
                batch = frame['children'][index:]; index = len(frame['children'])
                if cancel:
                    for child in batch: child.cancel()
                results = await asyncio.gather(*(child.task for child in batch), return_exceptions=True)
                if not cancel:
                    for child, result in zip(batch,results):
                        if isinstance(result,BaseException) and not child.observed: raise result
        scope = runtime.backend.node_locks.transaction(key[0],p['nodes'],strength=strength,channels=channels,
            timeout=p['timeout'],validate=lambda:runtime._budget(key,p),finish=finish)
        frame['scopes'].append(scope)
        return scope
    if operation == 'patch_edges':
        from .edge_changes import edge_changes
        changes=edge_changes(json_copy(p['changes']));p=dict(p);p['strength'],p['channels']=runtime._budget(key,p)
        targets=tuple(dict.fromkeys(n for change in changes for n in (change['source'],change['edge'].target_node_id)))
        async def patch():
            async with runtime.backend.node_locks.access(targets):
                strength,channels=runtime._budget(key,p)
                with runtime.backend._transaction_lock:
                    for target in targets:runtime._route(key,target,strength,channels)
                    for change in changes:
                        if not set(change['edge'].metadata.channels)<=set(channels):raise PermissionError('连接频道不能超过模块授权')
                    pending={source:list(network.nodes[source].interfaces) for source in {c['source'] for c in changes}}
                    for change in changes:
                        edges=pending[change['source']];edge=change['edge']
                        if change['action']=='remove':edges[:]=[old for old in edges if old!=edge]
                        elif edge not in edges:edges.append(edge)
                    for source,edges in pending.items():network.nodes[source].interfaces=edges
                return dict(changed=len(changes))
        request=AccessRequest(patch());frame['children'].append(request);return request
    if operation in QUERY_OPERATIONS:return query_request(runtime,key,operation,p)
    if operation in ('signal_status', 'signal_wait', 'signal_cancel'):
        if operation == 'signal_wait' and runtime.backend.node_locks.current:
            raise RuntimeError('Wait for independent signals after releasing node locks')
        signal_id = p['signal_id']
        record = network.signal_runs.get(signal_id)
        if not record or record['signal']['origin'] != key[0]:
            raise PermissionError('Only the emitting node can manage its signal receipt')
        if operation == 'signal_status': return runtime.backend.signals.status(signal_id)
        async def manage():
            runtime._scope(key)
            if operation == 'signal_wait':return await runtime.backend.signals.wait(signal_id)
            return await runtime.backend.signals.cancel(signal_id)
        request = AccessRequest(manage())
        frame['children'].append(request)
        return request
    if operation == 'caller': return frame['caller']
    if operation == 'requester': return frame['requester']
    if operation == 'local_metadata': return json_copy(node.get_metadata())
    if operation == 'publish_metadata':
        runtime.backend.node_locks.require_mutable(key[0])
        if not isinstance(p['fields'], dict): raise ValueError('Metadata fields must be an object')
        runtime._published[key] = json_copy(p['fields'])
        network.metadata_registry.register('module:' + repr(key),
            lambda target: runtime._metadata_fields(key, target))
        return None
    if operation == 'schema': return json_copy(node.get_schema())
    if operation == 'read': return json_copy(node.read(json_copy(p['request'])))
    if operation == 'write':
        runtime.backend.node_locks.require_mutable(key[0])
        return json_copy(node.write(p['key'], json_copy(p['value']), mode=p['mode']))
    if operation == 'inputs':
        runtime.backend.node_locks.require_mutable(key[0])
        def reject_files(value):
            if isinstance(value, dict):
                if 'file' in value: raise PermissionError('Modules cannot load arbitrary document paths')
                for item in value.values(): reject_files(item)
            elif isinstance(value, (list, tuple)):
                for item in value: reject_files(item)
        patch = json_copy(p['patch']); reject_files(patch)
        if not hasattr(node, 'inputs'): raise TypeError('Only Agent nodes have input surfaces')
        return json_copy(node.inputs.update('module:' + key[1], patch))
    if operation == 'extended':
        handler = runtime._extension(key[1])
        policy = runtime._access[key].get('extension')
        if not handler or not policy or p['operation'] not in policy['operations']:
            raise PermissionError('Extended operation was not explicitly granted')
        arguments=json_copy(p['arguments'])
        async def extended():
            targets=[arguments[field] for field in ('source','target') if isinstance(arguments.get(field),str)]
            if p['operation']=='nodes':targets=[n for n in network.nodes if '*' in policy['targets'] or n in policy['targets']]
            async with runtime.backend.node_locks.access(targets,mutable=p['operation'] in ('connect','disconnect')):
                runtime._scope(key)
                value=handler(runtime.backend,key[0],policy,p['operation'],arguments)
                if inspect.isawaitable(value):value=await value
                return json_copy(value)
        request=AccessRequest(extended());frame['children'].append(request);return request
    if operation in ('call', 'invoke'):
        p = dict(p)
        p['arguments'] = json_copy(p['arguments'])
        p['strength'], p['channels'] = runtime._budget(key, p)
        # Schedule immediately: independent requests overlap even before awaited.
        async def invoke():
            async with runtime.backend.node_locks.access([p['target']]):
                return await entered()
        async def entered():
            strength, channels = runtime._budget(key, p)
            target, _, _ = runtime._route(key, p['target'], strength, channels)
            if operation == 'call':
                target_key = (p['target'], p['module'])
                callee = runtime._check(target_key)
                entry = callee.operations.get(p['operation'])
                if entry is None: raise PermissionError('No accessible module operation')
                function,_ = entry
                declared=runtime._operation_channels(target_key,p['operation'])
            else:
                if p['tool'].startswith('module:'):
                    from .module_tools import ModuleTools
                    module,separator,tool_id=p['tool'][7:].partition('/')
                    if not separator:raise ValueError('模块工具引用无效')
                    value=await ModuleTools(runtime.backend).invoke(key[0],dict(node_id=p['target'],module=module,tool_id=tool_id),p['arguments'],strength=strength,channels=channels)
                    runtime._scope(key);return value
                if ':' in p['tool']:
                    value = await runtime.backend.external_tools.invoke(key[0], p['target'], p['tool'],
                        p['arguments'], strength=strength, channels=channels)
                    runtime._scope(key)
                    return value
                if p['tool'] not in target.expose or p['tool'] not in target.tool_definitions:
                    raise PermissionError('No accessible node tool')
                definition = target.tool_definitions[p['tool']]
                declared = definition['access_channels']
                from .tool_access import validate_arguments
                validate_arguments(p['arguments'], definition['parameters'])
                function = target.tools[p['tool']]
            selected = tuple(c for c in channels if c in declared)
            if (declared or p['target'] != key[0]) and not selected:
                raise PermissionError('Endpoint channel is not granted')
            _, path, remaining = runtime._route(key, p['target'], strength, selected)
            with access_context(network, p['target'], remaining, path, channels=selected):
                forwarded=forward_strength.set(remaining if operation=='call' and p.get('forward') else None)
                try:
                    if operation == 'call': result = runtime._run(target_key, function, **json_copy(p['arguments']))
                    else: result = function(**json_copy(p['arguments']))
                    if inspect.isawaitable(result):result=await result
                finally:forward_strength.reset(forwarded)
                runtime._scope(key)
                return json_copy(result)
        trace = frame['trace']
        if trace['calls'] >= trace.get('max_calls',1000000) or time.monotonic() >= trace['deadline']:
            raise RuntimeError('Access request resource budget exhausted')
        trace['calls'] += 1
        task = AccessRequest(invoke())
        frame['children'].append(task)
        return task
    strength, channels = runtime._budget(key, p)
    if operation == 'emit':
        from .signals import Signal
        allowed = {'kind', 'sequence', 'close_loop', 'failure_policy', 'max_hops', 'max_deliveries',
                   'timeout_seconds', 'node_timeout_seconds', 'parent_id'}
        if set(p['options']) - allowed: raise PermissionError('Module cannot override signal identity')
        signal = Signal(key[0], channels, strength, content=p['content'],**p['options'])
        return runtime.backend.signals.emit(signal)
    raise ValueError('Unknown local module request: ' + operation)
