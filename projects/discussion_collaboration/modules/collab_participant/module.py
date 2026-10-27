"""成员入口在所在节点转交整合操作，保留原始请求者身份。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller, requester_id
from domain.core import CallableTool, Module, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))


class CollabParticipantModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__('collab.participant', **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:self.tools._add(CallableTool(spec['id'],getattr(self,spec['operation']),spec['description'],deepcopy(spec['parameters'])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id+'\0'+self.module_id).encode()).hexdigest()[:24]
        for tool,spec in zip(self.tools,TOOLS):
            tool.name = 'mod_'+sha256((source_id+'\0'+spec['id']).encode()).hexdigest()[:24]
            tool.description = node.info.node_id+' · '+spec['name']+' · '+spec['description']

    async def read(self):return next(iter((await self._operate('read',{})).values()))
    async def submit(self, **arguments):return next(iter((await self._operate('submit',arguments)).values()))
    async def approve(self, **arguments):return next(iter((await self._operate('approve',arguments)).values()))
    async def veto(self, **arguments):return next(iter((await self._operate('veto',arguments)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        integrator = node.modules.get(self.config['integrator_module'])
        actor = requester_id.get() or node.info.node_id
        arguments = dict(thaw(parameters))
        with as_caller(node.info.node_id):
            if operation == 'read':arguments = {'include_history':False}
            else:
                arguments['member'] = actor
                if operation in ('approve','veto') and not arguments.get('candidate_id'):
                    candidate = (await integrator.read(include_history=False)).get('candidate') or {}
                    if not candidate.get('id'):raise ValueError('当前没有待验收的候选')
                    arguments['candidate_id'] = candidate['id']
            data = thaw(await getattr(integrator,operation)(**arguments))
        if operation == 'read' and isinstance(data,dict):
            own = next((entry for entry in data.get('members',[]) if entry['id']==actor),None)
            data['self'] = {'id':actor,'branch':own.get('branch') if own else None,'is_member':own is not None}
        return data
