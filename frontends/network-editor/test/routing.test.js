import test from 'node:test';
import assert from 'node:assert/strict';
import ELK from 'elkjs/lib/elk.bundled.js';
import {NODE_SIZE,planPorts,routingGraph} from '../src/routing.js';
import {sceneRouter} from '../src/route-session.js';
import {arrangeGraph} from '../src/layout.js';
const node=(id,x,y)=>({id,position:{x,y},measured:{width:NODE_SIZE,height:NODE_SIZE},data:{}});
const edge=(id,source,target,direction='write',channels=[])=>({id,source,target,direction,metadata:{channels,visibility:'public'}});
const points=route=>[route.sourcePoint,...route.bendPoints,route.targetPoint];
function assertClear(routes,nodes,edges){
 for(const [id,route] of routes){const e=edges.find(e=>e.id===id),p=points(route);
  for(let i=1;i<p.length;i++)for(let t=0;t<=1;t+=.025){const x=p[i-1].x+(p[i].x-p[i-1].x)*t,y=p[i-1].y+(p[i].y-p[i-1].y)*t;
   for(const n of nodes)if(![e.source,e.target].includes(n.id))assert.ok(!(x>n.position.x&&x<n.position.x+NODE_SIZE&&y>n.position.y&&y<n.position.y+NODE_SIZE),'route crosses '+n.id);
  }
 }
}
test('equal fanout shares a trunk; directions and access metadata keep separate ports',()=>{
 const nodes=[node('a',0,0),node('b',300,0),node('c',300,180)];
 const edges=[edge('ab','a','b'),edge('ac','a','c'),edge('ar','a','b','read'),edge('ba','b','a'),edge('tick','a','b','write',['tick'])];
 const original=structuredClone(edges),plan=planPorts(nodes,edges);
 assert.deepEqual(plan.get('ab').source,plan.get('ac').source);
 for(const id of ['ar','ba','tick'])assert.notDeepEqual(plan.get('ab').source,id==='ba'?plan.get(id).target:plan.get(id).source);
 assert.equal(planPorts([node('a',0,0),node('b',0,300)],[edges[0]]).get('ab').source.side,'bottom');
 assert.deepEqual(edges,original);
});
test('libavoid shares a real trunk, avoids an obstacle and updates a moved obstacle',async()=>{
 const nodes=[node('a',0,0),node('b',360,0),node('c',360,160),node('block',180,0)],edges=[edge('ab','a','b'),edge('ac','a','c')];
 const router=sceneRouter();try{
  const routes=await router.route(routingGraph(nodes,edges));assert.equal(routes.size,2);assertClear(routes,nodes,edges);
  assert.deepEqual(points(routes.get('ab')).slice(0,2),points(routes.get('ac')).slice(0,2));
  nodes[3].position.y=-100;
  const moved=await router.route(routingGraph(nodes,edges));assertClear(moved,nodes,edges);assert.notDeepEqual(moved.get('ab'),routes.get('ab'));
 }finally{router.destroy();}
});
function straightCrossings(nodes,edges){
 const byId=new Map(nodes.map(n=>[n.id,n.position])),cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);let count=0;
 for(let i=0;i<edges.length;i++)for(let j=i+1;j<edges.length;j++){
  const e=edges[i],f=edges[j];if([e.source,e.target].some(n=>n===f.source||n===f.target))continue;
  const [a,b,c,d]=[e.source,e.target,f.source,f.target].map(n=>byId.get(n));
  if(cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0)count++;
 }return count;
}
test('ELK reduces crossed node ordering and only returns selected positions, away from fixed obstacles',async()=>{
 const nodes=[node('a',0,0),node('b',0,300),node('c',400,300),node('d',400,0),node('sink',800,150)];
 const edges=[edge('ac','a','c'),edge('bd','b','d'),edge('cs','c','sink'),edge('ds','d','sink')],before=structuredClone(nodes);
 const positions=await arrangeGraph(nodes,edges,new ELK());
 const arranged=nodes.map(n=>({...n,position:positions[n.id]}));
 assert.ok(straightCrossings(nodes,edges)>straightCrossings(arranged,edges));assert.deepEqual(nodes,before);
 const fixed=node('fixed',0,0),partial=await arrangeGraph(nodes.slice(0,2),edges,new ELK(),[fixed]);
 assert.deepEqual(Object.keys(partial).sort(),['a','b']);
 for(const p of Object.values(partial))assert.ok(p.x+NODE_SIZE<=0||p.x>=NODE_SIZE||p.y+NODE_SIZE<=0||p.y>=NODE_SIZE);
});
