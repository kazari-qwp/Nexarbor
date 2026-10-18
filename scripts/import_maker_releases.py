"""维护时将验收后的制作产物收进组件源码；成品运行不依赖此脚本。"""
from pathlib import Path
from hashlib import sha256
import json,sys
ROOT=Path(__file__).resolve().parents[1]
studio=Path(sys.argv[1]).resolve()/'studio';library=json.loads((studio/'library.json').read_text(encoding='utf-8'))
selected=sys.argv[2:]
for name in selected:
    release=library[name];source=(studio/release['folder']).resolve()
    if not source.is_relative_to(studio/'releases'):raise ValueError('来源不属于已发布目录')
    destination=ROOT/'extensions/composable/capabilities'/name.replace('.','_') if name!='movement.here' else ROOT/'extensions/foundation/capabilities/move_here'
    destination.mkdir(parents=True,exist_ok=True);hashes={}
    for file in source.rglob('*'):
        relative=file.relative_to(source)
        if not file.is_file() or relative.parts[0] in ('dependencies','reference','lessons') or relative.name in ('AGENTS.md','MODULE_GUIDE.md','FRONTEND_GUIDE.md','workspace.json','validation.log','test-output.txt') or '__pycache__' in relative.parts:continue
        # 仅保留实际组件及业务测试；制作中的接口探针不进入产品。
        if relative.name=='test_probe.py':continue
        content=file.read_bytes();target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content);hashes[relative.as_posix()]=sha256(content).hexdigest()
    if name!='movement.here':
        manifest=dict(id='capabilities/'+name.replace('.','_'),kind='capabilities',version=release['version'],description=release['manifest'].get('description',''),requires=['capabilities/module_sdk',*['capabilities/'+n.replace('.','_') if n not in ('place.info','tools.collector') else {'place.info':'capabilities/place_info','tools.collector':'capabilities/tool_collector'}[n] for n in release['manifest']['requires']]],nodeModule='.')
        (destination/'component.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    evidence=[]
    for file in (studio/'maker-evidence').glob('*.json'):
        job=json.loads(file.read_text(encoding='utf-8'))
        if job.get('release',{}).get('id')==name:evidence.append(dict(task=job['id'],session=job['session_id'],workspace=job['workspace'],status=job['status'],prefix=job['prefix'],requests=job.get('requests'),repairs=job.get('repairs'),validation=job.get('validation'),source_session=job.get('source_session')))
    provenance=dict(origin='DeepSeek Harness 原生模块／工具制作 Agent',study='已有实现的参考修订' if name=='movement.here' else '从空白生成、宿主审查后修订',release_digest=release['digest'],source_hashes=hashes,evidence=evidence)
    (destination/'制作记录.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(name)
