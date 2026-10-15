"""Stage the declared plugin files without Python bytecode caches."""
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
staging = root / 'build' / 'plugin-staging'
if staging.exists():
    if staging.resolve().parent != (root / 'build').resolve():
        raise RuntimeError('Unexpected package staging path')
    shutil.rmtree(staging)
staging.mkdir(parents=True)
manifest = json.loads((root / 'package.json').read_text(encoding='utf-8'))
for name in ['package.json', *manifest['files']]:
    source = (root / name).resolve()
    if not source.is_relative_to(root):
        raise RuntimeError('Package entry is outside the product directory')
    target = staging / name
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
print(staging)
