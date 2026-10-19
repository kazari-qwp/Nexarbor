"""只读场景查询：道路、同地人物与公开地点；不持有节点事务锁。"""
from collections.abc import Mapping


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


async def call(ctx, target, module, operation, arguments=None):
    result = await ctx.network.call(target, module, operation, arguments or {})
    if result.get('status') != 'ok':
        raise RuntimeError(result.get('error') or f'无法读取 {module}.{operation}')
    return plain(result.get('data') or {})


def identity(item):
    metadata = item.get('metadata') or {}
    path = item.get('path') or []
    return metadata.get('node_id') or item.get('id') or item.get('node_id') or (path[-1] if path else None)


async def visible_nodes(ctx):
    result = {}
    for item in await ctx.network.nodes(channels=['movement']):
        item = plain(item)
        key = identity(item)
        if key:
            result[key] = item.get('metadata') or {}
    return result


def place_ref(key, metadata):
    return {'id': key, 'name': metadata.get('name') or key}


def public_profile(metadata, config):
    fields = config.get('public_fields', ('name', 'gender', 'profession', 'age_group'))
    profile = metadata.get('extensions', {}).get('agents.context', {})
    return {key: plain(profile[key]) for key in fields if key in profile}


async def exits(ctx, location, nodes):
    if not location or location not in nodes:
        return []
    found = {}
    for edge in await ctx.network.edges(location, channels=['movement']):
        meta = edge.get('metadata') or {}
        target = edge.get('target_node_id')
        if target not in nodes or target == location or nodes[target].get('node_type') == 'agent':
            continue
        if 'movement' not in meta.get('channels', ()) or meta.get('attributes', {}).get('relation') not in (None, 'road'):
            continue
        found[target] = place_ref(target, nodes[target])
    return sorted(found.values(), key=lambda item: (item['name'], item['id']))


async def place_details(ctx, target, nodes):
    if target not in nodes or nodes[target].get('node_type') == 'agent':
        raise ValueError('该地点不在当前授权的地图范围内')
    value = await call(ctx, target, 'place.info', 'read')
    return {**place_ref(target, nodes[target]), 'description': value.get('description') or nodes[target].get('description', ''), 'exits': await exits(ctx, target, nodes)}


async def scene(ctx):
    records = await call(ctx, ctx.node_id, 'records.store', 'read')
    own_place = await call(ctx, ctx.node_id, 'place.info', 'read')
    location = own_place.get('location')
    nodes = await visible_nodes(ctx)
    people = []
    if location and location in nodes:
        # 只使用当前地点明确登记的访客；道路可达的远处人物不会混入同地人物。
        place = await call(ctx, location, 'place.info', 'read')
        for key in sorted(set(place.get('visitors', ()))):
            if key == ctx.node_id or key not in nodes or nodes[key].get('node_type') != 'agent':
                continue
            profile = public_profile(nodes[key], ctx.config)
            people.append({'id': key, 'name': profile.get('name') or '姓名未公开', 'profile': profile})
    clock = None
    if ctx.config.get('clock'):
        value = await call(ctx, ctx.config['clock'], 'clock.counter', 'read')
        clock = {key: value.get(key, default) for key, default in (('tick', 0), ('day', 1), ('slot', ''))}
    return {'clock': clock, 'location': place_ref(location, nodes.get(location, {})) if location else None,
            'records': records.get('values', {}), 'people': people, 'exits': await exits(ctx, location, nodes)}


async def inspect_place(ctx, query):
    nodes = await visible_nodes(ctx)
    if not query:
        query = (await call(ctx, ctx.node_id, 'place.info', 'read')).get('location')
    if query not in nodes:
        matches = [key for key, metadata in nodes.items() if metadata.get('node_type') != 'agent' and metadata.get('name') == query]
        if len(matches) > 1:
            raise ValueError('存在同名地点，请使用地点编号：' + '、'.join(matches))
        if not matches:
            raise ValueError('找不到该地点，或该地点不在授权范围内')
        query = matches[0]
    return await place_details(ctx, query, nodes)


async def map_graph(ctx):
    visible = await visible_nodes(ctx)
    # 地图只能呈现模块权限内的普通节点；不会读取其他角色的状态或记忆。
    nodes = {key: value for key, value in visible.items() if key != ctx.node_id and value.get('node_type') != 'agent'}
    if len(nodes) > 80:
        raise ValueError('当前地图超过80个地点，请配置较小的模块访问范围')
    directed = set()
    for key in sorted(nodes):
        for edge in await ctx.network.edges(key, channels=['movement']):
            meta = edge.get('metadata') or {}
            target = edge.get('target_node_id')
            if target in nodes and target != key and 'movement' in meta.get('channels', ()) and meta.get('attributes', {}).get('relation') in (None, 'road'):
                directed.add((key, target))
    roads = []
    handled = set()
    for a, b in sorted(directed):
        pair = tuple(sorted((a, b)))
        if pair in handled:
            continue
        handled.add(pair)
        both = (b, a) in directed
        roads.append({'from': pair[0] if both else a, 'to': pair[1] if both else b, 'bidirectional': both})
    points = [{**place_ref(key, nodes[key]), 'description': nodes[key].get('description', '')} for key in sorted(nodes)]
    return {'places': points, 'roads': roads}
