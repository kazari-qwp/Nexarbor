"""原桌面右键咨询入口；可选真实 DeepSeek API，凭据只交给本机模型连接库。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    directory=Path(mkdtemp(prefix='desktop-consultation-',dir=ROOT/'build')).resolve()
    env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
    secrets=[]
    if args.live:
        values=dotenv_values(ROOT/'.env')
        for name in ('DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL'):
            if values.get(name):env[name]=values[name]
        secrets=[env.get('DEEPSEEK_API_KEY','')]
    command=[r'C:\Program Files\nodejs\node.exe','test/workbench-current.browser.mjs',str(directory),*(['--live'] if args.live else [])]
    print('Evidence: '+str(directory),flush=True)
    process=subprocess.run(command,cwd=ROOT/'frontends/network-editor',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=process.stdout
    for secret in secrets:
        if secret:output=output.replace(secret,'[已隐藏密钥]')
    (directory/'process-output.json').write_text(json.dumps(dict(output=output,exit_code=process.returncode),ensure_ascii=False,indent=2),encoding='utf-8')
    print(output,flush=True)
    return process.returncode

if __name__=='__main__':raise SystemExit(main())
