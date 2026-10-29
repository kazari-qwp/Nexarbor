"""Build the same portable Windows ZIP on the current domain/app/adapt/frontends layout."""
from __future__ import annotations
import argparse,hashlib,importlib.metadata as metadata,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
from packaging.requirements import Requirement
from bundle_town_example import bundle as check_town_example
ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
FOLDERS={'domain','app','adapt','modules','configs','docs','resources','projects','项目演示'}
TOP={'README.md','PROJECT_OVERVIEW.md','package.json','requirements-runtime.txt'}
PRIVATE={'.git','__pycache__','node_modules','native-logs','maker-logs','.venv','.venv-runtime','runs','models','desktop-profile'}

def command(args,**options):subprocess.run([str(value) for value in args],cwd=options.pop('cwd',ROOT),check=True,**options)
def filesystem_path(value):
    path=Path(value).resolve()
    return Path('\\\\?\\'+str(path)) if os.name=='nt' and not str(path).startswith('\\\\?\\') else path

def copy(source,target):
    source,target=filesystem_path(source),filesystem_path(target)
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)

def build_python(target):
    base=Path(sys.base_prefix);home=target/'runtime/python';home.mkdir(parents=True)
    for file in base.iterdir():
        if file.is_file() and (file.suffix.lower()=='.dll' or file.name in ('python.exe','pythonw.exe','LICENSE_PYTHON.txt')):copy(file,home/file.name)
    for folder in ('DLLs','Lib'):
        source=base/folder
        for current,folders,files in os.walk(source):
            folders[:]=[name for name in folders if name not in ('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo')]
            for name in files:
                file=Path(current)/name
                if file.suffix not in ('.pyc','.pyo','.pdb') and not name.startswith('_test'):copy(file,home/folder/file.relative_to(source))
    for name in ('libssl-3-x64.dll','libcrypto-3-x64.dll','sqlite3.dll','libbz2.dll','liblzma.dll','libffi-8.dll','ffi-7.dll','ffi-8.dll','ffi.dll','zlib.dll'):
        source=base/'Library/bin'/name
        if source.exists():copy(source,home/name)
    installed={};visited=set()
    def dependency(name,extras=()):
        distribution=metadata.distribution(name);identity=distribution.metadata['Name'].lower().replace('_','-')
        key=(identity,tuple(sorted(extras)))
        if key in visited:return
        visited.add(key)
        items=[] if identity in installed else distribution.files or []
        installed[identity]=distribution.version
        for item in items:
            relative=Path(str(item))
            if relative.is_absolute() or '..' in relative.parts or any(part in ('tests','test','__pycache__') for part in relative.parts) or relative.suffix in ('.pyc','.pyo'):continue
            source=Path(distribution.locate_file(item))
            if filesystem_path(source).is_file():copy(source,home/'Lib/site-packages'/relative)
        for definition in distribution.requires or []:
            requirement=Requirement(definition)
            if not requirement.marker or any(requirement.marker.evaluate({'extra':extra}) for extra in ('',*extras)):dependency(requirement.name,requirement.extras)
    for line in (ROOT/'requirements-runtime.txt').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            requirement=Requirement(line);dependency(requirement.name,requirement.extras)
    dependency('pip')
    (home/'runtime-packages.json').write_text(json.dumps(installed,indent=2)+'\n',encoding='utf-8')
    environment={key:value for key,value in os.environ.items() if key not in ('PYTHONHOME','PYTHONPATH')};system=Path(os.environ.get('SystemRoot','C:/Windows'));environment['PATH']=os.pathsep.join(map(str,[system/'System32',system,system/'System32/WindowsPowerShell/v1.0']))
    command([home/'python.exe','-B','-I','-X','utf8','-c','import ssl,sqlite3,bz2,lzma,ctypes,jsonschema,filelock,yaml,pandas,numpy,PIL,fsspec,requests,llama_index.core,packaging; from PIL import Image; Image.new("RGB",(2,2)); print("Portable Python imports passed")'],env=environment)
    return installed

