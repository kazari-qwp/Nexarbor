"""Package the actually completed knowledge application and its native portable history."""
from pathlib import Path
import argparse,json,shutil,subprocess
from scripts.stabilize_tool_references import update
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('destination',type=Path);args=parser.parse_args();run=args.run.resolve();target=args.destination.resolve()
    if not run.is_relative_to(ROOT/'build') or not target.is_relative_to(ROOT/'项目演示'):raise ValueError('Expected the actual migration run and a demo destination')
    acceptance=json.loads((run/'independent-data-audit.json').read_text(encoding='utf-8'))
    if not acceptance['passed']:raise ValueError('Independent application acceptance has not passed')
    if target.exists():raise FileExistsError(target)
    source=run/'project';shutil.copytree(source,target,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','runs','cache','temp','model-config'))
    file=target/'nexarbor.json';manifest=json.loads(file.read_text(encoding='utf-8'));manifest.pop('model_settings',None);file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    stable=update(target,write=True)
    bundle=target/'.nexarbor/git-bundles/project.bundle';bundle.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','-C',str(source),'bundle','create',str(bundle),'--all'],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (target/'打开项目.cmd').write_text('@echo off\nchcp 65001 >nul\nset "NEXARBOR_ROOT=%~dp0..\\.."\nstart "" "%NEXARBOR_ROOT%\\frontends\\desktop\\node_modules\\electron\\dist\\electron.exe" "%NEXARBOR_ROOT%\\frontends\\desktop" --project "%~dp0."\n',encoding='utf-8')
    report={'status':'packaged-awaiting-cold-client','project':str(target),'paid_api_calls':0,'record_versions':acceptance['versions'],'observations':acceptance['observations'],'tool_reference_metadata':stable,'original_git_bundle':bundle.relative_to(target).as_posix()}
    (run/'portable-project.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
