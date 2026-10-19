import React from 'react';
export function ModuleAccess({value,onChange,nodeStrength}){
 const inherited=value?.strength==null;
 return <div className="module-access"><label><input type="checkbox" aria-label="继承节点默认强度" checked={inherited} onChange={e=>onChange({...value,strength:e.target.checked?null:nodeStrength??0})}/> 使用节点默认强度{nodeStrength!=null?'（'+nodeStrength+'）':'（装配时继承）'}</label><label>模块访问强度<input aria-label="模块访问强度" type="number" min="0" disabled={inherited} value={inherited?nodeStrength??'':value.strength} onChange={e=>onChange({...value,strength:Number(e.target.value)})}/></label><p className="muted">显式强度可以超过节点默认值；模块发起的访问、信号和锁定仍由框架按此授权检查。</p><label>授权频道<input aria-label="模块授权频道" value={(value?.channels??[]).join(', ')} onChange={e=>onChange({...value,channels:e.target.value.split(',').map(v=>v.trim()).filter(Boolean)})}/></label></div>;
}
