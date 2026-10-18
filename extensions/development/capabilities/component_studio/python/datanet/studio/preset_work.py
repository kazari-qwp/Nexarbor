"""现有组件的配置方案也是合法制作结果，不为配置差异复制实现。"""
import json
from pathlib import Path
from jsonschema import Draft202012Validator
SCHEMA={'type':'object','properties':{'format':{'const':'nexarbor-component-presets/v1'},'presets':{'type':'array','minItems':1,'maxItems':20,'items':{'type':'object','properties':{'module':{'type':'string'},'name':{'type':'string','minLength':1,'maxLength':160},'description':{'type':'string','maxLength':4000},'config':{'type':'object'}},'required':['module','name','description','config'],'additionalProperties':False}}},'required':['format','presets'],'additionalProperties':False}
def check(folder,library):
    value=json.loads((Path(folder)/'presets.json').read_text(encoding='utf-8'));Draft202012Validator(SCHEMA).validate(value)
    for preset in value['presets']:
        if preset['module'] not in library:raise ValueError('配置方案只能引用已发布组件：'+preset['module'])
        Draft202012Validator(library[preset['module']]['manifest']['config_schema']).validate(preset['config'])
    return value
