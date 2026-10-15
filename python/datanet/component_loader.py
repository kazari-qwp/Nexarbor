"""Mount explicitly selected extension and optional executor namespaces."""
from pathlib import Path
import json,os,sys

def mount(root=None):
    configured=root or os.environ.get('DATANET_COMPONENT_ROOT')
    if configured:
        root=Path(configured).resolve()
        for file in sorted(root.glob('*/*/component.json')):
            m=json.loads(file.read_text(encoding='utf-8'));relative=m.get('python',{}).get('path')
            if relative:
                entry=str((file.parent/relative).resolve())
                if entry not in sys.path:sys.path.append(entry)
    product=Path(os.environ.get('DATANET_PRODUCT_ROOT',Path(__file__).resolve().parents[3]))
    for name in json.loads(os.environ.get('DATANET_EXECUTORS','[]')):
        entry=(product/'executors'/name/'python').resolve()
        if not entry.is_relative_to((product/'executors').resolve()):raise ValueError('Executor outside runtime directory')
        if str(entry) not in sys.path:sys.path.append(str(entry))
mount()
