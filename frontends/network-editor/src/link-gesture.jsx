import React,{useEffect,useRef,useState} from 'react';
import {modifierMatches,pointerMatches,defaultShortcuts} from './shortcuts.js';

// 右键轻点和拖线分开处理；待放置的连线只改变本容器中的预览。
export function LinkGesture({children,onConnect,onCanvas,onSelectionContextMenu,onSelectionWheel,onBookmarkDrop,onHistoryDrop,onResourceDrop,edgePlacement,onEdgePlace,onEdgeCancel,bindings=defaultShortcuts}){
 const element=useRef(),latest=useRef(),gesture=useRef(),suppressContext=useRef(),placementClick=useRef(false);
 latest.current={onConnect,onSelectionContextMenu,onSelectionWheel,onBookmarkDrop,onHistoryDrop,onResourceDrop,onEdgePlace,onEdgeCancel,bindings};
 const [preview,setPreview]=useState(null),[edgePoint,setEdgePoint]=useState(null);
 useEffect(()=>{const wheel=event=>{if(!modifierMatches(event,latest.current.bindings.selectionWheel)||!event.deltaY||!latest.current.onSelectionWheel)return;event.preventDefault();event.stopPropagation();const steps=Math.max(1,Math.round(Math.abs(event.deltaY)/(event.deltaMode?3:100)));latest.current.onSelectionWheel(event.deltaY<0,steps);};const node=element.current;node.addEventListener('wheel',wheel,{passive:false,capture:true});return()=>node.removeEventListener('wheel',wheel,true);},[]);
 useEffect(()=>{
  if(!edgePlacement)return;
  const move=event=>setEdgePoint({id:edgePlacement.id,x:event.clientX,y:event.clientY}),outside=event=>{if(event.button===0&&!element.current.contains(event.target))latest.current.onEdgeCancel?.();},key=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();latest.current.onEdgeCancel?.();}};
  window.addEventListener('pointermove',move,true);window.addEventListener('pointerdown',outside,true);window.addEventListener('keydown',key,true);
  return()=>{window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerdown',outside,true);window.removeEventListener('keydown',key,true);};
 },[edgePlacement?.id]);
 const finish=(event,cancel=false)=>{
  const active=gesture.current;if(!active||event.pointerId!==active.pointer)return;
  event.preventDefault();event.stopPropagation();const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.react-flow__node')?.dataset.id;
  gesture.current=null;setPreview(null);event.currentTarget.releasePointerCapture?.(event.pointerId);
  if(active.button===2)suppressContext.current={x:event.clientX,y:event.clientY};
  if(!cancel&&active.moved&&target&&target!==active.source)latest.current.onConnect({source:active.source,target});
  else if(!cancel&&!active.moved&&active.button===2)latest.current.onSelectionContextMenu?.(event,{node:active.source});
 };
 let tail=preview;
 const point=edgePoint?.id===edgePlacement?.id?edgePoint:edgePlacement?.point;
 if(edgePlacement&&point&&element.current){
  const node=[...element.current.querySelectorAll('.react-flow__node')].find(n=>n.dataset.id===edgePlacement.source);
  if(node){const box=node.getBoundingClientRect(),bounds=element.current.getBoundingClientRect(),cx=box.x+box.width/2,cy=box.y+box.height/2,dx=point.x-cx,dy=point.y-cy,scale=1/Math.max(1,Math.hypot(dx/(box.width/2),dy/(box.height/2)));tail={x:cx+dx*scale-bounds.left,y:cy+dy*scale-bounds.top,endX:point.x-bounds.left,endY:point.y-bounds.top};}
 }
 return <div ref={element} className={'node-link-gesture'+(edgePlacement?' placing-edge':'')} tabIndex={-1} onPointerEnter={()=>onCanvas?.()} onDragOver={event=>{if(['application/x-nexarbor-bookmark','application/x-nexarbor-history','application/x-nexarbor-resource'].some(type=>event.dataTransfer.types.includes(type))){event.preventDefault();event.dataTransfer.dropEffect='copy';}}} onDrop={event=>{
  const id=event.dataTransfer.getData('application/x-nexarbor-bookmark'),entry=event.dataTransfer.getData('application/x-nexarbor-history'),resource=event.dataTransfer.getData('application/x-nexarbor-resource'),point={x:event.clientX,y:event.clientY};
  if(id){event.preventDefault();latest.current.onBookmarkDrop?.(id,point);}else if(entry){event.preventDefault();latest.current.onHistoryDrop?.(JSON.parse(entry),point);}else if(resource){event.preventDefault();latest.current.onResourceDrop?.(JSON.parse(resource),point);}
 }} onPointerDownCapture={event=>{
  onCanvas?.();suppressContext.current=null;event.currentTarget.focus({preventScroll:true});
  if(edgePlacement){if(event.button===0){event.preventDefault();event.stopPropagation();placementClick.current=true;const target=event.target.closest('.react-flow__node')?.dataset.id;if(target)latest.current.onEdgePlace?.(target,{x:event.clientX,y:event.clientY});else latest.current.onEdgeCancel?.();return;}latest.current.onEdgeCancel?.();}
  if(!pointerMatches(event,bindings.linkDrag))return;const node=event.target.closest('.react-flow__node');if(!node)return;
  event.preventDefault();event.stopPropagation();gesture.current={source:node.dataset.id,pointer:event.pointerId,button:event.button,x:event.clientX,y:event.clientY,moved:false};event.currentTarget.setPointerCapture(event.pointerId);
 }} onClickCapture={event=>{if(placementClick.current){placementClick.current=false;event.preventDefault();event.stopPropagation();}}} onPointerMoveCapture={event=>{
  onCanvas?.();const active=gesture.current;if(!active||event.pointerId!==active.pointer)return;
  event.preventDefault();event.stopPropagation();active.moved ||= Math.hypot(event.clientX-active.x,event.clientY-active.y)>6;if(!active.moved)return;
  const bounds=event.currentTarget.getBoundingClientRect();setPreview({x:active.x-bounds.left,y:active.y-bounds.top,endX:event.clientX-bounds.left,endY:event.clientY-bounds.top});
 }} onPointerUpCapture={event=>finish(event)} onPointerCancel={event=>finish(event,true)} onContextMenuCapture={event=>{
  event.preventDefault();event.stopPropagation();if(gesture.current)return;const suppressed=suppressContext.current;suppressContext.current=null;if(suppressed&&Math.hypot(event.clientX-suppressed.x,event.clientY-suppressed.y)<4)return;
  latest.current.onSelectionContextMenu?.(event,{node:event.target.closest('.react-flow__node')?.dataset.id,edge:event.target.closest('.react-flow__edge')?.dataset.id});
 }}>
  {children}{tail&&<svg className="node-link-preview" aria-hidden="true"><path d={`M ${tail.x} ${tail.y} H ${(tail.x+tail.endX)/2} V ${tail.endY} H ${tail.endX}`}/><circle cx={tail.endX} cy={tail.endY} r="5"/></svg>}
  {edgePlacement&&<div className="edge-placement-hint" role="status" style={tail?{left:Math.max(8,Math.min(tail.endX+14,(element.current?.clientWidth??500)-265)),top:Math.max(8,Math.min(tail.endY+14,(element.current?.clientHeight??400)-38))}:{left:12,top:12}}>点击终点节点 · 点击其他区域或 Esc 取消</div>}
 </div>;
}
