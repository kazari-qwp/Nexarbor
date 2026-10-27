"""讨论协作项目的模块、宿主工具与信号装配。"""

from copy import deepcopy
import json
from pathlib import Path

from app.network_saver import NetworkSaver
from app.projects import Project
from app.projects.host_tools import HostTools
from app.runtime.module_emitter import emit_module_signal
from modules.context_assembler import ContextAssemblerModule
from modules.tool_discovery import ToolDiscoveryModule
from .modules.agents_activity import AgentsActivityModule
from .modules.cooperative_group import CooperativeGroupModule
from .modules.cooperative_member import CooperativeMemberModule
from .modules.app_coordinator import AppCoordinatorModule
from .modules.collab_board import CollabBoardModule
from .modules.collab_participant import CollabParticipantModule
from .modules.discussion_seat import DiscussionSeatModule
from .modules.discussion_session import DiscussionSessionModule
from .modules.git_integrator import GitIntegratorModule
from .modules.messages_box import MessagesBoxModule
from .modules.notes_text import NotesTextModule
from .modules.records_store import RecordsStoreModule


class DiscussionModules:
    def __init__(self, definitions, directory=None):
        self.directory = Path(directory or ".").resolve()
        self.backend = None
        self.official_port = None
        self.saver = NetworkSaver()
        self.factories = {
            "cooperation.group":lambda config, **settings:CooperativeGroupModule(self.directory, self.transaction, self.emit, self.write_documents, config, **settings),
            "cooperation.member":lambda config, **settings:CooperativeMemberModule(self.execute_agent, config, **settings),
            "agents.activity":lambda config, **settings:AgentsActivityModule(self.execute_agent, config, **settings),
            "app.coordinator.entry":lambda config, **settings:AppCoordinatorModule(self.emit, config, **settings),
            "collab.board.rev_9191e2380f.rev_96569f0263":lambda config, **settings:CollabBoardModule(self.transaction, self.emit, config, **settings),
            "collab.participant":lambda config, **settings:CollabParticipantModule(config, **settings),
            "context.assembler":lambda config, **settings:ContextAssemblerModule(config, **settings),
            "discussion.seat":lambda config, **settings:DiscussionSeatModule(config, **settings),
            "discussion.session.rev_697d80a33d":lambda config, **settings:DiscussionSessionModule(self.transaction, self.emit, config, **settings),
            "git.integrator.rev_2863bbe53e.rev_c376775a7e":lambda config, **settings:GitIntegratorModule(config, **settings),
            "messages.box":lambda config, **settings:MessagesBoxModule(self.transaction, config, **settings),
            "notes.text":lambda config, **settings:NotesTextModule(self.transaction, config, **settings),
            "records.store":lambda config, **settings:RecordsStoreModule(config, **settings),
        }
        self.saver.tables.module_types.update({name:self.restore_module for name in self.factories})
        self.host_tools = HostTools(self.saver.tables, lambda:self.backend, self.execute_official, definitions)

    def make(self, name, config, access_settings=None):
        access_settings = access_settings or {}
        settings = {key:access_settings[key] for key in ("channels", "strength", "channel_mode") if key in access_settings}
        if name in ("tools.collector", "tool_discovery"):
            return ToolDiscoveryModule(config.get("channels", ()), settings.get("strength", 1),
                                       channel_mode=config.get("channel_modes", {}).get("channels", "allow"))
        return self.factories[name](deepcopy(config), **settings)

    def restore_module(self, record):
        return self.make(record["module_id"], record.get("config", {}), record)

    def write_documents(self, files):
        self.backend.write_documents(files)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    def emit(self, node, **parameters):
        return emit_module_signal(self.backend.signals, node, **parameters)

    async def execute_agent(self, actor, message="", **options):
        return await self.backend.execute_agent(actor, message, **options)

    async def execute_official(self, actor, name, arguments):
        if self.official_port is None:
            raise RuntimeError("当前宿主没有接入官方工具执行端口")
        return await self.official_port(actor, name, arguments)


class DiscussionProject(DiscussionModules, Project):
    def __init__(self, directory, project=None):
        folder = Path(project).resolve() if project is not None else Path(__file__).resolve().parent
        definitions = json.loads((folder / "host_tools.json").read_text(encoding="utf-8"))
        DiscussionModules.__init__(self, definitions, directory)
        Project.__init__(self, directory, folder)

    def configure_project(self):
        self.host_tools.register(self.manifest["properties"])
