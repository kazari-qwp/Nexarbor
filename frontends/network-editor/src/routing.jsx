import React,{createContext,useContext,useEffect,useMemo,useRef,useState} from 'react';
import {BaseEdge,getSmoothStepPath,useNodes} from '@xyflow/react';
import {NODE_SIZE,planPorts,roundedRoute,routingGraph,circularEndpoint,previewRoute} from './routing.js';
const RouteContext=createContext({ports:new Map(),routes:new Map()});
const stamp=(edge,byId)=>JSON.stringify([edge,byId.get(edge.source)?.position,byId.get(edge.target)?.position]);
function touches(route,node){
 const points=[route.sourcePoint,...route.bendPoints,route.targetPoint],{x,y}=node.position;
 return points.some((b,i)=>{if(!i)return false;const a=points[i-1];return Math.max(a.x,b.x)>x-12&&Math.min(a.x,b.x)<x+NODE_SIZE+12&&Math.max(a.y,b.y)>y-12&&Math.min(a.y,b.y)<y+NODE_SIZE+12;});
}
export function RoutedScene({nodes,edges,optimize,dragging:dragActive=false,children}){
 const live=useNodes(),worker=useRef(),cacheRef=useRef(new Map()),positions=useRef(new Map()),pending=useRef(),serial=useRef(0);
 const [cache,setCache]=useState(new Map()),[failed,setFailed]=useState(false);
 const scene=useMemo(()=>{const byId=new Map(live.map(n=>[n.id,n]));return nodes.map(n=>{const current=byId.get(n.id);return {...n,position:current?.position??n.position,dragging:current?.dragging??false,measured:current?.measured??{width:NODE_SIZE,height:NODE_SIZE}};});},[nodes,live]);
 const byId=new Map(scene.map(n=>[n.id,n]));
 const ports=planPorts(scene,edges),routes=new Map(),knownPins=new Map();
 for(const edge of edges){const entry=cache.get(edge.id);if(entry?.stamp===stamp(edge,byId)){
  ports.set(edge.id,entry.port);routes.set(edge.id,entry.route);
  for(const point of Object.values(entry.port))knownPins.set(point.portId,point);
 }}
 for(const pair of ports.values())for(const end of ['source','target'])if(knownPins.has(pair[end].portId))pair[end]=knownPins.get(pair[end].portId);
 const dragging=dragActive||scene.some(n=>n.dragging),displayPorts=new Map(ports);
 for(const edge of edges){const entry=cache.get(edge.id);if(!routes.has(edge.id)&&entry?.identity===JSON.stringify(edge)){
  const deltas=Object.fromEntries(['source','target'].map(end=>[end,{x:byId.get(edge[end]).position.x-entry.positions[end].x,y:byId.get(edge[end]).position.y-entry.positions[end].y}]));
  routes.set(edge.id,{...entry.route,preview:deltas});
  displayPorts.set(edge.id,Object.fromEntries(['source','target'].map(end=>[end,{...entry.port[end],x:entry.port[end].x+deltas[end].x,y:entry.port[end].y+deltas[end].y}])));
 }}
 const geometryKey=JSON.stringify([routingGraph(scene,edges,ports),optimize,dragging]);
 useEffect(()=>{
  const instance=new Worker(new URL('./router.worker.js',import.meta.url),{type:'module'});worker.current=instance;
  instance.onmessage=({data})=>{
   const request=pending.current;if(data.key!==request?.key)return;
   if(data.error){setFailed(true);console.warn('Network routing:',data.error);return;}
   const answer=new Map(data.routes),next=new Map(cacheRef.current);
   for(const edge of request.edges){const route=answer.get(edge.id);if(route)next.set(edge.id,{route,identity:JSON.stringify(edge),positions:request.positions.get(edge.id),port:request.ports.get(edge.id),stamp:request.stamps.get(edge.id)});else next.delete(edge.id);}
   cacheRef.current=next;setCache(next);setFailed(false);
  };
  instance.onerror=()=>setFailed(true);
  return()=>{instance.terminate();worker.current=null;};
 },[]);
 const lastOptimize=useRef();
 useEffect(()=>{
  if(dragging){pending.current=null;return;}
  const moved=scene.filter(n=>positions.current.get(n.id)!==JSON.stringify(n.position));
  for(const n of scene)positions.current.set(n.id,JSON.stringify(n.position));
  const requested=optimize&&lastOptimize.current!==optimize.serial?new Set(optimize.nodes):new Set();lastOptimize.current=optimize?.serial;
  const needed=edges.filter(e=>{
   const entry=cacheRef.current.get(e.id);
   return !entry||entry.stamp!==stamp(e,byId)||requested.has(e.source)||requested.has(e.target)||moved.some(n=>n.id!==e.source&&n.id!==e.target&&touches(entry.route,n));
  });
  // Filtering only adds/removes rendered elements. Reuse valid routes verbatim;
  // when an edit/explicit optimization needs routing, only visible items enter it.
  if(!needed.length)return;
  const key=++serial.current;
  pending.current={key,edges:needed,ports:new Map(ports),stamps:new Map(edges.map(e=>[e.id,stamp(e,byId)])),positions:new Map(edges.map(e=>[e.id,{source:{...byId.get(e.source).position},target:{...byId.get(e.target).position}}]))};
  worker.current?.postMessage({key,graph:routingGraph(scene,edges,ports)});
 },[geometryKey]);
 return <RouteContext.Provider value={{ports:displayPorts,routes,byId}}>{children}{failed&&<div className="routing-notice" role="status">自动绕线暂不可用，正在显示基础连线</div>}</RouteContext.Provider>;
}
export function RoutedEdge(props){
 const {ports,routes,byId}=useContext(RouteContext),port=ports.get(props.id),route=routes.get(props.id);
 const endpoints=port?{sourceX:port.source.x,sourceY:port.source.y,targetX:port.target.x,targetY:port.target.y,sourcePosition:port.source.side,targetPosition:port.target.side}:props;
 const [fallback,x,y]=getSmoothStepPath({...endpoints,borderRadius:8,offset:24});
 let points=route?[route.sourcePoint,...route.bendPoints,route.targetPoint].map(p=>({...p})):null;
 // Extend the conservative square route's terminal segments to the circle.
 if(points){
  const source={x:points[0].x+(route.preview?.source.x??0),y:points[0].y+(route.preview?.source.y??0)},target={x:points.at(-1).x+(route.preview?.target.x??0),y:points.at(-1).y+(route.preview?.target.y??0)};
  const start=circularEndpoint(source,route.sourceSide,byId.get(props.source)),end=circularEndpoint(target,route.targetSide,byId.get(props.target));
  if(route.preview)points=previewRoute(route,start,end);else{points[0]=start;points[points.length-1]=end;}
 }
 const path=points?roundedRoute(points):fallback,center=points?.[Math.floor(points.length/2)];
 return <g data-routing={route?.preview?'preview':points?'avoiding':'direct'} data-source-side={endpoints.sourcePosition} data-target-side={endpoints.targetPosition}>
  <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} interactionWidth={14}
   label={props.selected||props.data?.hovered?props.label:undefined} labelX={center?.x??x} labelY={center?.y??y}
   labelStyle={props.labelStyle} labelBgStyle={props.labelBgStyle}/>
  <circle cx={points?.[0].x??endpoints.sourceX} cy={points?.[0].y??endpoints.sourceY} r={2} fill={props.style?.stroke} pointerEvents="none"/>
 </g>;
}
export const edgeTypes={routed:RoutedEdge};
