import React from 'react';
import {Box,Wrench} from 'lucide-react';
import {resourceRelations} from './resources.js';
export function ResourceBadges({value,catalog,onOpen}){
 const relations=resourceRelations(value,catalog);
 return <span className="resource-badges">{[[Wrench,'tools','携带工具'],[Box,'modules','依赖模块']].map(([Icon,key,label])=><button key={key} aria-label={value.name+'的'+label+'，'+relations[key].length+' 个'} title={label+'：'+relations[key].length} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.preventDefault();e.stopPropagation();onOpen({...value,relationsFocus:key});}}><Icon size={11}/><span>{relations[key].length}</span></button>)}</span>;
}
export function ResourceRelations({value,catalog}){
 const relations=resourceRelations(value,catalog);
 return <div className="resource-relations">{[['modules','依赖模块'],['tools','携带工具']].map(([key,label])=><details key={key} open={value.relationsFocus===key}><summary>{label} · {relations[key].length}</summary>{relations[key].length?relations[key].map(id=><p key={id}>{key==='modules'?(catalog.modules[id]?.label??id):(catalog.tools.find(t=>t.ref===id)?.name??id)}<small>{id}</small></p>):<p className="muted">无{label}</p>}</details>)}</div>;
}
