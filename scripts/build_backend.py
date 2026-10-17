from pathlib import Path
import json, subprocess, sys, shutil
root=Path(__file__).resolve().parents[1]
staging=root/'build/staging'
if staging.exists():
    if staging.resolve().parent != (root/'build').resolve():
        raise RuntimeError('Unexpected staging path')
    shutil.rmtree(staging)
staging.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'python',staging/'python',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for file in (root/'adapters/harness/backend').glob('*.py'):
    if not file.name.startswith('test_'):shutil.copy2(file,staging/file.name)
shutil.copytree(root/'executors/minimal/python',staging/'python',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
paths=[staging/'python',staging]
modules=[]
collect=set();metadata=set()
for file in sorted((root/'extensions').glob('*/*/*/component.json')):
    m=json.loads(file.read_text(encoding='utf-8'))
    collect.update(m.get('python',{}).get('collect',[]))
    metadata.update(m.get('python',{}).get('metadata',[]))
    for section,key in [('python','path')]:
        relative=m.get(section,{}).get(key)
        if relative:
            source=file.parent/relative
            shutil.copytree(source,staging/('python' if section=='python' else '.'),dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    modules.extend(m.get('python',{}).get('node_codecs',[]))
    modules.extend(m.get('python',{}).get('toolbox_installers',[]))
    modules.extend(m.get('python',{}).get('services',[]))
    if m.get('python',{}).get('runtime'):modules.append(m['python']['runtime'])
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','datanet-backend','--distpath',str(root/'build/dist'),'--workpath',str(root/'build/work'),'--specpath',str(root/'build')]
for path in paths:command+=['--paths',str(path)]
for module in modules:command+=['--hidden-import',module]
for package in sorted(collect):command+=['--collect-all',package]
for package in sorted(metadata):command+=['--copy-metadata',package]
command+=[str(staging/'server.py')]
subprocess.run(command,check=True)
