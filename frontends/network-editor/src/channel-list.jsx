import React from 'react';
import {Plus,X} from 'lucide-react';
import './channel-list.css';
export function ChannelList({label='频道',value=[],mode='allow',onChange,onMode,disabled=false}){
 return <fieldset className="channel-list" disabled={disabled}><legend>{label}</legend>{onMode&&<select aria-label={label+'匹配模式'} value={mode} onChange={e=>onMode(e.target.value)}><option value="allow">白名单 · 仅匹配这些频道</option><option value="deny">黑名单 · 排除这些频道</option></select>}<div>{value.map((channel,index)=><div className="channel-item" key={index}><input aria-label={label+' '+(index+1)} value={channel} onChange={e=>onChange(value.map((old,i)=>i===index?e.target.value:old))}/><button type="button" aria-label={'删除'+label+' '+(index+1)} onClick={()=>onChange(value.filter((_,i)=>i!==index))}><X size={13}/></button></div>)}</div><button type="button" className="channel-add" onClick={()=>onChange([...value,''])}><Plus size={14}/>添加频道</button><small>{onMode?(mode==='deny'?'空黑名单不限制频道':'空白名单不匹配任何频道'):'发出信号的明确频道标签'}</small></fieldset>;
}
export const channelMatches=(items,candidates,mode='allow')=>candidates.some(c=>(items.includes(c))===(mode==='allow'));
