"""Add stable declared module tool IDs to delivered serialized tables; no dependency walk."""
from pathlib import Path
from hashlib import sha256
import json,argparse
ROOT=Path(__file__).resolve().parents[1]
def update(folder,*,write=False):
    manifests={}
    for base in (ROOT/'projects',ROOT/'modules',folder/'modules'):
        for file in base.rglob('module.json') if base.exists() else ():
            spec=json.loads(file.read_text(encoding='utf-8-sig'));manifests[spec['id']]=spec
    changed=[]
    def node(value):
        count=0
        def tool(item):
            nonlocal count
            if isinstance(item,dict):
                owner=item.get('factory_module');name=item.get('tool')
                if owner and name and 'factory_key' not in item:
                    specs=manifests[owner].get('agent_tools',[]);names={}
                    for spec in specs:
                        names[spec['id']]=spec['id']
                        for actor in {value['node_id'],item.get('description','').split(' · ')[0]}:
                            source=sha256((actor+'\0'+owner).encode()).hexdigest()[:24];names['mod_'+sha256((source+'\0'+spec['id']).encode()).hexdigest()[:24]]=spec['id']
                    item['factory_key']=names.get(name,name)
                    count+=1
                for part in item.values():tool(part)
            elif isinstance(item,list):
                for part in item:tool(part)
        tool(value['tables']);return count
    def visit(value):
        if isinstance(value,dict):
            count=node(value) if 'node_id' in value and 'tables' in value else 0
            return count+sum(visit(v) for k,v in value.items() if k!='tables')
        return sum(visit(v) for v in value) if isinstance(value,list) else 0
    for base in (folder/'nodes',folder/'network_presets',folder/'networks'):
        for file in base.rglob('*.json') if base.exists() else ():
            value=json.loads(file.read_text(encoding='utf-8-sig'));count=visit(value)
            if count:changed.append((file,value,count))
    if write:
        for file,value,count in changed:file.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'folder':str(folder),'files':len(changed),'tools':sum(count for _,_,count in changed),'written':write}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);p.add_argument('--write',action='store_true');a=p.parse_args()
    for folder in a.folders:print(json.dumps(update(folder.resolve(),write=a.write),ensure_ascii=False))
