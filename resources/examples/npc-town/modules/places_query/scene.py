"""授权范围内的地点快照与场景查询；不读取他人私人记录。"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict

from domain.core import access


class Roads:
    def __init__(self, module):
        self._access_origin = module._access_origin
        self.channels = module.config.get('road_channels', ['location', 'road'])
        self.strength = module.strength
        self.channel_mode = module.config.get('channel_modes', {}).get('road_channels', 'allow')

    @access()
    async def collect(self, node):
        metadata = dict(asdict(node.info), node_type=node.node_type,
                        extensions={module.module_id:deepcopy(module.published) for module in node.modules if hasattr(module,'published')})
        return dict(metadata=metadata, edges=tuple(node.links), place=node.modules.get('place.info'))


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def place_ref(key, metadata):
    return {'id': key, 'name': metadata.get('name') or key}


def public_profile(metadata, config):
    fields = config.get('public_fields', ('name', 'gender', 'profession', 'age_group'))
    profile = metadata.get('extensions', {}).get('places.query', {})
    return {key: plain(profile[key]) for key in fields if key in profile}



async def exits(module, location, nodes, views):
    if not location or location not in nodes:return []
    found = {}
    channels = module.config.get('road_channels', ['location','road'])
    for edge in views[location]['edges']:
        target = edge.target_id
        if target not in nodes or target == location or nodes[target].get('node_type') == 'agent':continue
        if not set(channels).intersection(edge.channels) or getattr(edge,'attributes',{}).get('relation') not in (None,'road'):continue
        found[target] = place_ref(target,nodes[target])
    return sorted(found.values(),key=lambda item:(item['name'],item['id']))


async def place_details(module, target, nodes, views):
    if target not in nodes or nodes[target].get('node_type') == 'agent':raise ValueError('该地点不在当前授权的地图范围内')
    value = await views[target]['place'].read()
    return {**place_ref(target,nodes[target]), 'description':value.get('description') or nodes[target].get('description',''),
            'exits':await exits(module,target,nodes,views)}


async def scene(module,node,views):
    records = await node.modules.get('records.store').read()
    own_place = await node.modules.get('place.info').read()
    location = own_place.get('location')
    nodes = {key:value['metadata'] for key,value in views.items()}
    people = []
    if location and location in nodes:
        place = await views[location]['place'].read()
        for key in sorted(set(place.get('visitors',()))):
            if key == node.info.node_id or key not in nodes or nodes[key].get('node_type') != 'agent':continue
            profile = public_profile(nodes[key],module.config)
            people.append({'id':key,'name':profile.get('name') or '姓名未公开','profile':profile})
    return {'location':place_ref(location,nodes.get(location,{})) if location else None,
            'records':records.get('values',{}),'people':people,'exits':await exits(module,location,nodes,views)}


async def inspect_place(module,node,query,views):
    nodes = {key:value['metadata'] for key,value in views.items()}
    if not query:query = (await node.modules.get('place.info').read()).get('location')
    if query not in nodes:
        found = [key for key,metadata in nodes.items() if metadata.get('node_type') != 'agent' and metadata.get('name') == query]
        if len(found)>1:raise ValueError('存在同名地点，请使用地点编号：'+'、'.join(found))
        if not found:raise ValueError('找不到该地点，或该地点不在授权范围内')
        query = found[0]
    return await place_details(module,query,nodes,views)


async def map_graph(module,node,views):
    nodes = {key:value['metadata'] for key,value in views.items() if key != node.info.node_id and value['metadata'].get('node_type') != 'agent'}
    if len(nodes)>80:raise ValueError('当前地图超过80个地点，请配置较小的模块访问范围')
    directed = set()
    channels = module.config.get('road_channels',['location','road'])
    for key in sorted(nodes):
        for edge in views[key]['edges']:
            target = edge.target_id
            if target in nodes and target != key and set(channels).intersection(edge.channels) and getattr(edge,'attributes',{}).get('relation') in (None,'road'):
                directed.add((key,target))
    roads = [];handled = set()
    for a,b in sorted(directed):
        pair = tuple(sorted((a,b)))
        if pair in handled:continue
        handled.add(pair)
        both = (b,a) in directed
        roads.append({'from':pair[0] if both else a,'to':pair[1] if both else b,'bidirectional':both})
    points = [{**place_ref(key,nodes[key]),'description':nodes[key].get('description','')} for key in sorted(nodes)]
    return {'places':points,'roads':roads}
