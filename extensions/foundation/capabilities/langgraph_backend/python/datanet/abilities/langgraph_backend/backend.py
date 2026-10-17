"""Compile bounded, structured module plans using the official LangGraph runtime."""
from copy import deepcopy
from typing import Annotated, TypedDict


def resolve(value, data):
    if isinstance(value, dict):
        if set(value) == {'$ref'}:
            pointer = value['$ref']
            if not isinstance(pointer, str) or not pointer.startswith('/'):
                raise ValueError('Reference must be a JSON Pointer')
            current = data
            for raw in pointer[1:].split('/'):
                key = raw.replace('~1', '/').replace('~0', '~')
                current = current[int(key)] if isinstance(current, list) else current[key]
            return deepcopy(current)
        return {k: resolve(v, data) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, data) for v in value]
    return value


def validate(plan, operations):
    from datanet.core.json_values import freeze, thaw
    plan = thaw(freeze(plan)); ids = set(); count = 0
    def walk(p, depth=0):
        nonlocal count
        count += 1
        if depth > 16 or count > 256: raise ValueError('Execution graph is too large')
        if not isinstance(p, dict): raise ValueError('Expected a structured execution block')
        kind = p.get('type')
        if kind == 'call':
            if set(p) != {'type','id','operation','arguments'}: raise ValueError('Invalid call fields')
            if not isinstance(p['id'], str) or not p['id'] or p['id'] in ids: raise ValueError('Duplicate or empty execution ID')
            ids.add(p['id'])
            if p['operation'] not in operations: raise PermissionError('Operation is not granted: '+str(p['operation']))
            if not isinstance(p['arguments'], dict): raise ValueError('Arguments must be an object')
        elif kind in ('sequence','parallel'):
            if set(p) != {'type','steps'} or not isinstance(p['steps'], list): raise ValueError('Invalid execution group')
            if kind == 'parallel' and not p['steps']: raise ValueError('Parallel requires at least one branch')
            for child in p['steps']: walk(child, depth+1)
        elif kind == 'branch':
            if set(p) != {'type','select','cases','default'} or not isinstance(p['cases'], dict) or not p['cases']: raise ValueError('Invalid branch')
            if not isinstance(p['select'], dict) or set(p['select']) != {'$ref'}: raise ValueError('Branch requires a result reference')
            for child in [*p['cases'].values(), p['default']]: walk(child, depth+1)
        else: raise ValueError('Unknown execution block: '+str(kind))
    walk(plan)
    return plan


def merge(left, right):
    overlap = set(left).intersection(right)
    if overlap: raise ValueError('Execution result written twice: '+','.join(sorted(overlap)))
    return {**left, **right}


class State(TypedDict):
    event: dict
    results: Annotated[dict, merge]


def compile_graph(plan, invoke):
    from langgraph.graph import StateGraph, START, END
    # Each group is a subgraph. A conditional branch has ONE completed successor;
    # the enclosing parallel join never waits for its unselected internal branches.
    def build(p):
        g = StateGraph(State); kind = p['type']
        if kind == 'call':
            async def call(state):
                args = resolve(p['arguments'], state)
                result = await invoke(p['operation'], args)
                return {'results': {p['id']: {'operation': p['operation'], 'value': result}}}
            g.add_node('call', call); g.add_edge(START, 'call'); g.add_edge('call', END)
        else:
            children = p['steps'] if kind in ('sequence','parallel') else [*p['cases'].values(),p['default']]
            names = []
            for index, child in enumerate(children):
                compiled = build(child); name = 'block_'+str(index); names.append(name)
                async def block(state, compiled=compiled):
                    result = await compiled.ainvoke(state, {'recursion_limit': 1024, 'callbacks': []})
                    return {'results': {k:v for k,v in result['results'].items() if k not in state['results']}}
                g.add_node(name, block)
            if not names: g.add_edge(START, END)
            elif kind == 'sequence':
                g.add_edge(START, names[0])
                for a,b in zip(names,names[1:]): g.add_edge(a,b)
                g.add_edge(names[-1], END)
            elif kind == 'parallel':
                for name in names: g.add_edge(START, name)
                g.add_node('join', lambda state: {})
                g.add_edge(names, 'join'); g.add_edge('join', END)
            else:
                routes = dict(zip(p['cases'], names)); fallback = names[-1]
                def route(state):
                    value = resolve(p['select'], state)
                    if not isinstance(value, (str,int,float,bool,type(None))): raise ValueError('Branch result must be scalar')
                    return routes.get(str(value), fallback)
                g.add_conditional_edges(START, route, names)
                for name in names: g.add_edge(name, END)
        return g.compile()
    return build(plan)
