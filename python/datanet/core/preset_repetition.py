"""One framework preset parameter: repeat a declared unit around shared nodes.

Only materializes an independent JSON snapshot. It neither mounts modules nor
starts Agents. Final placement allocates fresh IDs and storage as usual.
"""
from copy import deepcopy
from math import ceil,sqrt
from .component_registry import codecs

REPEAT_FIELDS=('repeat_unit_count','repeat_unit')

def validate_repetition(value):
    count=value.get('repeat_unit_count')
    if count is None:return None
    if type(count) is not int or not 1<=count<=100:raise ValueError('可重复单元数量必须是 1 至 100 的整数')
    ids=value.get('repeat_unit')
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or not i for i in ids) or len(ids)!=len(set(ids)):raise ValueError('预设必须声明唯一的可重复单元节点')
    known={n['node_id'] for n in value['nodes']}
    if not set(ids)<=known:raise ValueError('可重复单元引用不存在的节点')
    return count

def _references(value,schema,ids):
    if schema.get('format') in ('node-id','node-reference') and isinstance(value,str):return ids.get(value,value)
    if isinstance(value,list):return [_references(v,schema.get('items',{}),ids) for v in value]
    if isinstance(value,dict):return {k:_references(v,schema.get('properties',{}).get(k,schema.get('additionalProperties') if isinstance(schema.get('additionalProperties'),dict) else {}),ids) for k,v in value.items()}
    return value

def _documents(value,paths):
    if isinstance(value,list):return [_documents(v,paths) for v in value]
    if isinstance(value,dict):return {k:paths.get(v,v) if isinstance(v,str) and (k in ('file','path','document','directory') or k.endswith('_path')) else _documents(v,paths) for k,v in value.items()}
    return value

def expand_snapshot(snapshot,count=None,definitions=None):
    source=deepcopy(snapshot)
    if count is not None:source['repeat_unit_count']=count
    count=validate_repetition(source)
    if count is None:return source
    definitions=definitions or {};nodes=source['nodes'];files=source.get('files',{});unit=set(source['repeat_unit'])
    # 亚节点随所属重复单元一起复制，不能挂回原成员。
    while True:
        added={n['node_id'] for n in nodes if n['type']=='subnode' and n['parameters'].get('parent_id') in unit}-unit
        if not added:break
        unit.update(added)
    prototypes=[n for n in nodes if n['node_id'] in unit]
    if len(nodes)+(count-1)*len(unit)>10000:raise ValueError('展开后的预设超过 10000 个节点')
    used={n['node_id'] for n in nodes};maps=[{id:id for id in unit}]
    for index in range(1,count):
        ids={}
        for node in prototypes:
            base=node['node_id']+'~unit-'+str(index+1);candidate=base;suffix=1
            while candidate in used:candidate=base+'-'+str(suffix);suffix+=1
            ids[node['node_id']]=candidate;used.add(candidate)
        maps.append(ids)
    positions={n['node_id']:deepcopy(source.get('positions',{}).get(n['node_id'],{'x':(i%4)*180,'y':(i//4)*150})) for i,n in enumerate(nodes)};points=list(positions.values()) or [{'x':0,'y':0}];right=max(p['x'] for p in points)+180;top=min(p['y'] for p in points)
    unit_points=[positions.get(n['node_id'],{'x':0,'y':i*100}) for i,n in enumerate(prototypes)];left=min(p['x'] for p in unit_points);up=min(p['y'] for p in unit_points);width=max(p['x'] for p in unit_points)-left+180;height=max(p['y'] for p in unit_points)-up+150;columns=ceil(sqrt(max(1,count-1)))
    output=deepcopy(nodes);output_files=deepcopy(files)
    for node in output:
        if node['node_id'] in unit:continue
        # 固定对象指向重复单元的真实边按单元展开；单值配置引用仍指向第一个。
        node['connections']['interfaces']=[{**deepcopy(edge),'target_node_id':ids.get(edge['target_node_id'],edge['target_node_id'])} for edge in node['connections']['interfaces'] for ids in (maps if edge['target_node_id'] in unit else [maps[0]])]
    for index,ids in enumerate(maps[1:],1):
        roots={}
        for node in prototypes:
            codec=codecs().get(node['type']);fields=(*codec.resources,*codec.resource_directories) if codec else ('file_path','directory','storage_path')
            for field in fields:
                root=node['parameters'].get(field)
                if isinstance(root,str):roots[root]=None
        prefix='repetitions/unit-'+str(index+1)+'/'
        while any(name.startswith(prefix) for name in output_files):prefix='repetitions/'+prefix
        paths={root:prefix+root.replace('\\','/').lstrip('/') for root in roots}
        for name,content in files.items():
            if any(name==root or name.startswith(root.rstrip('/')+'/') for root in roots):paths[name]=prefix+name;output_files[paths[name]]=deepcopy(content)
        for i,original in enumerate(prototypes):
            # Arbitrary value-node JSON must not be interpreted as resource paths.
            node=_documents({**deepcopy(original),'parameters':{}},paths);node['parameters']=deepcopy(original['parameters']) if original['type']=='value' else _documents(deepcopy(original['parameters']),paths)
            node['node_id']=ids[original['node_id']];node['context_cursor']=None;node['inputs']=None
            parent=node.get('management_parent_id');node['management_parent_id']=ids.get(parent,parent)
            if node['type']=='subnode':node['parameters']['parent_id']=ids.get(node['parameters'].get('parent_id'),node['parameters'].get('parent_id'))
            codec=codecs().get(node['type'])
            for field,kind in (codec.references.items() if codec else []):
                if field in node['parameters']:
                    value=node['parameters'][field];node['parameters'][field]=[ids.get(v,v) for v in value] if kind=='many' else ids.get(value,value)
            binding=node.get('execution') or {}
            for ref in binding.get('prepare',[]):
                if 'node' in ref:ref['node']=ids.get(ref['node'],ref['node'])
            if 'tool_sources' in binding:binding['tool_sources']=[ids.get(v,v) for v in binding['tool_sources']]
            for name,mount in node.get('modules',{}).items():
                definition=definitions.get(name)
                if definition:
                    for field in ('config','state'):mount[field]=_references(mount[field],getattr(definition,field+'_schema'),ids)
            node['connections']['interfaces']=[{**e,'target_node_id':ids.get(e['target_node_id'],e['target_node_id'])} for e in node['connections']['interfaces']]
            output.append(node);p=unit_points[i];positions[node['node_id']]={'x':right+((index-1)%columns)*width+p['x']-left,'y':top+((index-1)//columns)*height+p['y']-up}
    result={**source,'nodes':output,'files':output_files,'positions':positions}
    result.pop('repeat_unit_count',None);result.pop('repeat_unit',None)
    if source.get('edges'):result['edges']=[{**deepcopy(edge),'target':ids.get(edge.get('target'),edge.get('target'))} if 'target' in edge else deepcopy(edge) for edge in source['edges'] for ids in (maps if edge.get('target') in unit else [maps[0]])]
    return result
