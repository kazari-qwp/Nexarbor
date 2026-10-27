"""验证真实 DSH 压缩、超限恢复与冷重开；只调用本地 HTTP 模型夹具。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--harness-exe',action='append',type=Path)
    args=parser.parse_args()
    executables=args.harness_exe or [Path(os.environ.get('DATANET_HARNESS_EXE') or Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe')]
    evidence={'paid_api_calls':0,'fixtures':[]}
    for executable in executables:
        folder=Path(mkdtemp(prefix='native-compaction-',dir=ROOT/'build'))
        result=subprocess.run([str(executable),'--experimental-vm-modules',str(ROOT/'tests/native_compaction_integration.mjs'),str(folder)],cwd=ROOT,
            env={**os.environ,'ELECTRON_RUN_AS_NODE':'1','DATANET_HARNESS_EXE':str(executable)},capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (folder/'process-output.json').write_text(json.dumps({'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False,indent=2),encoding='utf-8')
        verification=folder/'verification.json'
        passed=result.returncode==0 and verification.exists() and json.loads(verification.read_text(encoding='utf-8'))['passed']
        evidence['fixtures'].append({'executable':str(executable),'directory':str(folder),'passed':passed})
        print(json.dumps(evidence['fixtures'][-1],ensure_ascii=False),flush=True)
        if not passed:
            print(result.stdout[-4000:]);print(result.stderr[-4000:]);return 1
    (ROOT/'build/migration').mkdir(parents=True,exist_ok=True)
    (ROOT/'build/migration/native-compaction-verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':raise SystemExit(main())
