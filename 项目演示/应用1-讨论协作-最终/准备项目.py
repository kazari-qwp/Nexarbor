"""Restore the demo's real collaboration repository and worktrees after copying."""
from pathlib import Path
import json,subprocess,shutil,os
root=Path(__file__).resolve().parent
info=json.loads((root/'.nexarbor/git-bundles/restore.json').read_text(encoding='utf-8'))
def local(relative):
 p=(root/relative).resolve()
 if not p.is_relative_to(root):raise ValueError('Project path escapes demo')
 return p
def git(directory,*args):
 subprocess.run(['git','-C',str(directory),*args],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
main=local(info['repository'])
if not (main/'.git').exists():
 git(main,'init','-b','main')
 git(main,'fetch','--update-head-ok',str(local(info['bundle'])),'+refs/heads/*:refs/heads/*')
 git(main,'reset','--mixed','HEAD')
 git(main,'config','user.name','Nexarbor')
 git(main,'config','user.email','local@nexarbor.invalid')
for entry in info['workers']:
 worker=local(entry['directory'])
 if (worker/'.git').exists():continue
 backup=local('.nexarbor/cache/worktree-original/'+worker.name)
 if worker.exists():
  backup.parent.mkdir(parents=True,exist_ok=True)
  if backup.exists():raise ValueError('Existing worktree backup; inspect before restoring')
  worker.rename(backup)
 git(main,'worktree','add',str(worker),entry['branch'])
 if backup.exists():shutil.copytree(backup,worker,dirs_exist_ok=True)
