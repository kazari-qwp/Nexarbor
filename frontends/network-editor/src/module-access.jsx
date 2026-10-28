import React from 'react';
import {ChannelList} from './channel-list.jsx';
export function ModuleAccess({value={},defaultStrength,onChange}){
 return <div className="module-access"><label>模块访问强度<input aria-label="模块访问强度" type="number" min="0" value={value.strength??''} placeholder="装配时使用节点默认强度" onChange={e=>{const next={...value};if(e.target.value!=='')next.strength=Number(e.target.value);else if(defaultStrength!==undefined)next.strength=defaultStrength;else delete next.strength;onChange(next);}}/></label><ChannelList label="模块访问频道" value={value.channels??[]} mode={value.channel_mode??'allow'} onChange={channels=>onChange({...value,channels})} onMode={channel_mode=>onChange({...value,channel_mode})}/></div>;
}
