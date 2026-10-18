"""Composable persistence records. Outgoing links belong only to their source."""
from copy import deepcopy


def capture_records(document, node_ids, resource_files=None):
    selected = set(node_ids)
    entries = {entry['node_id']: entry for entry in document['network']['nodes']}
    if not selected <= entries.keys(): raise ValueError('Snapshot node is absent')
    resource_files = resource_files or {}
    return {node: deepcopy(dict(node=entries[node], agent=document.get('agents',{}).get(node),
        tools=document.get('tools',{}).get(node,{}), tool_names=document.get('tool_names',{}).get(node,[]),
        publications=document.get('node_publications',{}).get(node,{}),
        files={path: document['files'].get(path) for path in resource_files.get(node,())}))
        for node in sorted(selected)}


def merge_records(document, records):
    """Replace selected records; do not chase links or replace unrelated state."""
    result = deepcopy(document)
    positions = {entry['node_id']: index for index,entry in enumerate(result['network']['nodes'])}
    for node, record in records.items():
        if record['node']['node_id'] != node: raise ValueError('Node record identity mismatch')
        if node in positions: result['network']['nodes'][positions[node]] = deepcopy(record['node'])
        else: result['network']['nodes'].append(deepcopy(record['node']))
        agents=result.setdefault('agents',{})
        if record['agent'] is None: agents.pop(node,None)
        else: agents[node]=deepcopy(record['agent'])
        result.setdefault('tools',{})[node]=deepcopy(record['tools'])
        result.setdefault('tool_names',{})[node]=list(record['tool_names'])
        result.setdefault('node_publications',{})[node]=deepcopy(record['publications'])
        result.setdefault('files',{}).update(deepcopy(record['files']))
    return result
