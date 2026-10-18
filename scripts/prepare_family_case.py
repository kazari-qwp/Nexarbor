"""从已验收的节点存档复制到期未兑现状态；保留原数据库所有提交。"""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from datanet.core.checkpoints import Checkpoints
source=Path(sys.argv[1]).resolve();assert source.is_relative_to(ROOT/'build')
target=ROOT/'build'/('native-family-'+str(int(time.time()*1000)));target.mkdir()
store=Checkpoints(source)
try:
    for point in range(store.head,0,-1):
        snapshot=store.read(point);nodes={n['node_id']:n for n in snapshot['network']['nodes']}
        if any(n.startswith('instance-') for n in nodes):continue
        yue=nodes['npc/yue'];clock=nodes['world/time']['modules']['clock.counter']['state'].get('tick',0)
        if clock!=10 or yue['modules']['place.info']['state'].get('location')!='place/hospital':continue
        agreements=nodes['place/home1']['modules']['agreements.pair']['state'].get('agreements',[])
        match=next((a for a in agreements if a.get('status')=='pending' and a.get('due_tick',11)<=10 and not a.get('pending')),None)
        if match:break
    else:raise ValueError('没有找到到期但尚未办理的家庭状态')
    document=dict(network=snapshot['network'],files={name:text or '' for name,text in snapshot['files'].items()})
    (target/'initial.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'case.json').write_text(json.dumps(dict(source=str(source),commit=point,agreement=match['id'],name='小苗'),ensure_ascii=False,indent=2),encoding='utf-8');print(target)
finally:store.close()
