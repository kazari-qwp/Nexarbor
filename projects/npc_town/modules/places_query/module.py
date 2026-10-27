"""按需读取处境与地图，显式发布自己的公开人物资料。"""

from copy import deepcopy
import json
from pathlib import Path

from app.runtime.requester import requester_id
from app.transactions.locks import require_transaction_node
from domain.core import CallableTool, Module, access
from .scene import Roads, scene, inspect_place, map_graph
from .map_image import render_map

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))


class PlacesQueryModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__('places.query', **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'],getattr(self,spec['operation']),spec['description'],deepcopy(spec['parameters'])))

    async def publish(self):return next(iter((await self._execute('publish')).values()))
    async def look(self):return next(iter((await self._execute('look')).values()))
    async def place(self, place=None):return next(iter((await self._execute('place',place)).values()))
    async def map(self):return next(iter((await self._execute('map')).values()))

    @access(channels=())
    async def _execute(self, node, operation, place=None):
        if (requester_id.get() or node.info.node_id) != node.info.node_id:raise PermissionError('只能查询自己的处境')
        if operation == 'publish':
            require_transaction_node(node.info.node_id)
            values = (await node.modules.get('records.store').read()).get('values',{})
            self.published = {key:deepcopy(values[key]) for key in self.config.get('public_fields',('name','gender','profession','age_group')) if key in values}
            return deepcopy(self.published)
        views = await Roads(self).collect()
        if operation == 'look':return await scene(self,node,views)
        if operation == 'place':return await inspect_place(self,node,place,views)
        graph = await map_graph(self,node,views)
        if not graph['places']:raise ValueError('当前授权范围内没有可绘制的地点')
        image = render_map(graph,self.config)
        labels = '；'.join(item['name']+'='+item['id'] for item in graph['places'])
        return {'format':'nexarbor-tool-content/v1','content':[
            {'type':'text','text':'地点道路图。线段为道路，箭头为单向通行；示意位置不代表距离。地点编号：'+labels},
            {'type':'image','name':'地点道路图.png','mediaType':'image/png','data':image}]}
