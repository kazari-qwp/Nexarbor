"""Check/copy the self-contained maintained town project shipped with Nexarbor."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'resources/examples/npc-town'
TEXT={'.py','.json','.md','.txt','.toml','.html','.css','.js','.mjs','.cjs','.svg'}
PRIVATE_NAMES={'制作记录.json','发布记录.json','test-output.txt'}
def serialized(value):
    return json.dumps(value,ensure_ascii=False,indent=2)+'\n'
def build_files():
    output={}
    for file in sorted(DESTINATION.rglob('*')):
        relative=file.relative_to(DESTINATION)
        if file.name in PRIVATE_NAMES or any(part.startswith('.') or part in ('tests','test','__pycache__','reference','dependencies','native-logs','maker-logs') for part in relative.parts): continue
        if file.is_file() and file.suffix in TEXT:
            if not file.resolve().is_relative_to(DESTINATION.resolve()): raise ValueError('Sample source escapes its project')
            output[relative.as_posix()]=file.read_text(encoding='utf-8')
    manifest=json.loads(output['nexarbor.json'])
    if manifest['format']!='nexarbor-project/v1': raise ValueError('Invalid sample project')
    declared=manifest['resources']['modules']
    for identity,item in declared.items():
        folder=item['folder'].rstrip('/')+'/'
        owned={name[len(folder):]:text for name,text in output.items() if name.startswith(folder)}
        spec=json.loads(owned['module.json'])
        if spec['id']!=identity: raise ValueError('Module ID mismatch: '+identity)
        missing=set(spec.get('requires',[]))-set(declared)
        if missing: raise ValueError('Sample missing dependencies: '+str(missing))
        item['version']=spec['version']
        item['digest']=sha256(json.dumps(owned,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    for item in manifest['networks'].values():
        network=json.loads(output[item['file']])
        for node in network['nodes']:
            spec=json.loads(output[node['file']])
            if set(spec.get('modules',{}))-set(declared): raise ValueError('Missing node modules: '+node['id'])
        for item in network.get('files',[]):
            if item['file'] not in output: raise ValueError('Missing text resource: '+item['file'])
    output['nexarbor.json']=serialized(manifest)
    return output
def bundle(destination=DESTINATION,*,check=False):
    destination=Path(destination)
    if destination.is_symlink() or not destination.resolve().is_relative_to(ROOT): raise ValueError('Example destination must stay inside repository')
    expected=build_files()
    mismatch=[]
    for name,text in expected.items():
        file=destination/name
        if check:
            if not file.is_file() or file.read_text(encoding='utf-8')!=text: mismatch.append(name)
        else:
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(text,encoding='utf-8',newline='\n')
    if mismatch: raise ValueError('Built-in town sample differs: '+str(mismatch))
    return len(expected)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    print(f'Town sample: {bundle(check=args.check)} files, {DESTINATION}')
