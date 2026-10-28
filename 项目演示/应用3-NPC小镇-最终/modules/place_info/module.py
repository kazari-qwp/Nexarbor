"""节点自己的位置资料与访问者记录。"""

from copy import deepcopy

from app.runtime.requester import caller_id, requester_id
from app.transactions.locks import require_transaction_node
from domain.core import Module, access


class PlaceInfoModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__('place.info', **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}

    def _information(self, node):
        if self.config.get('visitors_from_edges', False):
            if node.node_type == 'agent':
                raise PermissionError('visitors_from_edges 只适用于普通地点节点，不能用于 Agent，避免把 Agent 自己的目的地误当成访客')
            visitors = sorted({edge.target_id for edge in node.links
                if getattr(edge, 'attributes', {}).get('relation') == 'location'
                and {'location', 'movement', 'road'}.intersection(edge.channels)})
        else:
            visitors = list(self.state.get('visitors', self.config.get('visitors', ())))
        return dict(node_id=node.info.node_id, name=node.info.name,
                    description=self.config.get('description') or node.info.description,
                    location=self.state.get('location', self.config.get('location')),
                    visit=self.state.get('visit', 0), visitors=visitors)

    async def read(self):
        return next(iter((await self._read()).values()))

    @access(channels=())
    async def _read(self, node):
        return self._information(node)

    async def arrive(self, visitor):
        return next(iter((await self._visitors(visitor, True)).values()))

    async def leave(self, visitor):
        return next(iter((await self._visitors(visitor, False)).values()))

    @access(channels=())
    async def _visitors(self, node, visitor, arriving):
        if visitor != (requester_id.get() or node.info.node_id):
            raise PermissionError('只能修改请求发起者自己的访客记录')
        require_transaction_node(node.info.node_id)
        visitors = set(self._information(node)['visitors'])
        visitors.add(visitor) if arriving else visitors.discard(visitor)
        self.state['visitors'] = sorted(visitors)
        self.published = self._information(node)
        return deepcopy(self.published)

    async def set_location(self, location, description):
        return next(iter((await self._set_location(location, description)).values()))

    @access(channels=())
    async def _set_location(self, node, location, description):
        value = self._information(node)
        if node.node_type != 'agent' or node.info.node_id != (requester_id.get() or node.info.node_id) or caller_id.get() != location:
            raise PermissionError('只有实际发起移动的 Agent 可以更新自己的位置')
        require_transaction_node(node.info.node_id)
        if value['location'] != location:self.state['visit'] = value['visit'] + 1
        self.state['location'] = location
        node.inputs.update('module:place.info', {'tail':['当前位置：' + location + '\n' + description]})
        self.published = self._information(node)
        return deepcopy(self.published)
