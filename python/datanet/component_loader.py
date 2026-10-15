"""Mount explicitly selected extension and optional executor namespaces."""
from pathlib import Path
import json,os,sys

def mount(root=None):
    configured=root or os.environ.get('DATANET_COMPONENT_ROOT')
    if configured:
        from .component_catalog import mount_paths
        mount_paths(configured)
    product=Path(os.environ.get('DATANET_PRODUCT_ROOT',Path(__file__).resolve().parents[2]))
    for name in json.loads(os.environ.get('DATANET_EXECUTORS','[]')):
        entry=(product/'executors'/name/'python').resolve()
        if not entry.is_relative_to((product/'executors').resolve()):raise ValueError('Executor outside runtime directory')
        if str(entry) not in sys.path:sys.path.append(str(entry))
mount()
