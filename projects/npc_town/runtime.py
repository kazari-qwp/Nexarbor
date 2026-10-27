"""小镇应用的装配端口；模块实例统一使用当前宿主。"""

from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json
from jsonschema import Draft202012Validator

from app.templates import TemplateService

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.module_signals import ModuleSignals
from modules.context_assembler import ContextAssemblerModule
from modules.tool_discovery import ToolDiscoveryModule
from .modules.agents_activity import AgentsActivityModule
from .modules.agents_memory import AgentsMemoryModule
from .modules.agreements_pair import AgreementsPairModule
from .modules.clock_counter import ClockCounterModule
from .modules.family_birth import FamilyBirthModule
from .modules.family_household import FamilyHouseholdModule
from .modules.messages_box import MessagesBoxModule
from .modules.messages_relay import MessagesRelayModule
from .modules.movement_here import MovementHereModule
from .modules.periodic_checkpoint import PeriodicCheckpointModule
from .modules.place_info import PlaceInfoModule
from .modules.places_query import PlacesQueryModule
from .modules.records_store import RecordsStoreModule
from .modules.records_transfer import RecordsTransferModule
from .modules.service_actions import ServiceActionsModule
from .modules.shop_market import ShopMarketModule
from .modules.world_time import WorldTimeModule


class TownModules:
    def __init__(self):
        self.backend = None
        self.templates = None
        self.saver = NetworkSaver()
        self.factories = {
            'agents.activity':lambda config, **settings:AgentsActivityModule(self.execute_agent,config,**settings),
            'agents.memory':lambda config, **settings:AgentsMemoryModule(config,**settings),
            'agreements.pair':lambda config, **settings:AgreementsPairModule(self.transaction,config,**settings),
            'clock.counter':lambda config, **settings:ClockCounterModule(self.transaction,self.checkpoint,config,**settings),
            'context.assembler':lambda config, **settings:ContextAssemblerModule(config,**settings),
            'family.birth':lambda config, **settings:FamilyBirthModule(self.transaction,self.instantiate,config,**settings),
            'family.household':lambda config, **settings:FamilyHouseholdModule(self.transaction,config,**settings),
            'messages.box':lambda config, **settings:MessagesBoxModule(self.transaction,config,**settings),
            'messages.relay':lambda config, **settings:MessagesRelayModule(config,**settings),
            'movement.here':lambda config, **settings:MovementHereModule(self.transaction,config,**settings),
            'place.info':lambda config, **settings:PlaceInfoModule(config,**settings),
            'places.query':lambda config, **settings:PlacesQueryModule(config,**settings),
            'records.store':lambda config, **settings:RecordsStoreModule(config,**settings),
            'records.transfer':lambda config, **settings:RecordsTransferModule(self.transaction,config,**settings),
            'runtime.periodic_checkpoint':lambda config, **settings:PeriodicCheckpointModule(self.transaction,self.checkpoint,config,**settings),
            'service.actions':lambda config, **settings:ServiceActionsModule(self.transaction,config,**settings),
            'shop.market':lambda config, **settings:ShopMarketModule(self.transaction,config,**settings),
            'world.time':lambda config, **settings:WorldTimeModule(self.transaction,config,**settings),
        }
        self.saver.tables.module_types.update({name:self.restore_module for name in self.factories})

    def make(self, name, config, access_settings=None):
        access_settings = access_settings or {}
        settings = {key:access_settings[key] for key in ('channels','strength','channel_mode') if key in access_settings}
        if name == 'tools.collector':
            return ToolDiscoveryModule(config.get('channels',()),settings.get('strength',1),
                                       channel_mode=config.get('channel_modes',{}).get('channels','allow'))
        return self.factories[name](deepcopy(config),**settings)

    def restore_module(self, record):
        return self.make(record['module_id'],record.get('config',{}),record)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes,**options)

    async def checkpoint(self, **options):
        await self.backend.node_locks.wait_prepared()
        return self.backend.save(**options)

    async def execute_agent(self, actor, message='', **options):
        return await self.backend.execute_agent(actor,message,**options)

    async def instantiate(self, actor, **arguments):
        return await self.templates.instantiate(actor,**arguments)

    def bind_signals(self):
        self.module_signals = ModuleSignals(self.backend.signals)
        self.module_signals.refresh()


