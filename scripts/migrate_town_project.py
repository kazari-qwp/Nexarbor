"""一次性转换原小镇成品数据；运行时只加载新的节点/模块/工具箱记录。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from domain.agent import AgentNode, MarkdownAgentNode
from domain.agent.inputs import AgentInputs
from domain.annotated_link import AnnotatedLink
from domain.core import AverageAggregation, MarkdownNode, MaxAggregation, MinAggregation, Multiplier, Network, Node, NodeInfo, SumAggregation
from domain.pulse_node import PulseNode
from projects.npc_town.runtime import TownModules

CLASSES = {
    'agents.activity':('agents_activity','AgentsActivityModule'), 'agents.memory':('agents_memory','AgentsMemoryModule'),
    'agreements.pair':('agreements_pair','AgreementsPairModule'), 'clock.counter':('clock_counter','ClockCounterModule'),
    'family.birth':('family_birth','FamilyBirthModule'), 'family.household':('family_household','FamilyHouseholdModule'),
    'messages.box':('messages_box','MessagesBoxModule'), 'messages.relay':('messages_relay','MessagesRelayModule'),
    'movement.here':('movement_here','MovementHereModule'), 'place.info':('place_info','PlaceInfoModule'),
    'places.query':('places_query','PlacesQueryModule'), 'records.store':('records_store','RecordsStoreModule'),
    'records.transfer':('records_transfer','RecordsTransferModule'), 'runtime.periodic_checkpoint':('periodic_checkpoint','PeriodicCheckpointModule'),
    'service.actions':('service_actions','ServiceActionsModule'), 'shop.market':('shop_market','ShopMarketModule'),
    'world.time':('world_time','WorldTimeModule'),
}
AGGREGATIONS = {'sum':SumAggregation,'max':MaxAggregation,'min':MinAggregation,'mean':AverageAggregation}
UNUSED_COMMUNICATION_NODES = {name+'通信' for name in ('小砾','林','小路','阿森','阿石','老铁','悦')}


def read(root,name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Source project path escapes project directory')
    return json.loads(path.read_text(encoding='utf-8'))


def files_from(root,manifest):
    result={}
    for item in manifest.get('files',[]):
        path=(root/item['file']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Project resource escapes project directory')
        result[item['name']]=path.read_text(encoding='utf-8') if item['encoding']=='utf8' else read(root,item['file'])['value']
    return result


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def referenced(value,identifier):
    if isinstance(value,dict):return any(referenced(item,identifier) for item in value.values())
    if isinstance(value,list):return any(referenced(item,identifier) for item in value)
    return value==identifier


def normalize_nodes(original):
    nodes=deepcopy(original);by={node['node_id']:node for node in nodes};moved=[];removed=[]
    for node in nodes:
        if node['type']!='subnode' or set(node.get('modules',{}))!={'tools.collector'}:continue
        parent=by[node['parameters']['parent_id']]
        if 'tools.collector' in parent['modules']:raise ValueError('Duplicate collector after co-location')
        parent['modules']['tools.collector']=node['modules'].pop('tools.collector')
        moved.append(dict(source=node['node_id'],target=parent['node_id']))
    for node in nodes:
        execution=node.get('execution')
        if execution:execution.pop('tool_sources',None)
    for node in nodes:
        if node['type']!='subnode' or node.get('modules'):continue
        if node['connections']['interfaces'] and node['node_id'] not in UNUSED_COMMUNICATION_NODES:continue
        if any(referenced(other,node['node_id']) for other in nodes if other is not node):continue
        removed.append(node['node_id'])
    return [node for node in nodes if node['node_id'] not in removed],moved,removed


def convert_nodes(nodes,base,modules,manifests):
    network=Network();properties={}
    for raw in nodes:
        info=NodeInfo(raw['node_id'],raw['name'],raw.get('description',''))
        kind=raw['type'];params=raw.get('parameters',{})
        if kind=='agent':node=MarkdownAgentNode(info,base/params['file_path']) if params.get('file_path') else AgentNode(info)
        elif kind=='text_file':node=MarkdownNode(info,base/params['file_path'])
        elif kind=='pulse':node=PulseNode(info,**params)
        elif kind in ('node','subnode'):node=Node(info)
        else:raise ValueError('Unmigrated town node type: '+kind)
        node.bias=raw.get('divergence',-1);node.aggregation=AGGREGATIONS[raw.get('aggregation','sum')]()
        if kind=='agent':node.inputs=AgentInputs(raw.get('inputs') or {})
        for edge in raw['connections']['interfaces']:
            data=edge['metadata'];attributes=deepcopy(data.get('attributes',{}))
            node.links.add(AnnotatedLink(edge['target_node_id'],data.get('channels',()),threshold=data.get('threshold',0),
                processor=Multiplier(data.get('multiplier',1)),channel_mode=attributes.get('channel_mode','allow'),attributes=attributes))
        instances={name:modules.make(name,mount.get('config',{}),mount.get('access',{})) for name,mount in raw.get('modules',{}).items()}
        for name,module in instances.items():
            mount=raw['modules'][name]
            if mount.get('state') or hasattr(module,'state'):module.state=deepcopy(mount.get('state',{}))
            module._dependencies=tuple(instances[dependency] for dependency in manifests[name].get('requires',[]))
        for module in instances.values():node.install(module)
        network.add(node)
        properties[node.info.node_id]={'management_parent_id':raw.get('management_parent_id'),
            'offered_ports':deepcopy(raw.get('offered_tools',[])),
            **({'parent_id':params.get('parent_id')} if kind=='subnode' else {})}
    records=modules.saver.document(network,base)['nodes']
    for raw,record in zip(nodes,records):
        if raw.get('execution') is not None:record['execution']=deepcopy(raw['execution'])
    return records,properties


def convert_template(template,modules,manifests):
    converted=deepcopy(template)
    raw_nodes,moved,removed=normalize_nodes(template['document']['network']['nodes'])
    # Isolated resources exist only while constructing the new serialized record.
    stage=Path(mkdtemp(prefix='town-template-convert-',dir=ROOT/'build'))
    for name,content in template['document']['files'].items():
        path=(stage/name).resolve()
        if not path.is_relative_to(stage):raise ValueError('Template resource escapes staging directory')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    records,properties=convert_nodes(raw_nodes,stage,modules,manifests)
    converted['document']={'network':{'nodes':records,'properties':properties},'files':deepcopy(template['document']['files'])}
    old_order=[node['node_id'] for node in template['document']['network']['nodes']]
    for binding in converted['bindings']:
        match=re.fullmatch(r'/network/nodes/(\d+)/(.*)',binding['path'])
        old_index,suffix=int(match[1]),match[2];node_id=old_order[old_index]
        index=next(i for i,node in enumerate(records) if node['node_id']==node_id)
        if suffix.startswith('modules/'):
            _,module_id,rest=suffix.split('/',2)
            canonical='tool_discovery' if module_id=='tools.collector' else module_id
            module_index=next(i for i,item in enumerate(records[index]['tables']['modules']) if item['module_id']==canonical)
            suffix=f'tables/modules/{module_index}/'+rest
        binding['path']=f'/network/nodes/{index}/'+suffix
    return converted


def migrate(source,target):
    source=Path(source).resolve();target=Path(target).resolve();modules=TownModules()
    project=read(source,'nexarbor.json');manifest=read(source,project['networks'][project['activeNetwork']]['file'])
    original=[read(source,entry['file']) for entry in manifest['nodes']]
    nodes,moved,removed=normalize_nodes(original)
    resources=files_from(source,manifest)
    for name,content in resources.items():
        path=(target/name).resolve()
        if not path.is_relative_to(target):raise ValueError('Resource escapes target project')
        if not isinstance(content,str):raise ValueError('Town initial resources must be text')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_text(encoding='utf-8')!=content:raise ValueError('Refusing to overwrite changed project resource: '+name)
        path.write_text(content,encoding='utf-8')
    manifests={name:read(source,entry['folder']+'/module.json') for name,entry in project['resources']['modules'].items()}
    records,properties=convert_nodes(nodes,target,modules,manifests)
    references=[]
    for record in records:
        file='nodes/'+sha256(record['node_id'].encode()).hexdigest()[:24]+'.json';write_json(target/file,record);references.append({'file':file})
    runtime=deepcopy(manifest.get('runtime',{}));runtime.pop('components',None)
    runtime['templates']=[convert_template(template,modules,manifests) for template in runtime.get('templates',[])]
    network={'format':'nexarbor-project-network/v2','nodes':references,'files':list(resources),
             'signals':deepcopy(manifest['network'].get('signals',{})),'properties':properties,'runtime':runtime,
             'layout':deepcopy(manifest.get('layout',{})),'view':deepcopy(manifest.get('view',{}))}
    write_json(target/'networks/main.json',network)
    module_resources={}
    for name,manifest in manifests.items():
        if name in ('context.assembler','tools.collector'):
            module_resources['tool_discovery' if name=='tools.collector' else name]={'builtin':True}
            continue
        folder,class_name=CLASSES[name]
        updated=deepcopy(manifest);updated.update(format='nexarbor-module/v4',entry='module.py:'+class_name)
        updated['node_types']=['markdown' if item=='text_file' else item for item in updated.get('node_types',[])]
        updated['requires']=['tool_discovery' if item=='tools.collector' else item for item in updated.get('requires',[])]
        write_json(target/'modules'/folder/'module.json',updated);module_resources[name]={'folder':'modules/'+folder}
    write_json(target/'nexarbor.json',{'format':'nexarbor-project/v2','name':project['name'],'activeNetwork':'main',
        'networks':{'main':{'name':project['name'],'file':'networks/main.json'}},'resources':{'modules':module_resources}})
    return dict(original_nodes=len(original),nodes=len(records),moved_collectors=moved,removed_unreferenced_empty_subnodes=removed,
                files=len(resources),templates=len(runtime['templates']))


if __name__=='__main__':
    source=sys.argv[1] if len(sys.argv)>1 else 'E:/DataNet-模块化成品/resources/examples/npc-town'
    target=sys.argv[2] if len(sys.argv)>2 else str(ROOT/'projects/npc_town')
    result=migrate(source,target);write_json(ROOT/'build/town-project-migration.json',result)
    print(json.dumps(result,ensure_ascii=False))
