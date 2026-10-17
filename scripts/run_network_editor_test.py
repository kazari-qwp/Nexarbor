"""Launch a separate, bounded native Mock host for browser workbench acceptance."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'build'/('network-editor-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
parser.add_argument('--resume',type=Path,help='Reopen an expired test workbench without sending model input')
args=parser.parse_args();run=(args.resume or args.output).resolve()
if not run.is_relative_to(ROOT/'build'):parser.error('Test output must stay under this repository build directory')
resume_session=None
if args.resume:
    connections=sorted((run/'.datanet/networks').glob('*/editor-connection.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not connections:parser.error('No saved workbench to reopen')
    connection=json.loads(connections[0].read_text('utf-8'));url=urllib.parse.urlparse(connection['url'])
    if url.scheme!='http' or url.hostname!='127.0.0.1':parser.error('Invalid local workbench address')
    try:
        with urllib.request.urlopen(urllib.parse.urlunparse(url._replace(path='/',fragment='')),timeout=1) as response:
            if response.status==200:print('Workbench is already running; no second host started.');raise SystemExit(0)
    except OSError:pass
    resume_session=bytes.fromhex(connections[0].parent.name).decode('utf-8')
    manifest=json.loads((run/'sessions-manifest.json').read_text('utf-8'))
    if not any(s['actor']=='root' and s['session_id']==resume_session for s in manifest['sessions']):parser.error('Saved root session is not in this test manifest')
else:run.mkdir(parents=True,exist_ok=False)
exe=Path(os.environ['LOCALAPPDATA'])/'Programs/DeepSeek Harness/DeepSeek Harness.exe'
started=time.time()
with (run/'host.stdout.log').open('ab') as stdout,(run/'host.stderr.log').open('ab') as stderr:
    process=subprocess.Popen([str(exe),'--experimental-vm-modules',str(ROOT/'tests/native_network_editor_test.cjs')],cwd=ROOT,
        env=dict(os.environ,ELECTRON_RUN_AS_NODE='1',DATANET_TEST_OUTPUT=str(run),**({'DATANET_EDITOR_ROOT_SESSION':resume_session} if resume_session else {})),stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'host-process.json').write_text(json.dumps(dict(pid=process.pid,executable=str(exe),script=str(ROOT/'tests/native_network_editor_test.cjs'),run=str(run)),indent=2),'utf-8')
deadline=time.monotonic()+45
while time.monotonic()<deadline:
    if process.poll() is not None:raise RuntimeError((run/'host.stderr.log').read_text('utf-8'))
    if (run/'editor.json').exists() and (run/'editor.json').stat().st_mtime>=started:print('Editor ready. Connection file:',run/'editor.json');break
    time.sleep(.5)
else:raise TimeoutError('Editor host did not start within 45 seconds')
