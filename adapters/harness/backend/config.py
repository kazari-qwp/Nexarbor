from pathlib import Path
import os,sys,json
default_root=Path(sys.executable).resolve().parents[4] if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[3]
PRODUCT_ROOT=Path(os.environ.get("DATANET_PRODUCT_ROOT",default_root)).resolve()
PROJECT_ROOT=PRODUCT_ROOT
COMPONENTS_DIR=PRODUCT_ROOT/"components"
os.environ.setdefault("DATANET_COMPONENT_ROOT",str(COMPONENTS_DIR))
sys.path.insert(0,str(PRODUCT_ROOT/"python"))
for file in sorted(COMPONENTS_DIR.glob("*/*/component.json")):
    m=json.loads(file.read_text(encoding="utf-8"))
    for section,key in [("python","path"),("harness","python_path")]:
        relative=m.get(section,{}).get(key)
        if relative:sys.path.append(str(file.parent/relative))
from pkgutil import extend_path
for name in sorted(list(sys.modules),key=lambda name:name.count('.')):
    module=sys.modules[name]
    if (name=='datanet' or name.startswith('datanet.') or name=='harness_components' or name.startswith('harness_components.')) and hasattr(module,'__path__'):
        module.__path__=extend_path(module.__path__,name)
