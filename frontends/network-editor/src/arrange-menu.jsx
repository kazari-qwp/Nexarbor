import React,{useId,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {LayoutGrid,ChevronDown} from 'lucide-react';
import './arrange-menu.css';
export function ArrangeMenu({busy,dragging,visibleCount,selectedCount,onArrange}){
 const [open,setOpen]=useState(false),[dense,setDense]=useState(false);
 const trigger=useRef(),popup=useRef(),id=useId();
 const [position,setPosition]=useState({left:8,top:8});
 useLayoutEffect(()=>{
  if(!open)return;
  const menu=popup.current,button=trigger.current;
  const fit=()=>{
   const anchor=button.getBoundingClientRect(),box=menu.getBoundingClientRect();
   const left=Math.max(8,Math.min(anchor.right-box.width,window.innerWidth-box.width-8));
   const below=anchor.bottom+7,top=below+box.height<=window.innerHeight-8?below:Math.max(8,anchor.top-box.height-7);
   setPosition({left,top});
  };
  const outside=event=>{if(!menu.contains(event.target)&&!button.contains(event.target))setOpen(false);};
  const escape=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false);button.focus({preventScroll:true});}};
  const scroll=event=>{if(!menu.contains(event.target))setOpen(false);};
  fit();menu.querySelector('[role=tab][aria-selected=true]')?.focus({preventScroll:true});
  window.addEventListener('pointerdown',outside,true);window.addEventListener('keydown',escape,true);
  window.addEventListener('resize',fit);window.addEventListener('scroll',scroll,true);
  return()=>{window.removeEventListener('pointerdown',outside,true);window.removeEventListener('keydown',escape,true);window.removeEventListener('resize',fit);window.removeEventListener('scroll',scroll,true);};
 },[open]);
 return <div className="arrange-menu">
  <button ref={trigger} aria-expanded={open} aria-controls={open?id:undefined} aria-haspopup="dialog" disabled={busy||dragging} onClick={()=>setOpen(v=>!v)}><LayoutGrid size={14}/>{busy?'整理中…':'整理'}<ChevronDown size={12}/></button>
  {open&&createPortal(<section ref={popup} id={id} className="arrange-popover" role="dialog" aria-label="整理选项" style={position}>
   <div role="tablist" aria-label="整理方式" onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?false:event.key==='End'?true:!dense;setDense(next);popup.current.querySelectorAll('[role=tab]')[Number(next)]?.focus();}}>{[[false,'层级整理'],[true,'稠密整理']].map(([value,label])=><button key={label} role="tab" tabIndex={dense===value?0:-1} aria-selected={dense===value} onClick={()=>setDense(value)}>{label}</button>)}</div>
   <p>{dense?'紧凑排布相邻节点，平衡画布长宽。':'按连接方向分层排列，保留现有整理方式。'}</p>
   <button className="arrange-visible" disabled={!visibleCount} onClick={()=>{setOpen(false);onArrange('visible',dense);}}>整理当前视图</button>
   <button disabled={!selectedCount} onClick={()=>{setOpen(false);onArrange('selected',dense);}}>整理选中（{selectedCount}）</button>
  </section>,document.body)}
 </div>;
}
