"""小镇应用的装配端口；模块实例统一使用当前宿主。"""

from copy import deepcopy
from pathlib import Path

from app.projects import Project

from app.network_saver import NetworkSaver
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


class TownProject(TownModules, Project):
    def __init__(self, directory, project=None):
        TownModules.__init__(self)
        Project.__init__(self, directory, project or Path(__file__).resolve().parent)
