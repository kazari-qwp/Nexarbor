"""Check checksum/CRC, extract long paths and verify the isolated bundled Python."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile,zipfile
from package_release import ROOT,filesystem_path
parser=argparse.ArgumentParser();parser.add_argument('--release-dir',type=Path,default=ROOT/'build/release');args=parser.parse_args()
base=args.release_dir.resolve();archive=base/'Nexarbor-0.9.2-win-x64.zip'
expected=(base/'SHA256SUMS.txt').read_text(encoding='utf-8').split()[0]
with archive.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
assert actual==expected
out=Path(tempfile.mkdtemp(prefix='release-unpacked-',dir=ROOT/'build'))
with zipfile.ZipFile(archive) as source:
    assert source.testzip() is None
    for item in source.infolist():
        relative=Path(item.filename)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert not any(part in ('.git','native-logs','maker-logs') or part.startswith('.env') or part=='.credentials.yaml' for part in relative.parts)
    count=len(source.infolist());source.extractall(filesystem_path(out))
product=out/'Nexarbor-0.9.2-win-x64'
metadata=json.loads((product/'release.json').read_text(encoding='utf-8'))
assert metadata['town_final_tick']==30 and metadata['demo_projects']==6
for name in ('domain','app','adapt','frontends') :assert (product/name).is_dir()
assert not any((product/name).exists() for name in ('python/datanet','adapters','extensions'))
assert hashlib.sha256((product/'domain/core/data_node.py').read_bytes()).digest()==hashlib.sha256((ROOT/'domain/core/data_node.py').read_bytes()).digest()
system=Path(os.environ.get('SystemRoot','C:/Windows'));env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX')};env['PATH']=os.pathsep.join(map(str,[system/'System32',system,system/'System32/WindowsPowerShell/v1.0']))
code='import sys,site,json,ssl,sqlite3,pandas,numpy,llama_index.core; print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,isolated=sys.flags.isolated,user_site=site.ENABLE_USER_SITE)))'
result=subprocess.run([str(product/'runtime/python/python.exe'),'-B','-I','-X','utf8','-c',code],cwd=product,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
runtime=json.loads(result.stdout);assert runtime['isolated']==1 and runtime['user_site'] is False and Path(runtime['prefix']).resolve()==(product/'runtime/python').resolve()
report=dict(passed=True,archive=str(archive),bytes=archive.stat().st_size,sha256=actual,entries=count,extracted=str(product),crc=True,runtime=runtime,metadata=metadata)
(ROOT/'build/release-archive-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({key:report[key] for key in ('passed','archive','sha256','entries','extracted')},ensure_ascii=False))
