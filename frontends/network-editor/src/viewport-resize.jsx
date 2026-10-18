import React,{useEffect,useRef} from 'react';
import {useReactFlow,useOnViewportChange} from '@xyflow/react';

// 只缩放视口；保留用户当前查看中心，不触发布局或网络修改。
export function resizedViewport(base,width,height){
 const zoom=Math.max(.12,Math.min(1.8,base.viewport.zoom*Math.min(width/base.width,height/base.height)));
 const center={x:(base.width/2-base.viewport.x)/base.viewport.zoom,y:(base.height/2-base.viewport.y)/base.viewport.zoom};
 return {x:width/2-center.x*zoom,y:height/2-center.y*zoom,zoom};
}
export function ViewportResize(){
 const anchor=useRef(),base=useRef(),size=useRef(),expected=useRef(),frame=useRef();const flow=useReactFlow();
 useOnViewportChange({onEnd:viewport=>{
  const target=expected.current;if(target&&Math.abs(target.x-viewport.x)<.1&&Math.abs(target.y-viewport.y)<.1&&Math.abs(target.zoom-viewport.zoom)<.0001)return;
  if(size.current)base.current={...size.current,viewport};
 }});
 useEffect(()=>{
  const element=anchor.current.closest('.node-link-gesture');
  const observer=new ResizeObserver(entries=>{
   const {width,height}=entries[0].contentRect;if(width<1||height<1)return;
   const before=size.current;size.current={width,height};
   if(!before){base.current={width,height,viewport:flow.getViewport()};return;}
   if(Math.abs(width-before.width)<.5&&Math.abs(height-before.height)<.5)return;
   cancelAnimationFrame(frame.current);frame.current=requestAnimationFrame(()=>{if(!base.current)return;expected.current=resizedViewport(base.current,width,height);flow.setViewport(expected.current,{duration:0});});
  });observer.observe(element);return()=>{observer.disconnect();cancelAnimationFrame(frame.current);};
 },[flow]);
 return <span ref={anchor} hidden/>;
}
