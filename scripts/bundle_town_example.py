"""Check the maintained v2 town sample without rewriting its manifests."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'resources/examples/npc-town'

def read(folder,name):
    file=(folder/name).resolve()
    if not file.is_relative_to(folder.resolve()) or not file.is_file():raise ValueError('Missing or external sample resource: '+name)
    return json.loads(file.read_text(encoding='utf-8'))

def bundle(destination=DESTINATION,*,check=True):
    folder=Path(destination).resolve()
    if not folder.is_relative_to(ROOT):raise ValueError('Sample must stay in the target project')
    project=read(folder,'nexarbor.json')
    if project['format']!='nexarbor-project/v2':raise ValueError('Sample must use project/v2')
    declared=project['resources']['modules']
    for identity,item in declared.items():
        if item.get('builtin'):continue
        spec=read(folder,item['folder']+'/module.json')
        if spec['id']!=identity or spec['format']!='nexarbor-module/v4':raise ValueError('Invalid sample module: '+identity)
        if set(spec.get('requires',[]))-set(declared):raise ValueError('Sample library dependency missing: '+identity)
    for item in project['networks'].values():
        network=read(folder,item['file']);nodes=[read(folder,n['file']) for n in network['nodes']];ids={n['node_id'] for n in nodes}
        if len(ids)!=len(nodes):raise ValueError('Duplicate sample node ID')
        for node in nodes:
            if any(m['module_id'] not in declared for m in node['tables']['modules']):raise ValueError('Unknown sample module')
            if any(link['target_id'] not in ids for link in node['links']):raise ValueError('Unknown sample target')
        for resource in network.get('files',[]):
            file=(folder/resource).resolve()
            if not file.is_relative_to(folder) or not file.is_file():raise ValueError('Missing sample file')
    return sum(1 for file in folder.rglob('*') if file.is_file() and '__pycache__' not in file.parts)

if __name__=='__main__':print('Town sample checked:',bundle())
