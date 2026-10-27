"""在隔离的真实候选图上执行制作 Agent 的行为测试。"""
from copy import deepcopy
import json
from importlib import import_module
import os
from pathlib import Path
from app.projects.project import Project
from app.projects.host_tools import host_tool_name
from app.templates.service import TemplateService,DEFINITION
from .testing import ModuleHarness

class NetworkHarness(ModuleHarness):
    validate_nodes=Project.validate_nodes
    remap_factory_tools=Project.remap_factory_tools
    link_record=staticmethod(Project.link_record)

    def __init__(self,fixture=None,*,network_file=None,_persistent=False):
        source=Path(fixture or os.environ['NEXARBOR_TEST_ENVIRONMENT']).resolve()
        setup=json.loads((source/'setup.json').read_text(encoding='utf-8'))
        if network_file is not None:
            source=Path(setup['views'][network_file]).resolve()
            setup=json.loads((source/'setup.json').read_text(encoding='utf-8'))
        library={key:(source/value).resolve() for key,value in setup['modules'].items()}
        document=json.loads((source/'initial.json').read_text(encoding='utf-8'))
        runtime=source/'runtime' if _persistent else None
        store=None
        if runtime is not None:
            from app.persistence.checkpoints import Checkpoints
            runtime.mkdir(parents=True,exist_ok=True)
            store=Checkpoints(runtime)
            document=store.latest() or document
        def configure(saver):
            for label in ('node_types','agent_node_types'):
                for kind,reference in setup.get(label,{}).items():
                    module,name=reference.split(':',1);getattr(saver,label)[kind]=getattr(import_module(module),name)
            self.port_contracts=deepcopy(setup.get('port_contracts',{}))
            self.definitions=deepcopy(setup.get('port_definitions',{}))
            self.definitions['templates:instantiate']=DEFINITION
            for node,metadata in document.get('node_properties',{}).items():
                for offer in metadata.get('offered_ports',[]):
                    ref=offer['ref'];name=host_tool_name(node,ref)
                    saver.tables.tool_types[name]=lambda current,record,ref=ref:self.make_port(current.info.node_id,ref)
        super().__init__(None,library=library,_runtime_directory=runtime,_initial_document={'version':1,'agents':{},**document},_configure_saver=configure,_store=store)
        self.module_schemas=self.modules.manifests
        self.tool_specs={key:item.get('agent_tools',[]) for key,item in self.module_schemas.items()}
        try:self._configure_templates()
        except BaseException:
            self.backend.close()
            if self.temporary is not None:self.temporary.cleanup()
            raise

    def _port(self,node,ref):return self.make_port(node,ref)

    def _configure_templates(self):
        self.templates=TemplateService(self,self.backend.extension_state.get('runtime',{}).get('templates',[]))
        self.modules.instantiate=self.templates.instantiate
        async def execute(actor,name,arguments):return await self.templates.instantiate(actor,**arguments)
        self.register_tools('templates',[DEFINITION],execute)
        self.register_readonly_ports()

    def _read_text(self,path,roots=()):
        for value in [path,*roots]:
            if not (self.folder/value).resolve().is_relative_to(self.folder):raise PermissionError('测试副本不能读取外部文件')
        return super()._read_text(path,roots)

    def graph_changed(self):
        self.signals.refresh()
        if self.backend.graph_observer is not None:self.backend.graph_observer()

    async def call(self,actor,node,module,operation,parameters=None,*,strength=2,channels=()):
        return await super().call(node,operation,parameters,actor=actor,module=module,strength=strength,channels=channels)

    async def restart(self):
        await super().restart()
        self._configure_templates()
