"""实际讨论项目的无模型 RPC/SDK 装配验证。"""

import json
import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = Path(mkdtemp(prefix="native-discussion-project-", dir=ROOT / "build")).resolve()
    (directory / "temp").mkdir()
    executable = Path(os.environ["LOCALAPPDATA"]) / "Programs/DeepSeek Harness/DeepSeek Harness.exe"
    result = subprocess.run([str(executable), "--experimental-vm-modules", str(ROOT / "tests/native_discussion_project_integration.mjs"), str(directory)],
                            cwd=ROOT, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"),
                            capture_output=True, text=True, encoding="utf-8", timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (directory / "process-output.json").write_text(json.dumps({"stdout":result.stdout, "stderr":result.stderr, "exit_code":result.returncode}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result.stdout.strip(), flush=True)
    print("Evidence:", directory, flush=True)
    if result.returncode:print(result.stderr, flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
