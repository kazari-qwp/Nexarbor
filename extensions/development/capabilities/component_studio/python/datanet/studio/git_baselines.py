"""真实 Git 对象保存工作分支基线；相同源码只存一份 blob。"""
from hashlib import sha1,sha256
from pathlib import Path
import json,os,subprocess,zlib

def command(studio,args,data=b''):
    root=studio.root/'history.git'
    env=dict(os.environ,GIT_AUTHOR_NAME='Nexarbor',GIT_AUTHOR_EMAIL='local@nexarbor.invalid',GIT_COMMITTER_NAME='Nexarbor',GIT_COMMITTER_EMAIL='local@nexarbor.invalid')
    normal=lambda value:str(value)[4:] if str(value).startswith(chr(92)*2+'?'+chr(92)) else str(value)
    result=subprocess.run(['git','--git-dir='+normal(root),*[normal(a) for a in args]],input=data,capture_output=True,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError(result.stderr.decode('utf-8',errors='replace'))
    return result.stdout

def save(studio,id,files):
    root=studio.root/'history.git'
    if not (root/'HEAD').exists():command(studio,['init','--bare','--object-format=sha1',str(root)])
    entries=[]
    for name,text in sorted(files.items()):
        payload=json.dumps(dict(name=name,text=text),ensure_ascii=False,sort_keys=True).encode();raw=b'blob '+str(len(payload)).encode()+b'\0'+payload;oid=sha1(raw).hexdigest();folder=root/'objects'/oid[:2];folder.mkdir(parents=True,exist_ok=True)
        try:
            with (folder/oid[2:]).open('xb') as f:f.write(zlib.compress(raw))
        except FileExistsError:pass
        entries.append('100644 blob '+oid+'\t'+sha256(name.encode()).hexdigest()+'.json\n')
    tree=command(studio,['mktree'],''.join(entries).encode()).decode().strip();ref='refs/heads/baseline-'+id
    commit=command(studio,['commit-tree',tree],b'Work branch baseline\n').decode().strip();command(studio,['update-ref',ref,commit]);return dict(git_commit=commit)

def read(studio,value):
    if not isinstance(value,dict) or set(value)!={'git_commit'}:return value
    commit=value['git_commit']
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('基线提交无效')
    entries=command(studio,['ls-tree','-z',commit]).split(b'\0');ids=[row.split(b'\t')[0].split()[2] for row in entries if row];data=command(studio,['cat-file','--batch'],b'\n'.join(ids)+b'\n');result={};offset=0
    for _ in ids:
        end=data.index(b'\n',offset);size=int(data[offset:end].split()[2]);item=json.loads(data[end+1:end+1+size]);result[item['name']]=item['text'];offset=end+size+2
    return result
