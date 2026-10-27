import React from 'react';
import {BookmarkPlus,Trash2} from 'lucide-react';
export function ResourceActions({label,onSave,onDelete}){
 return <span className="resource-inline-actions">{[[BookmarkPlus,'保存'+label+'至书签',onSave],[Trash2,'删除'+label,onDelete]].map(([Icon,name,fn],i)=><button key={name} className={i?'remove-resource':''} title={i?'从当前节点移除':'保存当前配置至书签'} aria-label={name} onClick={e=>{e.preventDefault();e.stopPropagation();fn();}}><Icon size={13}/></button>)}</span>;
}
