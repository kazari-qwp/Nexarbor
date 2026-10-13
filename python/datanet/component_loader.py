"""Mount component-owned Python namespaces using the package manifests."""
from pathlib import Path
import json, os, sys
def mount():
    root=Path(os.environ.get('DATANET_COMPONENT_ROOT',Path(__file__).resolve().parents[2]/'components'))
    for file in sorted(root.glob('*/*/component.json')):
        relative=json.loads(file.read_text(encoding='utf-8')).get('python',{}).get('path')
        if relative:
            entry=str(file.parent/relative)
            if entry not in sys.path:sys.path.append(entry)
mount()