class TownProject(TownModules):
    def __init__(self, directory, project=None):
        super().__init__()
        self.project = Path(project).resolve() if project is not None else Path(__file__).resolve().parent
        self.metadata = self._json('nexarbor.json')
        entry = self.metadata['networks'][self.metadata['activeNetwork']]
        self.manifest = self._json(entry['file'])
        self.module_schemas = {}
        self.tool_specs = {}
        for name, resource in self.metadata['resources']['modules'].items():
            if resource.get('builtin'):
                folder = Path(__file__).resolve().parents[2]/'modules'/('tool_discovery' if name=='tool_discovery' else 'context_assembler')
                spec = json.loads((folder/'module.json').read_text(encoding='utf-8'))
            else:
                folder = (self.project/resource['folder']).resolve()
                spec = json.loads((folder/'module.json').read_text(encoding='utf-8'))
            self.module_schemas[name] = spec
            self.tool_specs[name] = spec.get('agent_tools',[])
        records = [self._json(ref['file']) for ref in self.manifest['nodes']]
        initial = dict(version=1,network={'nodes':records},files={name:self._path(name).read_text(encoding='utf-8') for name in self.manifest['files']},
                       agents={},node_properties=deepcopy(self.manifest['properties']),runtime=deepcopy(self.manifest['runtime']),signals=deepcopy(self.manifest['signals']))
        self.backend = Backend(directory,saver=self.saver,initial_document=initial)
        self.module_signals = None
        self.templates = TemplateService(self,self.backend.extension_state['runtime'].get('templates',[]))
        self.graph_changed()

    def _path(self, name):
        path = (self.project/name).resolve()
        if not path.is_relative_to(self.project):raise ValueError('Project resource escapes project directory')
        return path

    def _json(self, name):
        return json.loads(self._path(name).read_text(encoding='utf-8'))

    def validate_nodes(self, nodes):
        for node in nodes:
            for spec in node.get('tables',{}).get('modules',[]):
                definition = self.module_schemas[spec['module_id']]
                if node['type'] not in definition.get('node_types',[]):raise ValueError('模块不支持节点类型：'+spec['module_id'])
                for field in ('config','state'):
                    Draft202012Validator(definition.get(field+'_schema',{})).validate(spec.get(field,{}))

    def remap_factory_tools(self, node, old_id):
        def name(node_id,module_id,tool_id):
            source_id = sha256((node_id+'\0'+module_id).encode()).hexdigest()[:24]
            return 'mod_'+sha256((source_id+'\0'+tool_id).encode()).hexdigest()[:24]
        names = {}
        for module in node.get('tables',{}).get('modules',[]):
            module_id = module['module_id']
            for tool in self.tool_specs.get(module_id,[]):
                names[(module_id,name(old_id,module_id,tool['id']))] = name(node['node_id'],module_id,tool['id'])
        def update(value):
            if isinstance(value,list):
                for item in value:update(item)
            elif isinstance(value,dict):
                key = value.get('factory_module'),value.get('tool')
                if key in names:
                    value['tool'] = names[key]
                    if value.get('description','').startswith(old_id+' · '):value['description'] = node['node_id']+value['description'][len(old_id):]
                for item in value.values():update(item)
        update(node.get('tables',{}))

    @staticmethod
    def link_record(target, metadata):
        attributes = deepcopy(metadata.get('attributes',{}))
        return dict(target_id=target,channels=list(metadata.get('channels',())),threshold=metadata.get('threshold',0),
                    channel_mode=attributes.get('channel_mode','allow'),processor={'type':'multiplier','factor':metadata.get('multiplier',1)},attributes=attributes)

    def graph_changed(self):
        if self.module_signals is not None:self.module_signals.clear()
        self.bind_signals()
        if self.backend.graph_observer is not None:self.backend.graph_observer()

    def close(self):
        self.backend.close()
