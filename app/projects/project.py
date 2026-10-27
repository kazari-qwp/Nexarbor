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
    def __init__(self, directory, project):
        self.project = Path(project).resolve()
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
        self.configure_project()
        records = [self._json(ref['file']) for ref in self.manifest['nodes']]
        initial = dict(version=1,network={'nodes':records},files={name:self._path(name).read_text(encoding='utf-8') for name in self.manifest['files']},
                       agents={},node_properties=deepcopy(self.manifest['properties']),runtime=deepcopy(self.manifest['runtime']),signals=deepcopy(self.manifest['signals']))
        self.backend = Backend(directory,saver=self.saver,initial_document=initial)
        self.module_signals = None
        self.templates = TemplateService(self,self.backend.extension_state['runtime'].get('templates',[]))
        self.graph_changed()

    def configure_project(self):
        """在构建节点前登记项目自有的工具和资源工厂。"""

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
