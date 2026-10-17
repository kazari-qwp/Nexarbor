import React from 'react';
import {Plus,X,ChevronDown} from 'lucide-react';
export function ValueEditor({value,onChange,label,depth=0}){
  const type=value===null?'null':Array.isArray(value)?'array':typeof value;
  const make=t=>({string:'',number:0,boolean:false,object:{},array:[],null:null,reference:{$ref:'/event/payload/'}}[t]);
  return <div className={'value-field depth-'+depth}>
    <div className="value-head">{label&&<label>{label}</label>}<select aria-label={`${label??'值'}类型`} value={type} onChange={e=>onChange(make(e.target.value))}>{['string','number','boolean','object','array','null','reference'].map(t=><option key={t}>{t}</option>)}</select></div>
    {type==='string'?<textarea aria-label={label} rows={value.includes('\n')?4:1} value={value} onChange={e=>onChange(e.target.value)}/>:
      type==='number'?<input aria-label={label} type="number" value={value} onChange={e=>onChange(Number(e.target.value))}/>:
      type==='boolean'?<input aria-label={label} type="checkbox" checked={value} onChange={e=>onChange(e.target.checked)}/>:
      type==='null'?<span className="muted">空值</span>:
      type==='array'?<><div className="nested-fields">{value.map((v,i)=><div key={i} className="field-row"><ValueEditor label={String(i+1)} value={v} onChange={x=>onChange(value.map((old,j)=>i===j?x:old))} depth={depth+1}/><button title="删除项" onClick={()=>onChange(value.filter((_,j)=>j!==i))}><X size={13}/></button></div>)}</div><button className="text-button" onClick={()=>onChange([...value,''])}><Plus size={13}/>添加一项</button></>:
      <><div className="nested-fields">{Object.entries(value).map(([k,v])=><div key={k} className="field-row"><ValueEditor label={k} value={v} onChange={x=>onChange({...value,[k]:x})} depth={depth+1}/><button title="删除字段" onClick={()=>{const next={...value};delete next[k];onChange(next);}}><X size={13}/></button></div>)}</div><button className="text-button" onClick={()=>{const key=prompt('新字段名称');if(key&&!(key in value))onChange({...value,[key]:''});}}><Plus size={13}/>添加字段</button></>}
  </div>;
}
export function GraphEditor({value,onChange,operations}){
  const type=value.type??'call';const seed=t=>t==='call'?{type:t,id:'step-'+Math.random().toString(36).slice(2,7),operation:Object.keys(operations)[0]??'',arguments:{}}:t==='branch'?{type:t,select:{$ref:'/results/'},cases:{},default:{type:'sequence',steps:[]}}:{type:t,steps:[]};
  return <div className="graph-block">
    <select aria-label="执行块类型" value={type} onChange={e=>onChange(seed(e.target.value))}><option value="call">调用模块</option><option value="sequence">顺序</option><option value="parallel">并行 · 完成后汇合</option><option value="branch">按结果分支</option></select>
    {type==='call'?<><label>步骤编号<input value={value.id??''} onChange={e=>onChange({...value,id:e.target.value})}/></label><label>调用<select value={value.operation??''} onChange={e=>onChange({...value,operation:e.target.value})}><option value="">选择操作</option>{Object.keys(operations).map(k=><option key={k}>{k}</option>)}</select></label><ValueEditor label="参数" value={value.arguments??{}} onChange={arguments_=>onChange({...value,arguments:arguments_})}/></>:
    type==='branch'?<><ValueEditor label="分支依据（支持 $ref）" value={value.select} onChange={select=>onChange({...value,select})}/>{Object.entries(value.cases??{}).map(([key,child])=><details key={key} open><summary>结果：{key}</summary><GraphEditor value={child} operations={operations} onChange={v=>onChange({...value,cases:{...value.cases,[key]:v}})}/><button onClick={()=>{const cases={...value.cases};delete cases[key];onChange({...value,cases});}}>删除分支</button></details>)}<button onClick={()=>{const key=prompt('匹配结果');if(key)onChange({...value,cases:{...value.cases,[key]:seed('call')}});}}>添加分支</button><details><summary>默认分支</summary><GraphEditor value={value.default??seed('sequence')} operations={operations} onChange={v=>onChange({...value,default:v})}/></details></>:
    <>{(value.steps??[]).map((step,i)=><div key={i} className="graph-step"><div className="step-heading"><span>{type==='parallel'?'并行分支':'步骤'} {i+1}</span><button title="上移" disabled={!i} onClick={()=>{const steps=[...value.steps];[steps[i],steps[i-1]]=[steps[i-1],steps[i]];onChange({...value,steps});}}>↑</button><button title="删除步骤" onClick={()=>onChange({...value,steps:value.steps.filter((_,j)=>i!==j)})}><X size={12}/></button></div><GraphEditor value={step} operations={operations} onChange={v=>onChange({...value,steps:value.steps.map((x,j)=>i===j?v:x)})}/></div>)}<button className="text-button" onClick={()=>onChange({...value,steps:[...(value.steps??[]),seed('call')]})}><Plus size={13}/>添加步骤</button></>}
  </div>;
}
