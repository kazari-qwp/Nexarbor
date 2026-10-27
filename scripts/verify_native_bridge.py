"""运行生产 RPC/DSH/JSONL 全链路，模型 HTTP 仅使用本地确定性测试服务。"""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime.backend import Backend
from modules.context_assembler import ContextAssemblerModule


def main():
    directory = Path(mkdtemp(prefix='native-bridge-', dir=ROOT / 'build')).resolve()
    (directory / 'temp').mkdir()
    backend = Backend(directory)
    try:
        node = backend.network.get('root')
        node.dataer.write('RPC_ORIGINAL')
        node.install(ContextAssemblerModule({'sources': [dict(id='rule', type='text', kind='system_prompt',
            text='Use the provided memory tools and return their results.')]}))
        backend.bindings['root'] = dict(executor='harness', strength=1, channels=[],
            prepare=[dict(module='context.assembler', operation='assemble', channels=[])])
        backend.save()
    finally:backend.close()
    executable = Path(os.environ['LOCALAPPDATA']) / 'Programs/DeepSeek Harness/DeepSeek Harness.exe'
    result = subprocess.run([str(executable), '--experimental-vm-modules', str(ROOT / 'tests/native_bridge_integration.mjs'), str(directory)],
        cwd=ROOT, env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'), capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (directory / 'process-output.json').write_text(json.dumps(dict(stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode),ensure_ascii=False,indent=2),encoding='utf-8')
    print(result.stdout.strip(), flush=True)
    print('Evidence:', directory, flush=True)
    if result.returncode:print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == '__main__':raise SystemExit(main())
