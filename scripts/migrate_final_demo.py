"""一次性迁移原两节点应用及原预设；运行时不读取旧核心。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.runtime.backend import Backend
from app.network_saver import NetworkSaver
from app.projects.host_tools import HostTools
from app.studio.service import Studio
from domain.core import Network
from modules.tool_discovery import ToolDiscoveryModule
from scripts.migrate_town_project import convert_nodes,files_from,read,write_json

NAMES={'context.network':'context.assembler','tools.collector':'tool_discovery'}
FOLDERS={'context.assembler':ROOT/'modules/context_assembler','tool_discovery':ROOT/'modules/tool_discovery',**{name:ROOT/'projects/discussion_collaboration/modules'/folder for name,folder in [('collaboration.group','collaboration_group'),('collaboration.member','collaboration_member'),('discussion.group','discussion_group'),('discussion.member','discussion_member'),('git.workspace','git_workspace'),('execution.logs','execution_logs'),('groups.control','groups_control'),('network.administrator','network_administrator')]}}

def reference_names(value):
    if isinstance(value,list):return [reference_names(item) for item in value]
    if isinstance(value,dict):return {key:NAMES.get(item,item) if key=='module' and isinstance(item,str) else reference_names(item) for key,item in value.items()}
    return value

class Converter:
    def __init__(self,backend):self.backend=backend;self.saver=self;self.factory=backend.studio.modules
    def document(self,network,base):
        from app.projects.module_tools import bind_tools
        for node in network:
            for module in node.modules:
                if hasattr(module,"_tool_specs"):bind_tools(module,node,module._tool_specs)
        return self.backend.saver.document(network,base)

    def make(self,name,config,access_settings):
        settings={key:access_settings[key] for key in ('channels','strength','channel_mode') if key in access_settings}
        if name=='tools.collector':return ToolDiscoveryModule(config.get('channels',()),settings.get('strength',1),channel_mode=config.get('channel_modes',{}).get('channels','allow'))
        return self.factory.restore(NAMES.get(name,name),dict(config=reference_names(config),**settings))

def converted(raw,files,target,converter,manifests,host_tools):
    files={name:content.replace("E:\\DataNet-模块化成品\\build\\node-objects-20261021\\app1\\project\\workspace\\task","workspace/task") if isinstance(content,str) else content for name,content in files.items()}
    nodes=deepcopy(raw)
    for node in nodes:
        if node['type']=='subnode' or node.get('toolboxes') or node.get('expose'):raise ValueError('最终应用出现未迁移的旧节点结构')
        binding=node.get('execution') or {};sources=binding.get('tool_sources',[])
        if any(source!=node['node_id'] for source in sources) and 'tools.collector' not in node['modules']:
            node['modules']['tools.collector']=dict(config={'channels':binding.get('channels',[])},state={},access={'channels':binding.get('channels',[]),'strength':binding.get('strength',1)})
    for name,content in files.items():
        file=(target/name).resolve()
        if not file.is_relative_to(target):raise ValueError('原项目资源越界')
        file.parent.mkdir(parents=True,exist_ok=True)
        if not isinstance(content,str):raise ValueError('最终应用的初始资源须为真实UTF-8文件')
        file.write_text(content,encoding='utf-8')
    records,properties=convert_nodes(nodes,target,converter,manifests);host_tools.register(properties)
    for raw,node in zip(nodes,records):
        for offer in raw.get('offered_tools',[]):
            tool=host_tools.make(node['node_id'],offer['ref']);node['tables']['tools']['members'].append(dict(tool=tool.name,description=tool.description,parameters=tool.parameters,modules=[],host_ref=offer['ref']))
        if node.get('execution') is not None:
            node['execution']=reference_names(node['execution']);node['execution'].pop('tool_sources',None)
    return dict(network=dict(nodes=records,properties=properties),files=deepcopy(files))

def migrate(source,target,definitions):
    source=Path(source).resolve();target=Path(target).resolve()
    if (target/'nexarbor.json').exists():raise FileExistsError('拒绝覆盖已有演示项目：'+str(target))
    target.mkdir(parents=True,exist_ok=True);metadata=read(source,'nexarbor.json');manifest=read(source,metadata['networks'][metadata['activeNetwork']]['file'])
    old_manifests={name:read(source,entry['folder']+'/module.json') for name,entry in metadata['resources']['modules'].items()}
    old_manifests.setdefault('tools.collector',read(ROOT,'modules/tool_discovery/module.json'))
    resources={}
    for name in {NAMES.get(name,name) for name in old_manifests}:
        folder=FOLDERS[name];relative='modules/'+folder.name
        shutil.copytree(folder,target/relative,ignore=shutil.ignore_patterns('__pycache__','*.pyc'));resources[name]={'folder':relative}
    saver=NetworkSaver();holder={};host_tools=HostTools(saver.tables,lambda:holder['backend'],None,definitions)
    with TemporaryDirectory(prefix='final-demo-convert-',dir=ROOT/'build') as temp:
        def configure(backend):Studio(backend,{name:target/entry['folder'] for name,entry in resources.items()},project_directory=target)
        backend=Backend(temp,saver=saver,network=Network(),configure=configure);holder['backend']=backend
        try:
            converter=Converter(backend);document=converted([read(source,entry['file']) for entry in manifest['nodes']],files_from(source,manifest),target,converter,old_manifests,host_tools)
            node_files=[]
            for node in document['network']['nodes']:
                relative='nodes/'+sha256(node['node_id'].encode()).hexdigest()[:24]+'.json';write_json(target/relative,node);node_files.append({'file':relative})
            write_json(target/'networks/main.json',dict(format='nexarbor-project-network/v2',nodes=node_files,files=list(document['files']),agents={},signals={},properties=document['network']['properties'],runtime={'templates':[]},layout=deepcopy(manifest.get('layout',{})),view=deepcopy(manifest.get('view',{}))))
            for name,entry in metadata['resources'].get('presets',{}).items():
                original=read(source,entry['file']);stage=Path(temp)/Path(entry['file']).stem;stage.mkdir()
                preset=converted(original['network']['nodes'],original.get('files',{}),stage,converter,old_manifests,host_tools)
                preset['network'].update({key:deepcopy(value) for key,value in original['network'].items() if key in ('repeat_unit','repeat_unit_count')})
                write_json(target/entry['file'],preset)
                editor=source/entry['file'].replace('.json','.editor.json')
                if editor.exists():shutil.copyfile(editor,target/entry['file'].replace('.json','.editor.json'))
        finally:backend.close()
    if (source/'workspace/task').exists():shutil.copytree(source/'workspace/task',target/'workspace/task')
    tool_resources=deepcopy(metadata['resources'].get('tools',{}))
    for entry in tool_resources.values():
        file=source/entry['file'];destination=target/entry['file'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,destination)
    write_json(target/'host_tools.json',definitions)
    write_json(target/'nexarbor.json',dict(format='nexarbor-project/v2',name=metadata['name'],activeNetwork='main',networks={'main':{'name':metadata['networks']['main']['name'],'file':'networks/main.json'}},resources=dict(modules=resources,tools=tool_resources,presets=deepcopy(metadata['resources'].get('presets',{})),skills={})))
    return dict(nodes=len(node_files),presets=len(metadata['resources'].get('presets',{})),modules=len(resources))

if __name__=='__main__':
    installs=json.loads((ROOT/'build/official-installations-verification.json').read_text(encoding='utf-8'));configured=next(item for item in installs if item['installation']=='configured');definitions=json.loads((Path(configured['directory'])/'catalog.json').read_text(encoding='utf-8'))
    print(json.dumps(migrate('E:/DataNet-模块化成品/项目演示/应用1-讨论协作-初始',ROOT/'项目演示/应用1-讨论协作-初始',definitions),ensure_ascii=False))
