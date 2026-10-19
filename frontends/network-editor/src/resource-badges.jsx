import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Box,Wrench,X,ArrowRight} from 'lucide-react';
import {resourceRelations,relatedEntries} from './resources.js';
const labels={tools:'携带工具',modules:'依赖模块'};
function RelationItems({value,catalog,relation,onNavigate}){
 const entries=relatedEntries(value,catalog,relation);
 return entries.length?entries.map(entry=>{const Icon=entry.kind==='module'?Box:Wrench;return <button key={entry.id} className="resource-relation-link" disabled={entry.missing} data-relation-kind={entry.kind} data-relation-id={entry.id} aria-label={'转到'+(entry.kind==='module'?'模块 ':'工具 ')+entry.name} title={entry.name+'：'+(entry.missing?'该资源已不在目录中':entry.description||'暂无描述')} onClick={e=>{e.preventDefault();e.stopPropagation();onNavigate(entry,value);}}><Icon size={13}/><span>{entry.name}<small>{entry.id}{entry.missing?' · 资源缺失':''}</small></span><ArrowRight size={12}/></button>;}):<p className="muted">无{labels[relation]}</p>;
}
export function ResourceBadges({value,catalog,onNavigate}){
 const relations=resourceRelations(value,catalog),[popup,setPopup]=useState(null),[position,setPosition]=useState({left:0,top:0}),menu=useRef(),trigger=useRef();
 useLayoutEffect(()=>{
  if(!popup||!menu.current)return;
  const place=()=>{const rect=popup.anchor.getBoundingClientRect(),height=menu.current.offsetHeight,width=menu.current.offsetWidth,left=Math.max(8,Math.min(rect.left,window.innerWidth-width-8)),top=Math.max(8,Math.min(rect.bottom+5,window.innerHeight-height-8));setPosition(old=>old.left===left&&old.top===top?old:{left,top});};
  place();menu.current.querySelector('button.resource-relation-link:not(:disabled)')?.focus({preventScroll:true});
  const observer=new ResizeObserver(place);observer.observe(menu.current);document.addEventListener('scroll',place,true);window.addEventListener('resize',place);
  return()=>{observer.disconnect();document.removeEventListener('scroll',place,true);window.removeEventListener('resize',place);};
 },[popup]);
 useEffect(()=>{if(!popup)return;const outside=e=>{if(!menu.current?.contains(e.target)&&!trigger.current?.contains(e.target))setPopup(null);},key=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setPopup(null);popup.anchor.focus({preventScroll:true});}};document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',key,true);return()=>{document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',key,true);};},[popup]);
 return <span className="resource-badges" ref={trigger}>{[[Wrench,'tools'],[Box,'modules']].map(([Icon,key])=><button key={key} aria-label={value.name+'的'+labels[key]+'，'+relations[key].length+' 个'} aria-expanded={popup?.key===key} aria-haspopup="dialog" title={labels[key]+'：'+relations[key].length} onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.preventDefault();e.stopPropagation();const anchor=e.currentTarget;setPopup(p=>p?.key===key?null:{key,anchor});}}><Icon size={11}/><span>{relations[key].length}</span></button>)}
 {popup&&createPortal(<div ref={menu} className="resource-dependency-popup" style={position} role="dialog" aria-label={labels[popup.key]+'列表'} onClick={e=>e.stopPropagation()} onPointerDown={e=>e.stopPropagation()}><header><span>{value.name} · {labels[popup.key]}</span><button aria-label="关闭依赖列表" onClick={()=>{setPopup(null);popup.anchor.focus({preventScroll:true});}}><X size={13}/></button></header><div className="resource-dependency-items"><RelationItems value={value} catalog={catalog} relation={popup.key} onNavigate={(entry,source)=>{setPopup(null);onNavigate?.(entry,source);}}/></div></div>,document.body)}
 </span>;
}
export function ResourceRelations({value,catalog,onNavigate}){
 const relations=resourceRelations(value,catalog);
 return <div className="resource-relations">{[['modules','依赖模块'],['tools','携带工具']].map(([key,label])=><details key={key} open={value.relationsFocus===key}><summary>{label} · {relations[key].length}</summary><RelationItems value={value} catalog={catalog} relation={key} onNavigate={onNavigate}/></details>)}</div>;
}