def allowed(name):
    relative=Path(name)
    if relative.parts[0] not in FOLDERS and name not in TOP and not name.startswith(('frontends/shared/','frontends/network-editor/src/','frontends/desktop/')) and name not in ('scripts/package_release.py','scripts/bundle_town_example.py'):return False
    if any(part in PRIVATE for part in relative.parts) or relative.name.startswith('.env') or relative.name=='.credentials.yaml' or relative.suffix in ('.pyc','.pyo','.log'):return False
    if relative.parts[0]!='项目演示' and any(part in ('test','tests') for part in relative.parts):return False
    return name not in ('frontends/desktop/package-lock.json','frontends/desktop/package.cjs')

def archive(target,base):
    destination=base/(target.name+'.zip');count=0
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for file in sorted(filesystem_path(target).rglob('*')):
            if not file.is_file():continue
            relative=file.relative_to(filesystem_path(target))
            if '__pycache__' in relative.parts or file.suffix in ('.pyc','.pyo'):continue
            if any(part in ('.git','.credentials.yaml','native-logs','maker-logs') for part in relative.parts) or file.name.startswith('.env') or file.suffix=='.log':raise ValueError('Forbidden release entry: '+str(relative))
            output.write(file,Path(target.name)/relative);count+=1
    with destination.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    (base/'SHA256SUMS.txt').write_text(digest+'  '+destination.name+'\n',encoding='utf-8')
    print(json.dumps(dict(archive=str(destination),bytes=destination.stat().st_size,files=count,sha256=digest)),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-build',action='store_true');parser.add_argument('--zip-only',action='store_true');parser.add_argument('--output-dir',type=Path,default=ROOT/'build/release');parser.add_argument('--desktop-dir',type=Path,default=ROOT/'build/desktop-release');args=parser.parse_args()
    base=args.output_dir.resolve();target=base/f'Nexarbor-{VERSION}-win-x64';desktop_dir=args.desktop_dir.resolve()
    if os.name!='nt':raise SystemExit('Windows x64 release must be assembled on Windows')
    for folder in (base,desktop_dir):
        if not folder.is_relative_to(ROOT):raise ValueError('Release outputs must stay in the target project')
    check_town_example();base.mkdir(parents=True,exist_ok=True)
    if not args.zip_only:
        if target.exists():raise SystemExit('Release already exists; use a new output directory: '+str(target))
        if not args.skip_build:
            node=shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
            command([node,ROOT/'frontends/network-editor/node_modules/vite/bin/vite.js','build'],cwd=ROOT/'frontends/network-editor')
            command([node,ROOT/'frontends/desktop/package.cjs','--out',desktop_dir])
        desktop=desktop_dir/'Nexarbor Workbench-win32-x64'
        if not (desktop/'Nexarbor.exe').is_file():raise SystemExit('Missing desktop build')
        shutil.copytree(desktop,target,ignore=shutil.ignore_patterns('test','tests','user-data','*.log'))
        names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
        for name in names:
            if name and allowed(name) and filesystem_path(ROOT/name).is_file():copy(ROOT/name,target/name)
        shutil.copytree(ROOT/'build/network-editor',target/'build/network-editor')
        shutil.copytree(filesystem_path(ROOT/'node_modules/zod'),filesystem_path(target/'node_modules/zod'),ignore=shutil.ignore_patterns('test','tests','*.map'))
        packages=build_python(target)
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();dirty=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=ROOT,text=True,encoding='utf-8').splitlines()
        dirty=[name for name in dirty if allowed(name)]
        detail=dict(version=VERSION,build='20261029-newcore',source_commit=commit,source_worktree_changes=[dict(path=name,sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()) for name in dirty if (ROOT/name).is_file()],platform='win32-x64',agent_runtime='DeepSeek Harness',python=sys.version.split()[0],python_packages=packages,layout=['domain','app','adapt','frontends'],demo_projects=6,town_final_tick=30)
        (target/'release.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (target/'安装说明.txt').write_text('Nexarbor '+VERSION+'（2026-10-29 新核心）\n\n完整解压后双击 Nexarbor.exe。内置 Electron、Python 和基础依赖，不需要另装 Node.js/Python。\n仍需 Git for Windows 和 DeepSeek Harness；可在工作台设置 Harness 路径、账户或本机 API 连接。\n六份演示在 项目演示/；小镇最终为第六天30时刻，双击Agent查看真实历史。\n详细安装与可选向量依赖：docs/INSTALLATION.md\n',encoding='utf-8')
    check_town_example(target/'resources/examples/npc-town');archive(target,base)

if __name__=='__main__':main()
