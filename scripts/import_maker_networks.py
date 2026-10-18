"""将完成验证的网络制作副本保存为随项目发布的真实配置。"""
import json,shutil
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1];studio=ROOT/'build/network-maker-apps/studio'
for work,name,title in [('module-4bbafa8544','fixed_groups_v3','固定讨论组与去中心化协作组'),('module-dff5444b25','knowledge_v3','知识归档与恢复'),('module-de777cb7e6','sensor_window_v3','委托制作滑动窗口示例')]:
    folder=ROOT/'configs'/name;folder.mkdir(exist_ok=True)
    for file in ['network.json','README.md']:shutil.copyfile(studio/'work'/work/file,folder/file)
    profile=dict(name=title,network='network.json',components=[],runtime_directory='../../build/'+name)
    (folder/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    jobs=[json.loads(f.read_text(encoding='utf-8')) for f in (studio/'maker-evidence').glob('*.json')]
    evidence=[{k:j.get(k) for k in ['id','workspace','session_id','source_session','status','requests','steps','validation','children']} for j in jobs if j['workspace']==work]
    provenance=dict(origin='DeepSeek Harness 网络预设制作 Agent',study='从需求生成、宿主执行检查后参考修订',evidence=evidence,sha256=sha256((folder/'network.json').read_bytes()).hexdigest())
    (folder/'制作记录.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(name)
