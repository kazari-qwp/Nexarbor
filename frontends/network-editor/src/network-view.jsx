import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import ELK from 'elkjs/lib/elk.bundled.js';
import {placeNetwork} from './network-view-layout.js';
import {NetworkNode} from './network-node.jsx';
import {nodeKind} from './model.js';
import {roundedRoute,circularEndpoint} from './routing.js';
import {planRegions,visibleRefs,completeRefs,regionAnchors} from './network-view-regions.js';
import './style.css';
import './network-view.css';
const elk=new ELK();
let routeWorker,routeSerial=0;
function routeBatch(graph){
 return new Promise((resolve,reject)=>{
  const worker=routeWorker??=new Worker(new URL('./router.worker.js',import.meta.url),{type:'module'}),key=++routeSerial;
  worker.onmessage=({data})=>{if(data.key===key)data.error?reject(Error(data.error)):resolve(new Map(data.routes));};
  worker.onerror=error=>{worker.terminate();routeWorker=null;reject(Error(error.message||'图片连线路由失败'));};
  worker.postMessage({key,graph,picture:true});
 });
}
async function routeGraph(graph){
 const result=new Map(),edges=[...graph.edges].sort((a,b)=>a.source.localeCompare(b.source));
 // Global crossing optimization grows expensive on dense full networks. Each
 // batch still avoids every node; small source batches keep export time bounded.
 for(let i=0;i<edges.length;i+=16)for(const [id,route] of await routeBatch({...graph,edges:edges.slice(i,i+16)}))result.set(id,route);
 return result;
}
const side=(point,n)=>Math.abs(point.x-n.x)<1?'west':Math.abs(point.x-n.x-n.width)<1?'east':Math.abs(point.y-n.y)<1?'north':'south';
function terminal(point,n){return circularEndpoint(point,side(point,n),{position:{x:n.x,y:n.y},measured:{width:n.width,height:n.height},data:{node:n}});}
function edgeLabel(edge,scene){
 const id=scene.showEdgeIds?(edge.refs.length>3?edge.refs.slice(0,2).join(',')+'… ('+edge.refs.length+')':edge.refs.join(',')):(edge.refs.length>1?'×'+edge.refs.length:'');
 const channels=scene.showChannels?edge.channels.join(','):'';
 const text=[id,channels].filter(Boolean).join(' · ');return text.length>66?text.slice(0,65)+'…':text;
}
const labelWidth=text=>[...text].reduce((sum,c)=>sum+(c.charCodeAt(0)>255?12:7),12);
const edgeColors=['#36cfff','#ffb72e','#ba8cff','#3ce79e','#ff6eae','#daef48','#ff795b','#7bafff'];
function edgeColor(edge){return edge.ownership?'#d08fff':edgeColors[(Number(edge.source.slice(1))||0)%edgeColors.length];}
async function layoutScene(scene){
 const nodes=await placeNetwork(scene,elk),byId=new Map(nodes.map(n=>[n.ref,n]));
 const links=[...scene.edges.map(e=>({...e,label:edgeLabel(e,scene)})),...scene.ownership.map(e=>({...e,ownership:true,label:''}))];
 const routes=await routeGraph({id:'picture',children:nodes.map(n=>({id:n.ref,x:n.x,y:n.y,width:n.width,height:n.height})),edges:links.flatMap((e,i)=>e.source===e.target?[]:[{id:String(i),source:e.source,target:e.target}])});
 const edges=links.map((data,i)=>{
  const from=byId.get(data.source),to=byId.get(data.target),route=routes.get(String(i));
  const loop=[{x:from.x+from.width,y:from.y+from.height/2},{x:from.x+from.width+28,y:from.y+from.height/2},{x:from.x+from.width+28,y:from.y-12},{x:from.x+from.width/2,y:from.y-12},{x:from.x+from.width/2,y:from.y}];
  if(!route&&data.source!==data.target)throw Error('连线路由失败：'+data.refs?.join(','));
  const points=data.source===data.target?loop:[terminal(route.sourcePoint,from),...route.bendPoints,terminal(route.targetPoint,to)];
  const segments=points.slice(1).map((p,i)=>({a:points[i],b:p,length:Math.hypot(p.x-points[i].x,p.y-points[i].y)})).sort((a,b)=>b.length-a.length);
  const best=segments[0],x=(best.a.x+best.b.x)/2,y=(best.a.y+best.b.y)/2,width=labelWidth(data.label);
  return {...data,id:String(i),path:roundedRoute(points),points,labelX:x,labelY:y,labelWidth:width};
 });
 const points=[...nodes.flatMap(n=>[{x:n.x-8,y:n.y-35},{x:n.x+n.width+8,y:n.y+n.height+(n.subnodes?32:10)}]),...edges.flatMap(e=>[...e.points,...(e.label?[{x:e.labelX-e.labelWidth/2,y:e.labelY-12},{x:e.labelX+e.labelWidth/2,y:e.labelY+12}]:[])])];
 const minX=Math.min(0,...points.map(p=>p.x))-30,minY=Math.min(0,...points.map(p=>p.y))-25;
 return {nodes,edges,bounds:[minX,minY,Math.max(250,...points.map(p=>p.x))-minX+30,Math.max(180,...points.map(p=>p.y))-minY+25]};
}
function Diagram({graph,plan,region}){
 return <svg className="observer-map" viewBox={(region?.bounds??graph.bounds).join(' ')} preserveAspectRatio="xMidYMid meet" role="img" aria-label="带编号的网络结构图">
  <defs><clipPath id="observer-viewport"><rect x={(region?.bounds??graph.bounds)[0]} y={(region?.bounds??graph.bounds)[1]} width={(region?.bounds??graph.bounds)[2]} height={(region?.bounds??graph.bounds)[3]}/></clipPath>{[...edgeColors,'#a9e8cd'].map(color=><marker key={color} id={'arrow-'+color.slice(1)} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 Z" fill={color}/></marker>)}</defs>
  <g clipPath="url(#observer-viewport)">
  {graph.edges.map(e=>{const color=e.selected?'#a9e8cd':edgeColor(e);return <g key={e.id}><path d={e.path} fill="none" stroke={color} strokeWidth={e.selected?2.8:1.6} strokeDasharray={e.ownership?'5 5':undefined} markerEnd={e.ownership?undefined:'url(#arrow-'+color.slice(1)+')'}/>{e.label&&<g transform={`translate(${e.labelX},${e.labelY})`}><rect x={-e.labelWidth/2} y={-11} width={e.labelWidth} height="22" rx="3" fill="#101923" stroke={color}/><text textAnchor="middle" dominantBaseline="central" fill={color} fontSize="12">{e.label}</text></g>}</g>;})}
  {graph.nodes.map(n=><g key={n.ref}><g transform={`translate(${n.x},${n.y-27})`}><rect width={n.ref.length*9+12} height="22" rx="4" fill="#29495b" stroke={edgeColor({source:n.ref})} strokeWidth="1.5"/><text x="6" y="15" fill="#edf7ff" fontSize="14" fontWeight="700" fontFamily="Consolas,monospace">{n.ref}</text></g><foreignObject x={n.x} y={n.y} width={n.width} height={n.height} style={{overflow:'visible'}}><NetworkNode readonly selected={n.selected} data={{node:{...n,node_id:n.id},kind:nodeKind(n),toolCount:n.offered_tools.length}}/></foreignObject>{n.subnodes>0&&<text x={n.x+8} y={n.y+n.height+21} fill="#cdb2e7" fontSize="12">亚节点 {n.subnodes}</text>}</g>)}
  {!region&&plan.regions.map(r=>{const [x,y,w,h]=r.bounds,s=1/plan.scale,inset=(3+(r.row+2*r.column)%4*3)*s,anchors=regionAnchors(graph.nodes,r.bounds).slice(0,2).map(n=>n.name).join('、'),label=r.id+(anchors?' · '+anchors.slice(0,18):''),labelWidth=[...label].reduce((v,c)=>v+(c.charCodeAt(0)>255?16:10),18);return <g key={r.id} className="observer-region"><rect x={x+inset} y={y+inset} width={Math.max(1,w-2*inset)} height={Math.max(1,h-2*inset)} fill={r.color} fillOpacity=".02" stroke={r.color} strokeWidth={2.3*s} strokeDasharray={`${8*s} ${5*s}`}/><g transform={`translate(${x+inset+5*s},${y+inset+5*s}) scale(${s})`}><rect width={labelWidth} height="28" rx="4" fill="#14242f" stroke={r.color} strokeWidth="1.5"/><text x="8" y="20" fill={r.color} fontSize="16" fontWeight="700">{label}</text></g></g>;})}
  </g>
 </svg>;
}
function Picture(){
 const [picture,setPicture]=useState(null);
 useEffect(()=>{const layouts=new Map();window.networkView?.receive(async scene=>{try{
  let graph=layouts.get(scene.view);if(!graph){graph=await layoutScene(scene);layouts.set(scene.view,graph);if(layouts.size>12)layouts.delete(layouts.keys().next().value);}
  const plan=planRegions(graph.bounds,scene.size,{nodes:graph.nodes}),region=scene.region?plan.regions.find(r=>r.id===scene.region):null;
  if(scene.region&&!region)throw Error('区域不存在；请先查看此视图的概览。');
  const display=region?{...graph,edges:graph.edges.map(e=>{if(e.ownership)return e;const label=edgeLabel(e,scene);return {...e,label,labelWidth:labelWidth(label)};})}:graph;
  setPicture({scene,graph:display,plan,region});
 }catch(error){window.networkView?.ready({error:String(error?.message??error)});}});},[]);
 useEffect(()=>{if(!picture)return;let live=true;(async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(live){const {graph,plan,region}=picture;window.networkView?.ready({ok:true,kind:region?'detail':'overview',...(region?{region:region.id,position:{row:region.row,column:region.column},visible_nodes:completeRefs(graph.nodes,region.bounds),clipped_nodes:visibleRefs(graph.nodes,region.bounds).length-completeRefs(graph.nodes,region.bounds).length}:{}),regions:plan.regions.filter(r=>!region||Math.abs(r.row-region.row)<=1&&Math.abs(r.column-region.column)<=1).map(r=>({id:r.id,row:r.row,column:r.column,color:r.color,nodes:r.complete.length,...(!region?{anchors:regionAnchors(graph.nodes,r.bounds)}:{})})),overlap:plan.regions.length?plan.overlap:0});}})();return()=>{live=false;};},[picture]);
 const scene=picture?.scene,region=picture?.region,regions=picture?.plan.regions??[];
 return <main className="network-picture" style={{width:scene?.size.width??1500,height:scene?.size.height??1250}}><header><div><strong>{scene?.title??'网络总览'}{region?' · 局部 '+region.id:''}</strong><span>快照 {scene?.snapshot.slice(0,10)} · 第 {scene?.page??1}/{scene?.pages??1} 页</span></div><p>{region?'本图完整节点 '+region.complete.length+' · ':''}视图含 {scene?.counts.shown_nodes??0}/{scene?.counts.total_nodes??0} 节点 · {scene?.counts.shown_edges??0}/{scene?.counts.total_edges??0} 连线</p></header>{picture?<Diagram graph={picture.graph} plan={picture.plan} region={region}/>:<div/>}<footer><span><i className="mint"/>Agent</span><span><i className="gold"/>文本 / 数据</span><span><i className="purple"/>亚节点 / 脉冲</span><span>实线按起点分色（循环用色）　×n＝平行边　虚线＝归属　!频道＝黑名单</span><span>{region?'沿用概览布局；窗口重叠20%，边可延伸至框外':regions.length?'彩色框 R1… 可按编号请求局部图（重叠20%）':'可用 N / E 编号继续查询；隐藏部分不表示不存在'}</span></footer></main>;
}
createRoot(document.getElementById('root')).render(<Picture/>);
