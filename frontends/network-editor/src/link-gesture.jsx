import React,{useEffect,useRef,useState} from 'react';
import {modifierMatches,pointerMatches,defaultShortcuts} from './shortcuts.js';

// 使用浏览器 Pointer Events；预览状态局限在此容器，避免重新布局整个图。
export function LinkGesture({children,onConnect,onCanvas,onSelectionWheel,onBookmarkDrop,onHistoryDrop,onResourceDrop,bindings=defaultShortcuts}){
 const element=useRef(),latest=useRef();latest.current={onSelectionWheel,onBookmarkDrop,onHistoryDrop,onResourceDrop,bindings};
 const gesture=useRef(),[preview,setPreview]=useState(null);
 useEffect(()=>{const wheel=event=>{if(!modifierMatches(event,latest.current.bindings.selectionWheel)||!event.deltaY||!latest.current.onSelectionWheel)return;event.preventDefault();event.stopPropagation();const steps=Math.max(1,Math.round(Math.abs(event.deltaY)/(event.deltaMode?3:100)));latest.current.onSelectionWheel(event.deltaY<0,steps);};const node=element.current;node.addEventListener('wheel',wheel,{passive:false,capture:true});return()=>node.removeEventListener('wheel',wheel,true);},[]);
 const finish=(event,cancel=false)=>{
  const active=gesture.current;if(!active||event.pointerId!==active.pointer)return;
  event.preventDefault();event.stopPropagation();
  const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.react-flow__node')?.dataset.id;
  gesture.current=null;setPreview(null);event.currentTarget.releasePointerCapture?.(event.pointerId);
  if(!cancel&&active.moved&&target&&target!==active.source)onConnect({source:active.source,target});
 };
 return <div ref={element} className="node-link-gesture" tabIndex={-1} onPointerEnter={()=>onCanvas?.()} onDragOver={event=>{if(['application/x-nexarbor-bookmark','application/x-nexarbor-history','application/x-nexarbor-resource'].some(type=>event.dataTransfer.types.includes(type))){event.preventDefault();event.dataTransfer.dropEffect='copy';}}} onDrop={event=>{const id=event.dataTransfer.getData('application/x-nexarbor-bookmark'),entry=event.dataTransfer.getData('application/x-nexarbor-history'),resource=event.dataTransfer.getData('application/x-nexarbor-resource'),point={x:event.clientX,y:event.clientY};if(id){event.preventDefault();latest.current.onBookmarkDrop?.(id,point);}else if(entry){event.preventDefault();latest.current.onHistoryDrop?.(JSON.parse(entry),point);}else if(resource){event.preventDefault();latest.current.onResourceDrop?.(JSON.parse(resource),point);}}} onPointerDownCapture={event=>{
  onCanvas?.();event.currentTarget.focus({preventScroll:true});
  if(!pointerMatches(event,bindings.linkDrag))return;const node=event.target.closest('.react-flow__node');if(!node)return;
  event.preventDefault();event.stopPropagation();
  gesture.current={source:node.dataset.id,pointer:event.pointerId,x:event.clientX,y:event.clientY,moved:false};
  event.currentTarget.setPointerCapture(event.pointerId);
 }} onPointerMoveCapture={event=>{
  onCanvas?.();
  const active=gesture.current;if(!active||event.pointerId!==active.pointer)return;
  event.preventDefault();event.stopPropagation();
  active.moved ||= Math.hypot(event.clientX-active.x,event.clientY-active.y)>6;if(!active.moved)return;
  const bounds=event.currentTarget.getBoundingClientRect();
  setPreview({x:active.x-bounds.left,y:active.y-bounds.top,endX:event.clientX-bounds.left,endY:event.clientY-bounds.top});
 }} onPointerUpCapture={event=>finish(event)} onPointerCancel={event=>finish(event,true)}
 onContextMenuCapture={event=>{if(event.target.closest('.react-flow__node')||gesture.current)event.preventDefault();}}>
  {children}{preview&&<svg className="node-link-preview" aria-hidden="true"><path d={`M ${preview.x} ${preview.y} H ${(preview.x+preview.endX)/2} V ${preview.endY} H ${preview.endX}`}/><circle cx={preview.endX} cy={preview.endY} r="5"/></svg>}
 </div>;
}
