"""Build the portable Windows workbench; no credentials or development artifacts."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata as metadata, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path
from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
BASE=ROOT/'build/release'
TARGET=BASE/f'Nexarbor-{VERSION}-win-x64'

def command(args,**kwargs):
    subprocess.run([str(value) for value in args],cwd=ROOT,check=True,**kwargs)

def copy(source: Path,target: Path):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)

def build_python():
    base=Path(sys.base_prefix)
    target=TARGET/'runtime/python'
    target.mkdir(parents=True,exist_ok=True)
    for file in base.iterdir():
        if file.is_file() and (file.suffix.lower()=='.dll' or file.name in ('python.exe','pythonw.exe','LICENSE_PYTHON.txt')):
            copy(file,target/file.name)
    for folder in ('DLLs','Lib'):
        source=base/folder
        for current,folders,files in os.walk(source):
            folders[:]=[name for name in folders if name not in ('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo')]
            for name in files:
                file=Path(current)/name;relative=file.relative_to(source)
                if file.suffix not in ('.pyc','.pyo','.pdb') and not file.name.startswith('_test'):
                    copy(file,target/folder/relative)
    # Conda Python keeps the standard library's shared libraries in Library/bin.
    for name in ('libssl-3-x64.dll','libcrypto-3-x64.dll','sqlite3.dll','libbz2.dll','liblzma.dll','libffi-8.dll','ffi-7.dll','ffi-8.dll','ffi.dll','zlib.dll'):
        source=base/'Library/bin'/name
        if source.exists():copy(source,target/name)
    installed={}
    def dependency(name):
        distribution=metadata.distribution(name)
        identity=distribution.metadata['Name'].lower().replace('_','-')
        if identity in installed:return
        installed[identity]=distribution.version
        for item in distribution.files or []:
            relative=Path(str(item))
            if relative.is_absolute() or '..' in relative.parts or any(part in ('tests','test','__pycache__') for part in relative.parts) or relative.suffix in ('.pyc','.pyo'):continue
            source=Path(distribution.locate_file(item))
            if source.is_file():copy(source,target/'Lib/site-packages'/relative)
        for definition in distribution.requires or []:
            requirement=Requirement(definition)
            if requirement.marker and not requirement.marker.evaluate({'extra':''}):continue
            dependency(requirement.name)
    for name in ('filelock','jsonschema','PyYAML','pandas','Pillow','fsspec','requests','llama-index-core','pip'):
        dependency(name)
    (target/'runtime-packages.json').write_text(json.dumps(installed,indent=2)+'\n',encoding='utf-8')
    # Verify this runtime without the developer's venv, user site or PYTHONPATH.
    command([target/'python.exe','-B','-I','-c','import ssl,sqlite3,bz2,lzma,ctypes,jsonschema,filelock,yaml,pandas,numpy,PIL,fsspec; print("Portable Python imports passed")'],env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')})
    return installed

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-build',action='store_true');parser.add_argument('--zip-only',action='store_true');args=parser.parse_args()
    if os.name!='nt':raise SystemExit('Windows x64 release must be assembled on Windows.')
    BASE.mkdir(parents=True,exist_ok=True)
    if not args.zip_only:
        if TARGET.exists():raise SystemExit('Release staging already exists. Move it aside before rebuilding: '+str(TARGET))
        if not args.skip_build:
            npm=shutil.which('npm.cmd') or r'C:\Program Files\nodejs\npm.cmd'
            node=shutil.which('node') or r'C:\Program Files\nodejs\node.exe'
            command([npm,'--prefix','frontends/network-editor','run','build'])
            command([node,ROOT/'frontends/desktop/package.cjs'])
        desktop=ROOT/'build/desktop/Nexarbor Workbench-win32-x64'
        if not (desktop/'Nexarbor.exe').is_file():raise SystemExit('Missing desktop build. Run without --skip-build.')
        shutil.copytree(desktop,TARGET,ignore=shutil.ignore_patterns('test','tests','user-data','*.log'))
        names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
        folders={'adapters','communication','shared','python','extensions','configs','docs','scripts'}
        for name in names:
            if not name:continue
            relative=Path(name);source=ROOT/relative
            if not source.is_file() or (relative.parts[0] not in folders and name not in ('README.md','README_EN.md','package.json','requirements-runtime.txt')):continue
            if any(part in ('test','tests','__pycache__','node_modules') for part in relative.parts):continue
            if name.startswith('adapters/harness/runtime/backend/'):continue
            copy(source,TARGET/relative)
        web=Path('extensions/editor/capabilities/network_editor/web')
        shutil.copytree(ROOT/web,TARGET/web,dirs_exist_ok=True)
        if (ROOT/'node_modules/zod').exists():
            shutil.copytree(ROOT/'node_modules/zod',TARGET/'node_modules/zod',ignore=shutil.ignore_patterns('test','tests','*.map'))
        packages=build_python()
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        (TARGET/'release.json').write_text(json.dumps({'version':VERSION,'source_commit':commit,'platform':'win32-x64','agent_runtime':'DeepSeek Harness','python':sys.version.split()[0],'python_packages':packages},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (TARGET/'安装说明.txt').write_text('Nexarbor '+VERSION+'\n\n先安装 Git for Windows 和 DeepSeek Harness，并在 Harness 完成账户授权。\n完整解压后双击 Nexarbor.exe，新建或打开项目文件夹。\n安装与组件装配：docs/INSTALLATION.md\n可选向量检索依赖与模型按需安装，详见同一说明。\n',encoding='utf-8')
    archive=BASE/(TARGET.name+'.zip')
    count=0
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for file in sorted(TARGET.rglob('*')):
            if not file.is_file():continue
            relative=file.relative_to(TARGET)
            if '__pycache__' in relative.parts or file.suffix in ('.pyc','.pyo'):continue
            if any(part in ('.git','.credentials.yaml','native-logs','maker-logs') for part in relative.parts) or file.suffix=='.log' or file.name.startswith('.env'):
                raise RuntimeError('Forbidden release entry: '+str(relative))
            output.write(file,Path(TARGET.name)/relative);count+=1
    digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
    (BASE/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':count,'sha256':digest}))

if __name__=='__main__':main()
