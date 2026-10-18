"""Configurable module workflows; LangGraph schedules, the core authorizes."""
import asyncio
from dataclasses import asdict
from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult
from datanet.abilities.langgraph_backend.backend import compile_graph, validate, resolve


async def execute(ctx, activation):
    operations = ctx.config['operations']
    graphs = {name: validate(plan, operations) for name, plan in ctx.config['graphs'].items()}
    for rule in ctx.config.get('on_signal', ()):
        if rule['graph'] not in graphs: raise ValueError('Unknown signal execution graph: '+rule['graph'])

    if activation.kind == 'access':
        if activation.operation != 'run': return ComponentResult(status='error', error='Unknown executor operation')
        graph = activation.parameters.get('graph', ctx.config.get('default_graph', 'main'))
        if graph not in graphs: return ComponentResult(status='error', error='Unknown execution graph: '+graph)
        selected = [graph]
        event = dict(kind='access', source=activation.source, input=thaw(activation.parameters.get('input', {})), signal=None, delivery=None)
    else:
        event = dict(kind='signal', source=activation.source, input=thaw(activation.signal.content),
            signal=activation.signal.to_dict(), delivery=asdict(activation.delivery))
        selected = []
        for rule in ctx.config.get('on_signal', ()):
            if rule.get('kind') is not None and rule['kind'] != activation.signal.kind: continue
            if rule.get('channels') and not set(rule['channels']).intersection(activation.signal.channels): continue
            try: matches = all(resolve({'$ref': pointer}, event) == thaw(value) for pointer, value in rule.get('where', {}).items())
            except (KeyError, IndexError, TypeError, ValueError): matches = False
            if matches: selected.append(rule['graph'])

    async def invoke(name, arguments):
        spec = operations[name]
        result = await ctx.network.call(spec.get('node', ctx.node_id), spec['module'], spec['operation'], arguments,
            channels=spec.get('channels'), strength=spec.get('strength'))
        if spec.get('require_success', True) and result['status'] != 'ok':
            raise RuntimeError('Operation '+name+' failed: '+str(result['error']))
        return result

    async def run():
        executions = []
        for name in selected:
            compiled = compile_graph(graphs[name], invoke)
            result = await compiled.ainvoke({'event': event, 'results': {}}, {'recursion_limit': 1024, 'callbacks': []})
            executions.append(dict(graph=name, results=result['results']))
        return dict(matched=len(executions), executions=executions)

    result = await asyncio.wait_for(run(), ctx.config.get('timeout_seconds', 60))
    return ComponentResult(data=result)
