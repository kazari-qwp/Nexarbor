"""打包真实完成的应用一及原Git bundle恢复方式；不运行业务或模型。"""
from pathlib import Path
import argparse,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();run=a.run.resolve();source=run/'project';target=a.destination.resolve()
 if not run.is_relative_to(ROOT/'build') or not target.is_relative_to(ROOT):raise ValueError('仅打包迁移项目中的实际验收结果')
 if target.exists():raise FileExistsError(target)
 state=json.loads((run/'final-state.json').read_text(encoding='utf8'));group=next(m['state']['group'] for n in state['live']['document']['network']['nodes'] for m in n['tables']['modules'] if m['module_id']=='collaboration.group')
 if group['phase']!='completed' or len(group['candidate']['approvals'])!=4:raise ValueError('尚未完成全体验收')
 shutil.copytree(source,target,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','runs','cache','temp','model-config'))
 metadata=json.loads((target/'nexarbor.json').read_text(encoding='utf8'));metadata.pop('model_settings',None);(target/'nexarbor.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 repository=source/Path(group['workspace']).relative_to(source)/'main'
 def git(*arguments):
  return subprocess.check_output(['git','-C',str(repository),*arguments],text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).strip()
 bundle=target/'.nexarbor/git-bundles/cooperation.bundle';bundle.parent.mkdir(parents=True,exist_ok=True);git('bundle','create',str(bundle),'--all')
 workers=[]
 for block in git('worktree','list','--porcelain').split('\n\n'):
  entries=dict(line.split(' ',1) for line in block.splitlines() if ' ' in line);directory=Path(entries['worktree'])
  if directory.resolve()==repository.resolve():continue
  workers.append(dict(directory=directory.relative_to(source).as_posix(),branch=entries['branch'].removeprefix('refs/heads/')))
 restore=dict(repository=repository.relative_to(source).as_posix(),bundle=bundle.relative_to(target).as_posix(),workers=workers)
 (bundle.parent/'restore.json').write_text(json.dumps(restore,ensure_ascii=False,indent=2),encoding='utf8')
 # 原演示的恢复器仅按项目相对目录恢复真实worktree，不改变业务模块。
 shutil.copyfile(ROOT/'resources/demo/prepare_project.py',target/'准备项目.py')
 (target/'打开项目.cmd').write_text('@echo off\nchcp 65001 >nul\nset "NEXARBOR_ROOT=%~dp0..\.."\n"%NEXARBOR_ROOT%\.venv-runtime\Scripts\python.exe" "%~dp0准备项目.py"\nif errorlevel 1 exit /b 1\nstart "" "%NEXARBOR_ROOT%\frontends\desktop\node_modules\electron\dist\electron.exe" "%NEXARBOR_ROOT%\frontends\desktop" --project "%~dp0."\n',encoding='utf8')
 result=dict(status='packaged-awaiting-cold-client-and-git-check',project=str(target),nodes=len(state['live']['document']['network']['nodes']),agents=sum(n['type']=='agent' for n in state['live']['document']['network']['nodes']),reviewed_commit=group['candidate']['review']['commit'],workers=len(workers),paid_api_calls=0)
 (run/'portable-project.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
