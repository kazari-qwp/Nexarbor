"""新格式项目的配置、节点与资源装配；业务模块工厂由项目提供。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from app.runtime.backend import Backend
from app.runtime.module_signals import ModuleSignals
from app.templates import TemplateService


class Project:
    def __init__(self, directory, project, *, studio=False):
        self.project = Path(project).resolve()
        self.metadata = self._json('nexarbor.json')
        entry = self.metadata.get('networks',{}).get(self.metadata.get('activeNetwork'))
        self.manifest = self._json(entry['file']) if entry is not None else None
        self.module_schemas = {}
        self.module_folders = {}
        self.tool_specs = {}
        for name, resource in self.metadata['resources']['modules'].items():
            if resource.get('builtin'):
                folder = Path(__file__).resolve().parents[2]/'modules'/('tool_discovery' if name=='tool_discovery' else 'context_assembler')
                try:spec = json.loads((folder/'module.json').read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    self.module_folders[name] = folder
                    continue
            else:
                folder = (self.project/resource['folder']).resolve()
                try:spec = json.loads((folder/'module.json').read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    self.module_folders[name] = folder
                    continue
            self.module_schemas[name] = spec
            self.module_folders[name] = folder
            self.tool_specs[name] = spec.get('agent_tools',[])
        self.configure_project()
        records = [self._json(ref['file']) for ref in self.manifest['nodes']] if self.manifest is not None else []
        files={}
        for entry in self.manifest['files'] if self.manifest is not None else []:
            if isinstance(entry,str):files[entry]=self._path(entry).read_text(encoding='utf-8')
            elif entry.get('encoding')=='utf8':files[entry['name']]=self._path(entry['file']).read_text(encoding='utf-8')
            else:files[entry['name']]=self._json(entry['file'])['value']
        initial = dict(version=1,network={'nodes':records},files=files,
                       agents=deepcopy(self.manifest.get('agents',{})),node_properties=deepcopy(self.manifest.get('properties',{})),runtime=deepcopy(self.manifest.get('runtime',{})),signals=deepcopy(self.manifest.get('signals',{})),port_definitions=deepcopy(self.manifest.get('port_definitions',{})),port_contracts=deepcopy(self.manifest.get('port_contracts',{}))) if self.manifest is not None else None
        def configure(backend):
            from app.studio.service import Studio
            async def instantiate(actor,**parameters):return await self.templates.instantiate(actor,**parameters)
            if hasattr(self,'host_tools'):
                backend.restore_extra=self.restore_metadata
            service=Studio(backend,self.module_folders,project_directory=self.project,agent_run=backend.execute_agent,instantiate=instantiate,
                           ports=getattr(getattr(self,'host_tools',None),'definitions',{}),catalog_changed=self.sync_modules,register_properties=self.register_properties)
            service.graph_changed=self.graph_changed
            if initial is not None and any('tools' not in record.get('tables',{}) or any('tools' not in item for item in record.get('tables',{}).get('modules',[])) for record in records) and backend.store.latest() is None:
                from app.studio.assembly import assemble_document
                document=assemble_document(dict(network={**initial['network'],'properties':initial['node_properties']},files=initial['files']),backend,service.library,port_definitions=service.ports,allow_missing=True)
                initial['network']=document['network'];initial['files']=document['files']
        self.backend = Backend(directory,saver=self.saver,initial_document=initial,configure=configure if studio else None)
        self.module_signals = None
        self.templates = TemplateService(self,self.backend.extension_state.get('runtime',{}).get('templates',[]))
        self.graph_changed()

    def configure_project(self):
        """在构建节点前登记项目自有的工具和资源工厂。"""

    def sync_modules(self,releases):
        self.module_schemas.clear();self.tool_specs.clear()
        for name,release in releases.items():
            self.module_schemas[name]=release['manifest'];self.tool_specs[name]=release['manifest'].get('agent_tools',[])

    def restore_metadata(self,backend,document):
        self.host_tools.definitions.update(document.get('port_definitions',{}))
        if hasattr(backend,'studio'):backend.studio.port_contracts.update(document.get('port_contracts',{}))
        self.register_properties(document.get('node_properties',{}))

    def register_properties(self,properties):
        if hasattr(self,'host_tools'):self.host_tools.register(properties)

    def bind_signals(self):
        self.module_signals = ModuleSignals(self.backend.signals)
        self.module_signals.refresh()

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

    def remap_factory_tools(self, node, old_id, properties=None):
        def name(node_id,module_id,tool_id):
            source_id = sha256((node_id+'\0'+module_id).encode()).hexdigest()[:24]
            return 'mod_'+sha256((source_id+'\0'+tool_id).encode()).hexdigest()[:24]
        names = {}
        for module in node.get('tables',{}).get('modules',[]):
            module_id = module['module_id']
            for tool in self.tool_specs.get(module_id,[]):
                names[(module_id,name(old_id,module_id,tool['id']))] = name(node['node_id'],module_id,tool['id'])
        from app.projects.host_tools import host_tool_name
        host_names={host_tool_name(old_id,item['ref']):host_tool_name(node['node_id'],item['ref']) for item in (properties or {}).get('offered_ports',[])}
        def update(value):
            if not isinstance(value,dict):return
            tool=value.get('tool')
            if isinstance(tool,str):
                key=value.get('factory_module'),tool
                if key in names:value['tool']=names[key]
                elif tool in host_names:value['tool']=host_names[tool]
                if value.get('description','').startswith(old_id+' · '):value['description']=node['node_id']+value['description'][len(old_id):]
            for item in value.get('members',[]):update(item)
        tables=node.get('tables',{});update(tables.get('tools'))
        for module in tables.get('modules',[]):update(module.get('tools'))

    @staticmethod
    def link_record(target, metadata):
        attributes = deepcopy(metadata.get('attributes',{}))
        return dict(target_id=target,channels=list(metadata.get('channels',())),threshold=metadata.get('threshold',0),
                    channel_mode=attributes.get('channel_mode','allow'),processor={'type':'multiplier','factor':metadata.get('multiplier',1)},attributes=attributes)

    def graph_changed(self):
        if hasattr(self,'host_tools'):self.host_tools.ensure(self.backend.network,self.backend.extension_state.get('node_properties',{}))
        if self.module_signals is not None:self.module_signals.clear()
        self.bind_signals()
        if self.backend.graph_observer is not None:self.backend.graph_observer()

    def close(self):
        self.backend.close()
