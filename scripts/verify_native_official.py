"""验证应用选定与默认安装两套 Harness 的真实官方工具；不调用模型。"""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = Path(os.environ["LOCALAPPDATA"]) / "Programs/DeepSeek Harness/DeepSeek Harness.exe"
    results = []
    for label, extra in [("configured", {}), ("default_installation", {"DATANET_HARNESS_EXE":str(executable)})]:
        result = subprocess.run([str(executable), str(ROOT / "scripts/native_official_acceptance.mjs")],
                                cwd=ROOT, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1", **extra),
                                capture_output=True, text=True, encoding="utf-8", timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(label + ": " + result.stdout.strip(), flush=True)
        if result.returncode:
            print(result.stderr, flush=True)
            return result.returncode
        results.append({"installation":label, **json.loads(result.stdout.strip().splitlines()[-1])})
    (ROOT / "build/official-installations-verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
