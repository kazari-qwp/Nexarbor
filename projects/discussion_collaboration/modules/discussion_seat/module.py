"""真实 Agent 的讨论席位；发布角色与显示名称，不运行模型。"""

from copy import deepcopy
from app.transactions.locks import require_transaction_node
from domain.core import Module, access

ROLES = ('leader', 'recorder', 'member')


class DiscussionSeatModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__('discussion.seat', **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}

    async def describe(self):
        return next(iter((await self._describe()).values()))

    @access(channels=())
    async def _describe(self, node):
        role = self.config.get('role', 'member')
        if role not in ROLES:raise ValueError('席位角色必须是 leader、recorder 或 member。')
        name = self.config.get('name', '')
        if not isinstance(name, str):raise ValueError('显示名称必须是字符串。')
        name = name.strip() or str(node.info.name or '').strip() or node.info.node_id
        require_transaction_node(node.info.node_id)
        self.published = {'role':role, 'name':name}
        return {'id':node.info.node_id, 'name':name, 'role':role}
