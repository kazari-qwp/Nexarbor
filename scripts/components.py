"""Enable/disable catalog entries for the next Harness startup."""
from pathlib import Path
import json, sys, argparse, os
root=Path(__file__).resolve().parents[1]
os.environ.setdefault('DATANET_COMPONENT_ROOT',str(root/'extensions/multi_agent'))
sys.path.insert(0,str(root/'python'))
from datanet.core.component_registry import manifests
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['list','enable','disable'])
parser.add_argument('ids',nargs='*')
args=parser.parse_args()
catalog={m['id']:m for m in manifests()}
file=root/'extensions/multi_agent/profile.json'
profile=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
if args.action!='list':
    if not args.ids:parser.error('Supply at least one component ID')
    for id in args.ids:
        if id not in catalog:parser.error('Unknown component: '+id)
    def enable(id,seen):
        if id in seen:return
        seen.add(id)
        for dep in catalog[id].get('requires',[]):enable(dep,seen)
        profile[id]=True
    for id in args.ids:
        if args.action=='enable':enable(id,set())
        else:profile[id]=False
    tmp=file.with_suffix('.tmp');tmp.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(file)
enabled={id for id,m in catalog.items() if profile.get(id,m.get('enabled',True))}
while True:
    removed={id for id in enabled if any(dep not in enabled for dep in catalog[id].get('requires',[]))}
    if not removed:break
    enabled-=removed
for id in sorted(catalog):print(('ON  ' if id in enabled else 'OFF ')+id)
if args.action!='list':print('配置已保存；重启 Harness 后生效。')
