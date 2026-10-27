"""真实 API 验收原小镇五天（25 tick），并验证原生会话冷重开。"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--days',type=int,choices=range(1,6),default=5);parser.add_argument('--resume-directory',type=Path);args=parser.parse_args()
    values=dotenv_values(ROOT/'.env')
    key=values.get('DEEPSEEK_API_KEY') or ''
    if not key:raise RuntimeError('本项目未配置 DEEPSEEK_API_KEY')
    directory=args.resume_directory.resolve() if args.resume_directory else Path(mkdtemp(prefix='native-town-newcore-',dir=ROOT/'build')).resolve()
    if args.resume_directory and not (directory/'resume-source.json').is_file():raise ValueError('续跑目录必须先通过 town_resume/prepare.py 校验恢复')
    (directory/'temp').mkdir(exist_ok=True)
    env=dict(os.environ,ELECTRON_RUN_AS_NODE='1')
    for name in ('DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL'):
        if values.get(name):env[name]=values[name]
    executable=Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
    print('Evidence: '+str(directory),flush=True)
    process=subprocess.Popen([str(executable),'--experimental-vm-modules',str(ROOT/'scripts/native_town_acceptance.mjs'),str(directory),str(args.days)],cwd=ROOT,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=[]
    try:
        for line in process.stdout:
            safe=line.replace(key,'[已隐藏密钥]');output.append(safe);print(safe,end='',flush=True)
        code=process.wait()
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=15)
    (directory/'process-output.json').write_text(json.dumps(dict(output=''.join(output),exit_code=code),ensure_ascii=False,indent=2),encoding='utf-8')
    return code


if __name__=='__main__':raise SystemExit(main())
