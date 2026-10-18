"""同节点依赖装配：先展开、检查，已有实例保持原配置。"""
from copy import deepcopy

def assemble(node,library,registered=()):
    result=deepcopy(node.get('modules',{}));visiting=set();done=set()
    def visit(name):
        if name in visiting:raise ValueError('模块装配依赖成环：'+name)
        if name in done:return
        if name not in library:
            # 宿主登记的官方能力由核心校验，不伪装成工作室发布版本。
            if name in registered:done.add(name);return
            raise ValueError('缺少已发布依赖模块：'+name)
        spec=library[name]['manifest']
        if node['type'] not in spec['node_types']:raise ValueError('依赖模块不支持该节点类型：'+name)
        visiting.add(name)
        for dependency in spec['requires']:
            if dependency not in result:
                defaults=library.get(dependency,{}).get('mount_defaults',{})
                result[dependency]=deepcopy(dict(config=defaults.get('config',{}),state=defaults.get('state',{}),access=defaults.get('access',dict(strength=0,channels=[]))))
            visit(dependency)
        visiting.remove(name);done.add(name)
    for name in list(result):visit(name)
    return result

def assemble_document(document,library,registered=()):
    result=deepcopy(document)
    for node in result['network']['nodes']:node['modules']=assemble(node,library,registered)
    return result
