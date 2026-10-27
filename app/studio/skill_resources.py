"""Validate imported Skill text and declarations without executing it."""
import json
import re
import yaml

def parse_skill(p):
    files=p.get('files')
    if not isinstance(files,dict) or not 1<=len(files)<=128:raise ValueError('Skill 文件数量为1至128')
    total=0
    for name,text in files.items():
        if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/') or any(v in ('','.','..') for v in name.split('/')):raise ValueError('Skill 文件路径无效')
        if not isinstance(text,str):raise ValueError('Skill 资源必须是文本文件')
        total+=len(text.encode('utf-8'))
    if total>2*1024*1024:raise ValueError('Skill 文本总量超过2MiB')
    entry=files.get('SKILL.md','');match=re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)',entry,re.S)
    if not match:raise ValueError('SKILL.md 缺少 YAML 名称和描述')
    front=yaml.safe_load(match.group(1))
    if not isinstance(front,dict):raise ValueError('Skill 元数据必须是对象')
    identity=front.get('name');description=front.get('description')
    if not isinstance(identity,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',identity) or len(identity)>64:raise ValueError('Skill name 必须为小写连字符名称')
    if not isinstance(description,str) or not description.strip() or len(description)>2000:raise ValueError('Skill description 无效')
    manifest=json.loads(files.get('skill.json','{}'))
    if not isinstance(manifest,dict) or manifest.get('format','nexarbor-skill/v1')!='nexarbor-skill/v1' or manifest.get('id',identity)!=identity:raise ValueError('skill.json 与 SKILL.md 的名称不一致')
    metadata=front.get('metadata') or {};extension=metadata.get('nexarbor',{}) if isinstance(metadata,dict) else {}
    requires=manifest.get('requires',extension.get('requires',{}))
    if not isinstance(requires,dict) or set(requires)-{'modules','tools','skills'}:raise ValueError('requires 仅支持 modules/tools/skills')
    dependencies={}
    for kind in ('modules','tools','skills'):
        values=requires.get(kind,[])
        if not isinstance(values,list) or len(values)>64 or any(not isinstance(v,str) or not v or len(v)>300 for v in values):raise ValueError('Skill 依赖必须是字符串列表')
        if kind=='modules' and any(not re.fullmatch(r'[a-z][a-z0-9_.-]*',v) for v in values):raise ValueError('依赖模块ID无效')
        if kind=='skills' and any(not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',v) for v in values):raise ValueError('依赖Skill名称无效')
        dependencies[kind]=list(dict.fromkeys(values))
    title=manifest.get('name',identity)
    if not isinstance(title,str) or not title.strip() or len(title)>160:raise ValueError('Skill 显示名称无效')
    return dict(manifest=dict(format='nexarbor-skill/v1',id=identity,name=title,description=description.strip(),requires=dependencies),content=entry[match.end():].strip(),files={k:v for k,v in files.items() if k not in ('SKILL.md','skill.json')})
