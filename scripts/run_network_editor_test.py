"""Launch a separate, bounded native Mock host for browser workbench acceptance."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'build'/('network-editor-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
args=parser.parse_args();run=args.output.resolve()
if not run.is_relative_to(ROOT/'build'):parser.error('Test output must stay under this repository build directory')
run.mkdir(parents=True,exist_ok=False)
exe=Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
with (run/'host.stdout.log').open('ab') as stdout,(run/'host.stderr.log').open('ab') as stderr:
    process=subprocess.Popen([str(exe),'--experimental-vm-modules',str(ROOT/'tests/native_network_editor_test.cjs')],cwd=ROOT,
        env=dict(os.environ,ELECTRON_RUN_AS_NODE='1',DATANET_TEST_OUTPUT=str(run)),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'host-process.json').write_text(json.dumps(dict(pid=process.pid,executable=str(exe),script=str(ROOT/'tests/native_network_editor_test.cjs'),run=str(run)),indent=2),'utf-8')
deadline=time.monotonic()+45
while time.monotonic()<deadline:
    if process.poll() is not None:raise RuntimeError((run/'host.stderr.log').read_text('utf-8'))
    if (run/'editor.json').exists():print('Editor ready. Connection file:',run/'editor.json');break
    time.sleep(.5)
else:raise TimeoutError('Editor host did not start within 45 seconds')
