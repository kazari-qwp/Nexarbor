"""真实 Harness 协作收尾集成；模型回复为本地夹具，零付费 API。"""
import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp
ROOT=Path(__file__).resolve().parents[1]
folder=Path(mkdtemp(prefix="native-cooperative-",dir=ROOT/"build"))
(folder/"temp").mkdir()
print("Evidence: "+str(folder),flush=True)
executable=Path(os.environ["LOCALAPPDATA"])/"Programs/DeepSeek Harness/DeepSeek Harness.exe"
result=subprocess.run([str(executable),"--experimental-vm-modules",str(ROOT/"tests/native_cooperative_protocol.mjs"),str(folder)],cwd=ROOT,env={**os.environ,"ELECTRON_RUN_AS_NODE":"1"},capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
(folder/"process-output.log").write_text(result.stdout+result.stderr,encoding="utf-8")
print(result.stdout+result.stderr)
raise SystemExit(result.returncode)
