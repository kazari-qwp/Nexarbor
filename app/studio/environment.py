"""制作副本复制实际网络和模块；模型与外部副作用默认禁用。"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
from .service import read_json,write_json,sources

def sanitized(document):
    result=deepcopy(document);files=result.get('files',{});copied={};paths={}
    for index,node in enumerate(result['network']['nodes']):
        if node['type']=='pulse':node.get('parameters',{}).pop('state',None)
        data=node.get('data')
        if not data:continue
        old=data['path'].replace('\\','/').rstrip('/');new=f'data/{index}/'+Path(old).name
        data['path']=new;paths[old]=new
        for name,content in files.items():
            if name==old or name.startswith(old+'/'):copied[new+name[len(old):]]=deepcopy(content)
        if not data.get('directory') and old not in files:copied[new]=''
    for index,(name,content) in enumerate(files.items()):
        if any(name==old or name.startswith(old+'/') for old in paths):continue
        mapped=f'data/documents/{index}/'+Path(name).name;paths[name]=mapped;copied[mapped]=deepcopy(content)
    def relocated(value):
        path=value.replace('\\','/')
        for old,new in sorted(paths.items(),key=lambda item:len(item[0]),reverse=True):
            if path==old or path.startswith(old+'/'):return new+path[len(old):]
        return value
    def rewrite(value):
        if isinstance(value,list):return [rewrite(item) for item in value]
        if isinstance(value,dict):return {key:relocated(item) if isinstance(item,str) and (key in ('file','path','document') or key.endswith('_path')) else rewrite(item) for key,item in value.items()}
        return value
    for node in result['network']['nodes']:
        if 'tables' in node:node['tables']=rewrite(node['tables'])
    result.update(version=1,agents={},signals={},files=copied)
    return result

def prepare(studio,p,*,folder=None,activate=True):
    work=folder or studio.folder(p['id']);metadata=read_json(studio.folder(p['id'])/'workspace.json',{})
    if p.get('source','current')=='candidate':
        from .network_work import validate_network
        document=validate_network(read_json(work/p.get('network_file','network.json'),{}),studio.backend,studio.library)
        document.update(runtime=read_json(work/'runtime.json',{'templates':[]}))
    else:
        scoped=getattr(studio.backend,'network_administrator',None)
        document=scoped.source(p['id']) if scoped and scoped.has(p['id']) else studio.backend.snapshot()
    home=studio.root/'environments'/p['id']/uuid4().hex;home.mkdir(parents=True)
    write_json(home/'initial.json',sanitized(document))
    library={name:studio.root/release['folder'] for name,release in studio.library.items()}
    if metadata.get('kind')!='network':
        from .contract import manifest
        spec=manifest(work);library[spec['id']]=work
    used={item['module_id'] for node in document['network']['nodes'] for item in node.get('tables',{}).get('modules',[])}
    for name,relative in [('tool_discovery','modules/tool_discovery'),('context.assembler','modules/context_assembler')]:
        if name in used and name not in library:library[name]=Path(__file__).resolve().parents[2]/relative
    modules={}
    for name,source in library.items():
        relative='modules/'+name;modules[name]=relative
        for file,content in sources(source).items():
            target=home/relative/file;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
    setup=dict(modules=modules,port_definitions=studio.ports,port_contracts=studio.port_contracts)
    for label in ('node_types','agent_node_types'):
        setup[label]={kind:cls.__module__+':'+cls.__name__ for kind,cls in getattr(studio.backend.saver,label).items()}
    write_json(home/'setup.json',setup)
    if activate:write_json(studio.root/'environments'/p['id']/'current.json',{'home':str(home)})
    return home
