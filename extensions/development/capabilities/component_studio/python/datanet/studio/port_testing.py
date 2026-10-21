"""Validate deterministic doubles against the host's real published result contracts."""
from pathlib import Path
import inspect,json,os
from jsonschema import Draft202012Validator

def environment_contracts():
    home=os.environ.get('DATANET_TEST_ENVIRONMENT')
    return json.loads((Path(home)/'setup.json').read_text('utf-8')).get('port_contracts',{}) if home else {}

def checked_executor(provider,definitions,execute,contracts):
    known={provider+':'+definition['name']:contracts[provider+':'+definition['name']] for definition in definitions if provider+':'+definition['name'] in contracts}
    async def checked(actor,name,args):
        value=execute(actor,name,args)
        if inspect.isawaitable(value):value=await value
        ref=provider+':'+name;contract=known.get(ref)
        if contract:
            if contract['format']!='harness-tool-result/v1':raise ValueError('未知端口测试返回契约：'+ref)
            if not isinstance(value,dict) or type(value.get('isError')) is not bool or not isinstance(value.get('content'),list):
                raise ValueError('端口 '+ref+' 的替身须返回真实 isError/content/value envelope；按需查 catalog_ports 精确 ref 的 result_contract')
            if not value['isError']:
                if 'value' not in value:raise ValueError('成功端口替身缺少 value：'+ref)
                error=next(Draft202012Validator(contract['value_schema']).iter_errors(value['value']),None)
                if error:
                    path='/value'+''.join('/'+str(part) for part in error.absolute_path)
                    raise ValueError('端口 '+ref+' 的替身不符合真实返回契约：'+path+' ('+str(error.validator)+')；查 catalog_ports 精确 ref 的 result_contract')
        return value
    return checked
