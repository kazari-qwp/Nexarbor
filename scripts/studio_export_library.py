"""Export unchanged verified module sources plus declarative component descriptors."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('studio',type=Path);p.add_argument('destination',type=Path);p.add_argument('--module',action='append',dest='modules',help='只导出指定模块，可重复');a=p.parse_args()
source=a.studio.resolve();destination=a.destination.resolve()
if not source.is_relative_to(ROOT/'build') or not destination.is_relative_to(ROOT/'extensions'):p.error('Expected a project build/studio and extensions destination')
library=json.loads((source/'library.json').read_text(encoding='utf-8'))
if a.modules:
    if set(a.modules)-set(library):p.error('Unknown module selection')
    library={name:release for name,release in library.items() if name in a.modules}
mapping={name:'capabilities/'+re.sub(r'[^a-z0-9_]','_',name) for name in library}
for release in library.values():
    if set(release['manifest']['requires'])-set(library):p.error('Include every required module in the export selection')
selection=[]
for name,release in library.items():
    key=mapping[name];target=destination/key;folder=source/release['folder'];target.mkdir(parents=True,exist_ok=True);hashes={}
    for file in folder.rglob('*'):
        relative=file.relative_to(folder)
        if not file.is_file() or file.suffix not in ['.py','.json','.md','.txt','.html','.css','.js'] or any(part in ['__pycache__','dependencies','reference'] for part in relative.parts) or relative.name in ['AGENTS.md','MODULE_GUIDE.md','FRONTEND_GUIDE.md','workspace.json']:continue
        output=target/relative;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,output);hashes[relative.as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
    descriptor=dict(id=key,kind='capabilities',version=release['version'],description=name+' (Agent-made)',requires=['capabilities/module_sdk']+[mapping[d] for d in release['manifest']['requires']],nodeModule='.')
    (target/'component.json').write_text(json.dumps(descriptor,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'provenance.json').write_text(json.dumps(dict(generator='DeepSeek Harness component maker',module=name,source_digest=release['digest'],files=hashes),ensure_ascii=False,indent=2),encoding='utf-8');selection.append(key)
(destination/'extension.json').write_text(json.dumps(dict(id=destination.name,version='0.4.0',sources=['../foundation'],select=selection),ensure_ascii=False,indent=2),encoding='utf-8')
print('Exported unchanged:',', '.join(library))
