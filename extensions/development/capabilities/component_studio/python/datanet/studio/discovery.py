"""Small discovery receipts; expand a directory or exact interface on demand."""
from pathlib import PurePosixPath
import json


def page(args,maximum):
    offset=args.get('offset',0);limit=args.get('limit',maximum)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=maximum:
        raise ValueError('分页参数无效')
    return offset,limit


def list_files(data,args):
    path=args.get('path','').replace('\\','/').strip('/')
    if path and (':' in path or '..' in PurePosixPath(path).parts):raise ValueError('请使用工作副本内相对目录')
    prefix=path+'/' if path else '';entries={}
    for category in ('files','references'):
        for name in data[category]:
            if not name.startswith(prefix):continue
            tail=name[len(prefix):];part,sep,_=tail.partition('/')
            key=prefix+part+('/' if sep else '')
            entries.setdefault(key,dict(path=key,kind='directory' if sep else 'file',readonly=category=='references',count=0))['count']+=1
    offset,limit=page(args,100);rows=sorted(entries.values(),key=lambda row:row['path'])
    return dict(path=path,entries=rows[offset:offset+limit],total=len(rows),next_offset=offset+limit if offset+limit<len(rows) else None,
                hint='目录用 list_files(path=目录) 展开；文件路径原样传 read_file。参考正文也可通过所属 Skill 按需读取。')


def catalog_modules(library,args,hidden=()):
    query=args.get('query','').lower();rows=[]
    for id,release in library.items():
        spec=release['manifest']
        if id in hidden or query and query not in json.dumps(spec,ensure_ascii=False).lower():continue
        row=dict(id=id,name=release['name'],description=spec.get('description',''),operations=[op['name'] for op in spec['operations']])
        row['available']=release.get('available',True)
        if not row['available']:row['unavailable_reason']=str(release.get('unavailableReason') or '当前项目未提供此组件')[:240]
        if args.get('details') or query==id.lower():
            row.update(node_types=spec['node_types'],requires=spec['requires'],operations=spec['operations'],
                agent_tools=spec.get('agent_tools',[]),defaults=release.get('mount_defaults',{}),frontend=bool(spec.get('frontend')),
                config_schema=spec['config_schema'],state_schema=spec['state_schema'])
        rows.append(row)
    offset,limit=page(args,30)
    return dict(modules=rows[offset:offset+limit],total=len(rows),next_offset=offset+limit if offset+limit<len(rows) else None,
                hint='query=精确模块 ID 展开接口；源码和说明用 read_resource。公开组件尚未安装时可用 install_module，再按安装结果装配。')
