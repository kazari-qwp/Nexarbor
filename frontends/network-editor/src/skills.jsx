import React,{useState} from 'react';
import {BookOpen,Plus} from 'lucide-react';
import {RichText} from './message-content.jsx';
import {ResourceBadges} from './resource-badges.jsx';
import {ResourceActions} from './resource-actions.jsx';
import {resourceAvailable} from './resources.js';

export function SkillContent({id,api}){
 const [value,setValue]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const load=async()=>{if(value||loading)return;setLoading(true);try{setValue(await api('skills.read',{id}));setError('');}catch(e){setError(e.message);}finally{setLoading(false);}};
 return <details className="skill-content" onToggle={e=>{if(e.currentTarget===e.target&&e.currentTarget.open)load();}}><summary>Skill 说明与参考目录</summary>{loading&&<p role="status">正在读取 Skill…</p>}{error&&<p role="alert" className="notice">{error}<button onClick={load}>重试</button></p>}{value&&<><RichText text={value.content} api={api}/><details><summary>参考文件 · {value.files.length}</summary><ul>{value.files.map(file=><li key={file}>{file}</li>)}</ul></details></>}</details>;
}
export function NodeSkills({node,catalog,organization,api,onMount,onRemove,onSave,onNavigate}){
 const [selected,setSelected]=useState('');
 return <section className="node-skills" aria-label="Agent Skills"><p className="muted">仅此 Agent 使用这些 Skills。装配时递归安装依赖，模型按需读取说明和参考；移除 Skill 会保留已装依赖。</p><div className="module-add"><select aria-label="选择 Skill" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">装配一个 Skill…</option>{Object.entries(catalog.skills??{}).filter(([id,s])=>s.available!==false&&!node.skills?.includes(id)&&resourceAvailable(catalog,organization,'skill',id)).map(([id,s])=><option key={id} value={id}>{s.name} · {id}</option>)}</select><button disabled={!selected} title="装配 Skill" onClick={()=>{onMount(selected);setSelected('');}}><Plus size={16}/></button></div>{(node.skills??[]).map(id=>{const spec=catalog.skills?.[id],value={name:spec?.name??id,asset:{kind:'skill',id}};return <article className="module-section skill-section" data-mounted-kind="skill" data-mounted-id={id} key={id}><header title={spec?.description??'项目缺少此 Skill'}><BookOpen size={14}/><span>{value.name}<small>{id}</small></span><ResourceBadges value={value} catalog={catalog} onNavigate={target=>onNavigate(target,{kind:'skill',id})}/><ResourceActions label={'Skill '+id} onSave={()=>onSave(id)} onDelete={()=>onRemove(id)}/></header><p className={spec?.available===false||!spec?'notice':'muted'}>{spec?.description??'项目缺少此 Skill，请将文件夹放回项目 skills 目录。'}</p>{spec?.local===false&&<button onClick={()=>onMount(id)}>下载 Skill 及依赖</button>}{spec?.available!==false&&spec&&<SkillContent id={id} api={api}/>}</article>;})}{!node.skills?.length&&<p className="muted">此 Agent 尚未装配 Skill，也可以从左栏或书签拖入。</p>}</section>;
}
