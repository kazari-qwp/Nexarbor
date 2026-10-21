"""Inspect/select independently loadable components for the next runtime startup."""
from pathlib import Path
import argparse, json, os, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['list','select','enable','disable'])
parser.add_argument('ids',nargs='*')
parser.add_argument('--root',type=Path,default=ROOT/'extensions/development')
args=parser.parse_args()
os.environ['DATANET_COMPONENT_ROOT']=str(args.root.resolve())
from datanet.component_catalog import resolve,discover,read_json,dependency
catalog=discover()
for key in args.ids:
    if key not in catalog:parser.error('Unknown component: '+key)
if args.action=='select':
    file=args.root/'selection.json'
    file.write_text(json.dumps({'select':args.ids},indent=2)+'\n',encoding='utf-8')
elif args.action in ['enable','disable']:
    if not args.ids:parser.error('Supply at least one component ID')
    file=args.root/'profile.json';profile=read_json(file,{})
    def enable(key,seen):
        if key in seen:return
        seen.add(key)
        for dep in catalog[key].get('requires',[]):enable(dependency(dep)[0],seen)
        profile[key]=True
    for key in args.ids:
        if args.action=='enable':enable(key,set())
        else:profile[key]=False
    file.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
catalog,order,blocked=resolve()
for key in sorted(catalog):print(('ON  ' if key in order else 'BLOCKED ' if key in blocked else 'OFF ')+key)
if args.action!='list':print('配置已保存；重启运行时后生效。')
