import React from 'react';
import {ChannelList} from './channel-list.jsx';
export function ModuleAccess({value={},onChange}){
 return <div className="module-access"><label>模块访问强度<input aria-label="模块访问强度" type="number" min="0" value={value.strength??''} placeholder="模块默认值" onChange={e=>onChange({...value,strength:Number(e.target.value)})}/></label><ChannelList label="模块访问频道" value={value.channels??[]} mode={value.channel_mode??'allow'} onChange={channels=>onChange({...value,channels})} onMode={channel_mode=>onChange({...value,channel_mode})}/></div>;
}
