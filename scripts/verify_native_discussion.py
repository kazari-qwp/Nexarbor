"""真实 API 验收实际讨论协作项目和同会话冷重开。"""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from threading import Timer
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]


def main():
    values=dotenv_values(ROOT/'.env')
    key=values.get('DEEPSEEK_API_KEY') or ''
    if not key:raise RuntimeError('本项目未配置 DEEPSEEK_API_KEY')
    directory=Path(mkdtemp(prefix='native-discussion-newcore-',dir=ROOT/'build')).resolve()
    (directory/'temp').mkdir()
    env=dict(os.environ,ELECTRON_RUN_AS_NODE='1')
    for name in ('DEEPSEEK_API_KEY','DEEPSEEK_MODEL','DEEPSEEK_BASE_URL'):
        if values.get(name):env[name]=values[name]
    executable=Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
    print('Evidence: '+str(directory),flush=True)
    process=subprocess.Popen([str(executable),'--experimental-vm-modules',str(ROOT/'scripts/native_discussion_acceptance.mjs'),str(directory)],cwd=ROOT,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=[]
    timer=Timer(2400,process.terminate);timer.daemon=True;timer.start()
    try:
        for line in process.stdout:
            safe=line.replace(key,'[已隐藏密钥]');output.append(safe);print(safe,end='',flush=True)
        code=process.wait(timeout=2400)
    finally:
        timer.cancel()
        if process.poll() is None:process.terminate();process.wait(timeout=15)
    (directory/'process-output.json').write_text(json.dumps(dict(output=''.join(output),exit_code=code),ensure_ascii=False,indent=2),encoding='utf-8')
    return code


if __name__=='__main__':raise SystemExit(main())
