"""统一检索请求：范围由网络决定，节点只解释检索方法。"""
from copy import deepcopy

def validate_request(request):
    if not isinstance(request, dict):
        raise TypeError('读取请求必须是字典')
    method = request.get('method')
    if not isinstance(method, str) or method not in ('key', 'filter', 'semantic'):
        raise ValueError('method 必须为 key、filter 或 semantic')
    required = {'key': {'method', 'key'}, 'filter': {'method', 'filters'}, 'semantic': {'method', 'query'}}[method]
    allowed = required | ({'top_k'} if method == 'semantic' else set())
    if required - request.keys() or request.keys() - allowed:
        raise ValueError('读取请求缺少必填字段或包含无关字段')
    if method == 'key' and (not isinstance(request['key'], str)):
        raise TypeError('key 必须为字符串')
    if method == 'filter' and (not isinstance(request['filters'], dict)):
        raise TypeError('filters 必须为字典')
    if method == 'semantic':
        if not isinstance(request['query'], str) or not request['query'].strip():
            raise TypeError('query 必须为非空字符串')
        if type(request.get('top_k', 5)) is not int or request.get('top_k', 5) < 1:
            raise ValueError('top_k 必须为正整数')
    return deepcopy(request)

def request_schema():
    return {'type': 'object', 'properties': {'method': {'type': 'string', 'enum': ['key', 'filter', 'semantic']}, 'key': {'type': 'string'}, 'filters': {'type': 'object'}, 'query': {'type': 'string'}, 'top_k': {'type': 'integer'}}, 'required': ['method'], 'additionalProperties': False, 'description': 'key 方法必须提供 key；filter 方法必须提供 filters；semantic 必须提供 query，可选 top_k。不得混用字段。'}
