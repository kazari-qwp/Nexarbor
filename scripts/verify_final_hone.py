"""按原入口、两预设及公开输入运行hone；默认仅本地预检。"""
import argparse,json,os,shutil,subprocess
from pathlib import Path
from tempfile import mkdtemp
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
 directory=Path(mkdtemp(prefix='final-hone-',dir=ROOT/'build'));project=directory/'project';shutil.copytree(ROOT/'项目演示/应用1-讨论协作-初始',project)
 request=(ROOT/'tests/evaluation/hone/request.txt').read_text(encoding='utf8');spec=dict(project=str(project),runtime=str(directory/'runtime'),request=request)
 (directory/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf8')
 env=dict(os.environ,PYTHONUTF8='1');env.pop('ELECTRON_RUN_AS_NODE',None);secrets=[]
 if args.live:
  values=dotenv_values(ROOT/'.env')
  for name in ['DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL']:
   if values.get(name):env[name]=values[name]
  secrets=[env.get('DEEPSEEK_API_KEY','')]
 print('Evidence: '+str(directory),flush=True)
 with (directory/'process.log').open('w',encoding='utf8') as log:
  process=subprocess.Popen([r'C:\Program Files\nodejs\node.exe',str(ROOT/'scripts/native_final_hone.mjs'),str(directory),*(['--live'] if args.live else [])],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  for line in process.stdout:
   for secret in secrets:
    if secret:line=line.replace(secret,'[已隐藏密钥]')
   log.write(line);log.flush();print(line.rstrip(),flush=True)
  return process.wait()
if __name__=='__main__':raise SystemExit(main())
