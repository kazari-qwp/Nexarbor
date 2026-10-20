import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import ELK from 'elkjs/lib/elk.bundled.js';
import {NetworkNode} from './network-node.jsx';
import {nodeKind} from './model.js';
import {roundedRoute,circularEndpoint} from './routing.js';
import {planRegions,visibleRefs,regionAnchors} from './network-view-regions.js';
import './style.css';
import './network-view.css';
const elk=new ELK();
const side=(point,n)=>Math.abs(point.x-n.x)<1?'west':Math.abs(point.x-n.x-n.width)<1?'east':Math.abs(point.y-n.y)<1?'north':'south';
function terminal(point,n){return circularEndpoint(point,side(point,n),{position:{x:n.x,y:n.y},measured:{width:n.width,height:n.height},data:{node:n}});}
function edgeLabel(edge,scene){
 const id=scene.showEdgeIds?(edge.refs.length>3?edge.refs.slice(0,2).join(',')+'… ('+edge.refs.length+')':edge.refs.join(',')):(edge.refs.length>1?'×'+edge.refs.length:'');
 const channels=scene.showChannels?edge.channels.join(','):'';
 const text=[id,channels].filter(Boolean).join(' · ');return text.length>66?text.slice(0,65)+'…':text;
}
async function layoutScene(scene){
 const raw=scene.nodes.map(n=>({id:n.ref,width:n.type==='subnode'?106:112,height:n.type==='subnode'?38:112}));
 const links=[...scene.edges.map(e=>({...e,label:edgeLabel(e,scene)})),...scene.ownership.map(e=>({...e,ownership:true,label:''}))];
 const layout=await elk.layout({id:'picture',layoutOptions:{'elk.algorithm':'layered','elk.direction':'RIGHT','elk.edgeRouting':'ORTHOGONAL','elk.layered.mergeEdges':'true','elk.spacing.nodeNode':'85','elk.layered.spacing.nodeNodeBetweenLayers':'100','elk.spacing.componentComponent':'80','elk.randomSeed':'1'},children:raw,edges:links.map((e,i)=>({id:String(i),sources:[e.source],targets:[e.target]}))});
 const byId=new Map((layout.children??[]).map(n=>[n.id,{...scene.nodes.find(v=>v.ref===n.id),...n}]));
 const nodes=[...byId.values()];
 const edges=(layout.edges??[]).flatMap(e=>{
  const section=e.sections?.[0];if(!section)return [];
  const data=links[Number(e.id)],from=byId.get(data.source),to=byId.get(data.target);
  const points=[terminal(section.startPoint,from),...(section.bendPoints??[]),terminal(section.endPoint,to)];
  const segments=points.slice(1).map((p,i)=>({a:points[i],b:p,length:Math.hypot(p.x-points[i].x,p.y-points[i].y)})).sort((a,b)=>b.length-a.length);
  const best=segments[0],x=(best.a.x+best.b.x)/2,y=(best.a.y+best.b.y)/2,width=[...data.label].reduce((sum,c)=>sum+(c.charCodeAt(0)>255?12:7),12);
  return [{...data,id:e.id,path:roundedRoute(points),points,labelX:x,labelY:y,labelWidth:width}];
 });
 const points=[...nodes.flatMap(n=>[{x:n.x-8,y:n.y-35},{x:n.x+n.width+8,y:n.y+n.height+(n.subnodes?32:10)}]),...edges.flatMap(e=>[...e.points,...(e.label?[{x:e.labelX-e.labelWidth/2,y:e.labelY-12},{x:e.labelX+e.labelWidth/2,y:e.labelY+12}]:[])])];
 const minX=Math.min(0,...points.map(p=>p.x))-30,minY=Math.min(0,...points.map(p=>p.y))-25;
 return {nodes,edges,bounds:[minX,minY,Math.max(250,...points.map(p=>p.x))-minX+30,Math.max(180,...points.map(p=>p.y))-minY+25]};
}
function Diagram({graph,plan,region}){
 return <svg className="observer-map" viewBox={(region?.bounds??graph.bounds).join(' ')} preserveAspectRatio="xMidYMid meet" role="img" aria-label="带编号的网络结构图">
  <defs><clipPath id="observer-viewport"><rect x={(region?.bounds??graph.bounds)[0]} y={(region?.bounds??graph.bounds)[1]} width={(region?.bounds??graph.bounds)[2]} height={(region?.bounds??graph.bounds)[3]}/></clipPath>{[['arrow','#87a8b8'],['selected-arrow','#a9e8cd']].map(([id,color])=><marker key={id} id={id} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 Z" fill={color}/></marker>)}</defs>
  <g clipPath="url(#observer-viewport)">
  {graph.edges.map(e=><g key={e.id}><path d={e.path} fill="none" stroke={e.ownership?'#b695da':e.selected?'#a9e8cd':'#87a8b8'} strokeWidth={e.selected?2.8:1.6} strokeDasharray={e.ownership?'5 5':undefined} markerEnd={e.ownership?undefined:'url(#'+(e.selected?'selected-arrow':'arrow')+')'}/>{e.label&&<g transform={`translate(${e.labelX},${e.labelY})`}><rect x={-e.labelWidth/2} y={-11} width={e.labelWidth} height="22" rx="3" fill="#101923" stroke="#354d5d"/><text textAnchor="middle" dominantBaseline="central" fill="#dcebf4" fontSize="12">{e.label}</text></g>}</g>)}
  {graph.nodes.map(n=><g key={n.ref}><g transform={`translate(${n.x},${n.y-27})`}><rect width={n.ref.length*9+12} height="22" rx="4" fill="#29495b" stroke="#62879a"/><text x="6" y="15" fill="#edf7ff" fontSize="14" fontWeight="700" fontFamily="Consolas,monospace">{n.ref}</text></g><foreignObject x={n.x} y={n.y} width={n.width} height={n.height} style={{overflow:'visible'}}><NetworkNode readonly selected={n.selected} data={{node:{...n,node_id:n.id},kind:nodeKind(n),toolCount:n.offered_tools.length}}/></foreignObject>{n.subnodes>0&&<text x={n.x+8} y={n.y+n.height+21} fill="#cdb2e7" fontSize="12">亚节点 {n.subnodes}</text>}</g>)}
  {!region&&plan.regions.map(r=>{const [x,y,w,h]=r.bounds,s=1/plan.scale;return <g key={r.id} className="observer-region"><rect x={x} y={y} width={w} height={h} fill="none" stroke="#e6c06e" strokeWidth={1.4*s} strokeDasharray={`${7*s} ${5*s}`}/><g transform={`translate(${x+6*s},${y+6*s}) scale(${s})`}><rect width={r.id.length*10+16} height="27" rx="4" fill="#493e24" stroke="#e6c06e"/><text x="8" y="19" fill="#fff1c5" fontSize="17" fontWeight="700">{r.id}</text></g></g>;})}
  </g>
 </svg>;
}
function Picture(){
 const [picture,setPicture]=useState(null);
 useEffect(()=>{const layouts=new Map();window.networkView?.receive(async scene=>{try{
  let graph=layouts.get(scene.view);if(!graph){graph=await layoutScene(scene);layouts.set(scene.view,graph);if(layouts.size>12)layouts.delete(layouts.keys().next().value);}
  const plan=planRegions(graph.bounds,scene.size),region=scene.region?plan.regions.find(r=>r.id===scene.region):null;
  if(scene.region&&!region)throw Error('区域不存在；请先查看此视图的概览。');
  setPicture({scene,graph,plan,region});
 }catch(error){window.networkView?.ready({error:error.message});}});},[]);
 useEffect(()=>{if(!picture)return;let live=true;(async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(live){const {graph,plan,region}=picture;window.networkView?.ready({ok:true,kind:region?'detail':'overview',...(region?{region:region.id,position:{row:region.row,column:region.column},visible_nodes:visibleRefs(graph.nodes,region.bounds)}:{}),regions:plan.regions.filter(r=>!region||Math.abs(r.row-region.row)<=1&&Math.abs(r.column-region.column)<=1).map(r=>({id:r.id,row:r.row,column:r.column,nodes:visibleRefs(graph.nodes,r.bounds).length,...(!region?{anchors:regionAnchors(graph.nodes,r.bounds)}:{})})),overlap:plan.regions.length?.28:0});}})();return()=>{live=false;};},[picture]);
 const scene=picture?.scene,region=picture?.region,regions=picture?.plan.regions??[];
 return <main className="network-picture" style={{width:scene?.size.width??1500,height:scene?.size.height??1100}}><header><div><strong>{scene?.title??'网络总览'}{region?' · 局部 '+region.id:''}</strong><span>快照 {scene?.snapshot.slice(0,10)} · 第 {scene?.page??1}/{scene?.pages??1} 页</span></div><p>视图含 {scene?.counts.shown_nodes??0}/{scene?.counts.total_nodes??0} 节点 · {scene?.counts.shown_edges??0}/{scene?.counts.total_edges??0} 连线 · 边界外 {scene?.counts.boundary_edges??0}</p></header>{picture?<Diagram graph={picture.graph} plan={picture.plan} region={region}/>:<div/>}<footer><span><i className="mint"/>Agent</span><span><i className="gold"/>文本 / 数据</span><span><i className="purple"/>亚节点 / 脉冲</span><span>箭头＝方向　×n＝平行边　虚线＝归属　!频道＝黑名单</span><span>{region?'沿用概览布局；窗口间至少重叠 28%，边可延伸至框外':regions.length?'金色框 R1… 可按编号请求局部图（重叠 ≥28%）':'可用 N / E 编号继续查询；隐藏部分不表示不存在'}</span></footer></main>;
}
createRoot(document.getElementById('root')).render(<Picture/>);
