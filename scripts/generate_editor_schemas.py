"""Seed component-owned editor contracts from the current NPC recipe.

Run deliberately when introducing editor metadata, then review the generated
contracts. Runtime never infers validation contracts from untrusted input.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ['DATANET_COMPONENT_ROOT']=str(ROOT/'extensions/editor')
sys.path.insert(0,str(ROOT/'python'))
from datanet.component_catalog import discover

catalog=discover(ROOT/'extensions/editor')
document=json.loads((ROOT/'extensions/npc_world/network_presets/small_town/network.json').read_text('utf-8'))
nodes=document['network']['nodes'];ids={n['node_id'] for n in nodes}
labels={'action.budget':'行动额度','agent.session':'Agent 会话','agent.signal':'信号驱动 Agent','clock.text':'时间文本','context.sources':'上下文来源','checkpoint.counter':'计数存档','event.trigger':'事件触发器','information.provider':'信息提供器','information.collector':'信息收集器','tools.assembly':'工具装配器','input.opening':'初始动机','probability.events':'概率事件','world.resident':'居民身份与状态','world.address':'场所与移动','world.gather':'采集','world.trade':'交易','world.repair':'修理','world.household':'住户与休息','world.marriage':'结婚登记','world.family':'孕育','world.birth':'出生','world.drink':'饮品','world.information':'场所信息','world.knowledge':'身份知识','scene.operator':'场景操作'}
titles={'capacity':'每周期行动值','default_cost':'默认操作成本','costs':'操作成本','channels':'频道','strength':'访问强度','max_requests':'最大模型调用数','actors':'接收 Agent','sources':'来源','kind':'类型','source':'内容来源','target':'目标节点','address':'场所节点','service':'业务节点','manager':'管理 Agent','clock':'时间节点','pulse':'脉冲节点','text':'文本','name':'名称','role':'职业','gender':'性别','place':'当前场所','coins':'金币','inventory':'物品','residents':'住户','operations':'可调用模块方法','rules':'事件规则','graphs':'执行图','duration':'持续时刻数','slots':'时刻名称','format':'格式','probability':'独立概率','max_occurrences':'可触发次数上限','effects':'效果','toolboxes':'工具箱','prompt':'基础提示词','file':'组件内文件','component':'组件','method':'方法','module':'模块','prepare':'执行前准备','when':'匹配条件','state':'状态'}

def infer(value,key=''):
    title=titles.get(key,key)
    if key=='probability':return dict(title=title,type='number',minimum=0,maximum=1)
    if key=='max_occurrences':return dict(title=title,type=['integer','null'],minimum=1)
    if value is None:return {'title':title,'type':['string','number','boolean','object','array','null']}
    if type(value) is bool:return dict(title=title,type='boolean')
    if type(value) in (int,float):return dict(title=title,type='integer' if type(value) is int else 'number')
    if isinstance(value,str):
        result=dict(title=title,type='string')
        if value in ids and key not in ('id','node_id','name','text') and not key.startswith('/'):result['format']='node-id'
        if key in ('text','task','background'):result['format']='textarea'
        if key=='kind' and value in ('system_prompt','context','inputs','tail'):result['enum']=['system_prompt','context','inputs','tail']
        return result
    if isinstance(value,list):
        item=infer(value[0]) if value else {'type':'string'}
        if value and all(isinstance(v,dict) for v in value):
            props={}
            for v in value:
                for k,x in v.items():props.setdefault(k,infer(x,k))
            item=dict(type='object',properties=props,additionalProperties=True)
        return dict(title=title,type='array',items=item)
    return dict(title=title,type='object',properties={k:infer(v,k) for k,v in value.items()},additionalProperties=True)

module_to_owner={}
for key,m in catalog.items():
    for service in m.get('python',{}).get('services',[]):
        path=m['implementation_directory']/m['python'].get('path','python')/Path(*service.split('.')).with_suffix('.py')
        if path.exists():
            import re
            for name in re.findall(r"(?:s|services)\.node_module\(['\"]([^'\"]+)",path.read_text('utf-8')):module_to_owner[name]=key
grouped={}
for n in nodes:
    for name,spec in n['modules'].items():
        owner=module_to_owner[name]
        if name in grouped.get(owner,{}):continue
        schema=infer(spec['config']);state_schema=infer(spec['state'])
        if name=='action.budget':
            schema['properties']['capacity']['minimum']=1
            schema['properties']['costs']['additionalProperties']={'type':'integer','minimum':0}
        if name=='clock.text':schema['required']=['channels','slots','format'];schema['properties']['slots']['minItems']=1
        if name=='agent.session':schema['required']=['prompt'];schema['properties']['prompt']={'title':'基础提示词','oneOf':[{'type':'string'},{'type':'object','properties':{'component':{'type':'string'},'file':{'type':'string'}},'required':['component','file']}]}
        grouped.setdefault(owner,{})[name]=dict(label=labels.get(name,name),schema=schema,stateSchema=state_schema,defaults=deepcopy(spec))
for owner,specs in grouped.items():
    root=catalog[owner]['implementation_directory']
    (root/'editor.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2)+'\n','utf-8')
    path=root/'component.json';m=json.loads(path.read_text('utf-8'));m['editor']={'modules':'editor.json'}
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8')
print('Seeded',sum(map(len,grouped.values())),'module contracts in',len(grouped),'components')
