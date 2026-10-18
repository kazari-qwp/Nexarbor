import React from 'react';
import {FileCode,Folder} from 'lucide-react';

function tree(names){
 const root={children:new Map()};
 for(const path of names){let node=root;const parts=path.split('/');parts.forEach((name,index)=>{if(!node.children.has(name))node.children.set(name,{name,path:parts.slice(0,index+1).join('/'),children:new Map()});node=node.children.get(name);if(index===parts.length-1)node.file=true;});}
 return root;
}
export function FileList({names,selected,changed,onSelect}){
 const render=node=>[...node.children.values()].sort((a,b)=>Number(!!a.file)-Number(!!b.file)||a.name.localeCompare(b.name)).map(item=>item.file?
  <button key={item.path} title={item.path} aria-label={'打开文件 '+item.path} className={selected===item.path?'active':''} onClick={()=>onSelect(item.path)}><FileCode size={13}/><span>{item.name}{selected===item.path&&changed?' *':''}</span></button>:
  <details key={item.path} open={selected.startsWith(item.path+'/')||undefined}><summary title={item.path}><Folder size={13}/><span>{item.name}</span></summary><div>{render(item)}</div></details>);
 return <div className="studio-file-tree">{render(tree(names))}</div>;
}
