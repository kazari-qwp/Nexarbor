from pathlib import Path
import os,sys,json
default_root=Path(sys.executable).resolve().parents[4] if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[3]
PRODUCT_ROOT=Path(os.environ.get("DATANET_PRODUCT_ROOT",default_root)).resolve()
PROJECT_ROOT=PRODUCT_ROOT
COMPONENTS_DIR=Path(os.environ.get("DATANET_COMPONENT_ROOT",PRODUCT_ROOT/"extensions/.none"))
os.environ.setdefault("DATANET_COMPONENT_ROOT",str(COMPONENTS_DIR))
sys.path.insert(0,str(PRODUCT_ROOT/"python"))
from datanet.component_catalog import mount_paths
mount_paths(COMPONENTS_DIR)
from pkgutil import extend_path
for name in sorted(list(sys.modules),key=lambda name:name.count('.')):
    module=sys.modules[name]
    if (name=='datanet' or name.startswith('datanet.')) and hasattr(module,'__path__'):
        module.__path__=extend_path(module.__path__,name)
