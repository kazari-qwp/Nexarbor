import React,{createContext,useContext,useEffect,useMemo,useRef,useState} from 'react';
import {BaseEdge,getSmoothStepPath,useNodes} from '@xyflow/react';
import {NODE_SIZE,roundedRoute,routingGraph,circularEndpoint} from './routing.js';
const RouteContext=createContext({routes:new Map()});
const stamp=(edge,byId)=>JSON.stringify([edge,byId.get(edge.source)?.position,byId.get(edge.target)?.position]);
const sides={east:'right',west:'left',north:'top',south:'bottom'};
function touches(route,box){
 const points=[route.sourcePoint,...route.bendPoints,route.targetPoint];
 return points.some((b,i)=>{if(!i)return false;const a=points[i-1];return Math.max(a.x,b.x)>=box.x-24&&Math.min(a.x,b.x)<=box.x+NODE_SIZE+24&&Math.max(a.y,b.y)>=box.y-24&&Math.min(a.y,b.y)<=box.y+NODE_SIZE+24;});
}
export function RoutedScene({nodes,edges,optimize,dragging:dragActive=false,children}){
 const live=useNodes(),worker=useRef(),cacheRef=useRef(new Map()),positions=useRef(new Map()),pending=useRef(),latest=useRef(),serial=useRef(0);
 const [cache,setCache]=useState(new Map()),[failed,setFailed]=useState(false);
 const scene=useMemo(()=>{const byId=new Map(live.map(n=>[n.id,n]));return nodes.map(n=>{const current=byId.get(n.id);return {...n,position:current?.position??n.position,dragging:current?.dragging??false,measured:current?.measured??{width:NODE_SIZE,height:NODE_SIZE}};});},[nodes,live]);
 const byId=new Map(scene.map(n=>[n.id,n]));
 const dragging=dragActive||scene.some(n=>n.dragging),routes=new Map();
 for(const edge of edges){const entry=cache.get(edge.id);if(entry?.identity===JSON.stringify(edge)){
  const delta=Object.fromEntries(['source','target'].map(end=>[end,{x:byId.get(edge[end]).position.x-entry.positions[end].x,y:byId.get(edge[end]).position.y-entry.positions[end].y}]));
  routes.set(edge.id,{...entry.route,preview:entry.stamp===stamp(edge,byId)?undefined:delta});
 }}
 const geometryKey=JSON.stringify([routingGraph(scene,edges),optimize,dragging]);latest.current=geometryKey;
 useEffect(()=>{
  const instance=new Worker(new URL('./router.worker.js',import.meta.url),{type:'module'});worker.current=instance;
  instance.onmessage=({data})=>{
   const request=pending.current;if(data.key!==request?.key||request.geometry!==latest.current)return;
   if(data.error){pending.current=null;setFailed(true);console.warn('Network routing:',data.error);return;}
   const answer=new Map(data.routes);
   // Never apply half a shared routing result. The worker only computes edges
   // that this request will actually replace; the rest stay fixed on screen.
   if(request.edges.some(edge=>!answer.has(edge.id))){pending.current=null;setFailed(true);return;}
   const next=new Map(cacheRef.current);
   for(const edge of request.edges)next.set(edge.id,{route:answer.get(edge.id),identity:JSON.stringify(edge),positions:request.positions.get(edge.id),stamp:request.stamps.get(edge.id)});
   pending.current=null;cacheRef.current=next;setCache(next);setFailed(false);
  };
  instance.onerror=()=>setFailed(true);
  return()=>{instance.terminate();worker.current=null;};
 },[]);
 const lastOptimize=useRef();
 useEffect(()=>{
  // A render that changed geometry invalidates older worker replies immediately.
  pending.current=null;
  if(dragging)return;
  const moved=scene.filter(n=>positions.current.has(n.id)&&JSON.stringify(positions.current.get(n.id))!==JSON.stringify(n.position));
  const previous=new Map(positions.current);for(const n of scene)positions.current.set(n.id,{...n.position});
  const requested=optimize&&lastOptimize.current!==optimize.serial?new Set(optimize.nodes):new Set();lastOptimize.current=optimize?.serial;
  const needed=edges.filter(e=>{const entry=cacheRef.current.get(e.id);
   return !entry||entry.stamp!==stamp(e,byId)||requested.has(e.source)||requested.has(e.target)||moved.some(n=>n.id!==e.source&&n.id!==e.target&&(touches(entry.route,n.position)||touches(entry.route,previous.get(n.id))));
  });
  if(!needed.length)return;
  const key=++serial.current;
  pending.current={key,geometry:geometryKey,edges:needed,stamps:new Map(needed.map(e=>[e.id,stamp(e,byId)])),positions:new Map(needed.map(e=>[e.id,{source:{...byId.get(e.source).position},target:{...byId.get(e.target).position}}]))};
  worker.current?.postMessage({key,graph:routingGraph(scene,needed)});
 },[geometryKey]);
 return <RouteContext.Provider value={{routes,byId}}>{children}{failed&&<div className="routing-notice" role="status">自动绕线暂不可用，正在显示基础连线</div>}</RouteContext.Provider>;
}
export function RoutedEdge(props){
 const {routes,byId}=useContext(RouteContext),route=routes.get(props.id);
 const from=byId.get(props.source),to=byId.get(props.target);
 const endpoints=route?{sourceX:route.sourcePoint.x+(route.preview?.source.x??0),sourceY:route.sourcePoint.y+(route.preview?.source.y??0),targetX:route.targetPoint.x+(route.preview?.target.x??0),targetY:route.targetPoint.y+(route.preview?.target.y??0),sourcePosition:sides[route.sourceSide],targetPosition:sides[route.targetSide]}:props;
 const start=circularEndpoint({x:endpoints.sourceX,y:endpoints.sourceY},route?.sourceSide??({left:'west',right:'east',top:'north',bottom:'south'}[props.sourcePosition]),from);
 const end=circularEndpoint({x:endpoints.targetX,y:endpoints.targetY},route?.targetSide??({left:'west',right:'east',top:'north',bottom:'south'}[props.targetPosition]),to);
 const [preview,x,y]=getSmoothStepPath({...endpoints,sourceX:start.x,sourceY:start.y,targetX:end.x,targetY:end.y,borderRadius:8,offset:20});
 const points=route&&!route.preview?[start,...route.bendPoints,end]:null;
 const path=points?roundedRoute(points):preview,center=points?.[Math.floor(points.length/2)];
 return <g data-routing={route?.preview?'preview':points?'avoiding':'direct'} data-source-side={endpoints.sourcePosition} data-target-side={endpoints.targetPosition}>
  <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} interactionWidth={14}
   label={props.selected||props.data?.hovered?props.label:undefined} labelX={center?.x??x} labelY={center?.y??y}
   labelStyle={props.labelStyle} labelBgStyle={props.labelBgStyle}/>
  <circle cx={start.x} cy={start.y} r={2} fill={props.style?.stroke} pointerEvents="none"/>
 </g>;
}
export function OwnershipEdge(props){const [path]=getSmoothStepPath({...props,borderRadius:6});return <BaseEdge path={path} style={{stroke:'#9073ac',strokeWidth:1.2,strokeDasharray:'4 3'}} interactionWidth={0}/>;}
export const edgeTypes={routed:RoutedEdge,ownership:OwnershipEdge};
