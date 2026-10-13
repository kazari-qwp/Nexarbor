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
shutil.copytree(root/'adapters/harness/backend/harness_components',staging/'harness_components',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for file in (root/'adapters/harness/backend').glob('*.py'):
    if not file.name.startswith('test_'):shutil.copy2(file,staging/file.name)
paths=[staging/'python',staging]
modules=[]
for file in sorted((root/'components').glob('*/*/component.json')):
    m=json.loads(file.read_text(encoding='utf-8'))
    for section,key in [('python','path'),('harness','python_path')]:
        relative=m.get(section,{}).get(key)
        if relative:
            source=file.parent/relative
            shutil.copytree(source,staging/('python' if section=='python' else '.'),dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    modules.extend(m.get('python',{}).get('node_codecs',[]))
    modules.extend(m.get('python',{}).get('toolbox_installers',[]))
    modules.extend(m.get('harness',{}).get('services',[]))
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','datanet-backend','--distpath',str(root/'build/dist'),'--workpath',str(root/'build/work'),'--specpath',str(root/'build')]
for path in paths:command+=['--paths',str(path)]
for module in modules:command+=['--hidden-import',module]
command+=[str(staging/'server.py')]
subprocess.run(command,check=True)
