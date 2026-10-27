"""使用已安装 Harness 验证原 JSONL/AgentLoop 恢复规则；模型为本地确定性替身。"""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {
    "native_session_restore_test.cjs": "PASS native compressed persistence",
    "native_loop_restore_test.cjs": "PASS native AgentLoop",
    "native_node_lock_positions.cjs": '"passed":true',
}


def main():
    executable = Path(os.environ["LOCALAPPDATA"]) / "Programs/DeepSeek Harness/DeepSeek Harness.exe"
    if not executable.is_file():
        raise FileNotFoundError("需要已安装的 DeepSeek Harness：" + str(executable))
    evidence = {"paid_api_calls": 0, "fixtures": []}
    output = ROOT / "build/migration/native-runtime-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    for fixture, marker in FIXTURES.items():
        completed = subprocess.run(
            [str(executable), "--experimental-vm-modules", str(ROOT / "tests" / fixture)],
            cwd=ROOT, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        passed = completed.returncode == 0 and marker in completed.stdout
        evidence["fixtures"].append({"name": fixture, "passed": passed, "exit_code": completed.returncode,
                                     "stdout": completed.stdout, "stderr": completed.stderr})
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(completed.stdout.strip() or completed.stderr.strip(), flush=True)
        if not passed:
            print(completed.stderr, file=sys.stderr)
            return 1
    print("原生运行时恢复验证通过；证据：" + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
