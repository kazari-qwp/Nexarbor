import React,{useRef} from 'react';

export function SidebarResizer({side,onCommit,note}){
 const drag=useRef(),label=side==='left'?'左':'右',property='--saved-'+side+'-width';
 const bounds=element=>{const app=element.parentElement,other=app.querySelector(side==='left'?'.right-panel':'.left-panel').getBoundingClientRect().width,min=side==='left'?160:220;return {app,min,max:Math.max(min,Math.min(app.clientWidth-other-240,app.clientWidth/2-120))};};
 const apply=(active,width)=>{active.width=Math.round(Math.max(active.min,Math.min(active.max,width)));active.app.style.setProperty(property,active.width+'px');};
 const finish=(event,cancel=false)=>{
  const active=drag.current;if(!active||active.pointer!==event.pointerId)return;drag.current=null;
  active.app.classList.remove('resizing-sidebar');event.currentTarget.releasePointerCapture(event.pointerId);
  if(cancel){active.original?active.app.style.setProperty(property,active.original):active.app.style.removeProperty(property);return;}
  onCommit(active.width).catch(note);
 };
 return <div className={'sidebar-resizer '+side} role="separator" tabIndex={0} aria-label={'调整'+label+'侧栏宽度'} aria-orientation="vertical" title={'拖动调整'+label+'侧栏宽度'} onPointerDown={event=>{
  if(event.button!==0)return;event.preventDefault();const limits=bounds(event.currentTarget),width=limits.app.querySelector('.'+side+'-panel').getBoundingClientRect().width;
  drag.current={...limits,pointer:event.pointerId,x:event.clientX,start:width,width,original:limits.app.style.getPropertyValue(property)};limits.app.classList.add('resizing-sidebar');event.currentTarget.setPointerCapture(event.pointerId);
 }} onPointerMove={event=>{const active=drag.current;if(active?.pointer===event.pointerId)apply(active,active.start+(event.clientX-active.x)*(side==='left'?1:-1));}} onPointerUp={event=>finish(event)} onPointerCancel={event=>finish(event,true)} onKeyDown={event=>{
  if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const active=bounds(event.currentTarget),width=active.app.querySelector('.'+side+'-panel').getBoundingClientRect().width;apply(active,width+(event.key==='ArrowRight'?16:-16)*(side==='left'?1:-1));onCommit(active.width).catch(note);
 }}/>;
}
