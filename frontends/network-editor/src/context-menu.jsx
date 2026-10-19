import React,{useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import './context-menu.css';

// 挂到 body，避免侧栏的尺寸、滚动与层叠样式影响浮动菜单。
export function ContextMenu({x,y,label,onClose,className='',children}){
 const px=Number.isFinite(x)?x:8,py=Number.isFinite(y)?y:8;
 const ref=useRef(),[position,setPosition]=useState({left:px,top:py});
 useLayoutEffect(()=>{
  const menu=ref.current,fit=()=>{const box=menu.getBoundingClientRect();setPosition({left:Math.max(8,Math.min(px,window.innerWidth-box.width-8)),top:Math.max(8,Math.min(py,window.innerHeight-box.height-8))});};fit();
  menu.querySelector('[role=menuitem]:not(:disabled)')?.focus({preventScroll:true});
  const outside=event=>{if(!menu.contains(event.target))onClose();},escape=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose();}},scroll=event=>{if(!menu.contains(event.target))onClose();};
  window.addEventListener('pointerdown',outside,true);window.addEventListener('keydown',escape,true);window.addEventListener('resize',fit);window.addEventListener('wheel',scroll,true);
  return()=>{window.removeEventListener('pointerdown',outside,true);window.removeEventListener('keydown',escape,true);window.removeEventListener('resize',fit);window.removeEventListener('wheel',scroll,true);};
 },[x,y]);
 return createPortal(<div ref={ref} className={'resource-context-menu compact-context-menu '+className} role="menu" aria-label={label} style={position} onContextMenu={e=>{e.preventDefault();e.stopPropagation();}} onKeyDown={event=>{
  event.stopPropagation();if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;event.preventDefault();const items=[...ref.current.querySelectorAll('[role=menuitem]:not(:disabled)')],index=items.indexOf(document.activeElement);const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next]?.focus();
 }}>{children}</div>,document.body);
}
