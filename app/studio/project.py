"""工作台按项目清单加载新模块、数据类型和宿主工具；不载入旧核心。"""
import json
from pathlib import Path
from app.network_saver import NetworkSaver
from app.projects import Project
from app.projects.host_tools import HostTools
from projects.knowledge_archive.nodes.value import ValueNode
from projects.knowledge_archive.nodes.csv import CsvNode
from projects.knowledge_archive.nodes.sqlite import SqliteNode
from projects.knowledge_archive.nodes.collection import CollectionNode
from projects.knowledge_archive.nodes.vector.node import LlamaIndexNode

class WorkbenchProject(Project):
    def __init__(self,directory,project):
        self.official_port=None
        super().__init__(directory,project,studio=True)

    def configure_project(self):
        from app.runtime.ports import read_text
        self.saver=NetworkSaver(read_text=lambda path,roots=():read_text(self.project,dict(path=path,roots=roots)))
        self.saver.node_types.update(value=ValueNode,csv=CsvNode,sqlite=SqliteNode,knowledge_collection=CollectionNode,llamaindex=LlamaIndexNode)
        root=Path(__file__).resolve().parents[2]
        standards={'tool_discovery':root/'modules/tool_discovery','context.assembler':root/'modules/context_assembler',
                   'data.local':root/'projects/knowledge_archive/modules/data_local','data.knowledge':root/'projects/knowledge_archive/modules/data_knowledge'}
        for name,folder in standards.items():
            if name not in self.module_folders:
                self.module_folders[name]=folder;spec=json.loads((folder/'module.json').read_text(encoding='utf-8'))
                self.module_schemas[name]=spec;self.tool_specs[name]=spec.get('agent_tools',[])
        file=self.project/'host_tools.json';definitions=json.loads(file.read_text(encoding='utf-8')) if file.exists() else []
        self.host_tools=HostTools(self.saver.tables,lambda:self.backend,self.execute_official,definitions,instantiate=self.instantiate)
        self.register_properties(self.manifest.get('properties',{}) if self.manifest is not None else {})

    async def instantiate(self,actor,**arguments):return await self.templates.instantiate(actor,**arguments)

    async def execute_official(self,actor,name,arguments):
        if self.official_port is None:raise RuntimeError('此宿主尚未接通官方工具')
        return await self.official_port(actor,name,arguments)
