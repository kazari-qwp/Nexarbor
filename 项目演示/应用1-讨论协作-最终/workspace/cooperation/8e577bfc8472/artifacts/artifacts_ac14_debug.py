import os, subprocess, sys, tempfile, json
from pathlib import E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ath
ROOT=E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ath(r'E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140')
E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140Y=sys.executable
def run(cmd, env=None, cwd=ROOT):
    e=dict(os.environ); e["E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140YTHONE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ATH"]=str(ROOT)+os.pathsep+e.get("E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140YTHONE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ATH",""); e.pop("E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140YTHONHOME",None)
    if env is not None: e=env
    return subprocess.run(cmd,stdout=subprocess.E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140IE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140E,stderr=subprocess.E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140IE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140E,cwd=str(cwd),env=e)
with tempfile.TemporaryDirectory() as tmp:
    tmp=E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ath(tmp)
    proc=run([E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140Y,"-m","pip","wheel",".","--no-build-isolation","-w",str(tmp)],timeout=600)
    print("wheel rc",proc.returncode, proc.stdout.decode('utf-8','replace')[-500:], proc.stderr.decode('utf-8','replace')[-500:])
    wheels=sorted(tmp.glob("hone-*.whl")); print("wheels",wheels)
    wheel=wheels[-1]
    venv=tmp/"venv"
    proc=run([E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140Y,"-m","venv",str(venv)],timeout=300)
    print("venv rc",proc.returncode, proc.stderr.decode('utf-8','replace')[-500:])
    vpy=venv/("Scripts/python.exe" if os.name=="nt" else "bin/python")
    print("vpy exists",vpy.exists())
    proc=run([str(vpy),"-m","pip","install","--no-index","--no-deps",str(wheel)],timeout=300)
    print("install rc",proc.returncode, proc.stdout.decode('utf-8','replace')[-1000:], proc.stderr.decode('utf-8','replace')[-1000:])
    env=dict(os.environ); env.pop("E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140YTHONE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140ATH",None)
    proc=subprocess.run([str(vpy),"-c","import sys; print(sys.executable); print(sys.path); import hone; from hone.hone import Hone; print(hone.Hone is Hone)"],stdout=subprocess.E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140IE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140E,stderr=subprocess.E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140IE:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\workers\6fe0f5dd8699d140E,cwd=str(tmp),env=env,timeout=120)
    print("import rc",proc.returncode)
    print("OUT",proc.stdout.decode('utf-8','replace'))
    print("ERR",proc.stderr.decode('utf-8','replace'))
    print("site",list((venv/"Lib/site-packages").glob('*')))
