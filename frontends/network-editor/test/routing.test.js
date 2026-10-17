import test from 'node:test';
import assert from 'node:assert/strict';
import ELK from 'elkjs/lib/elk.bundled.js';
import {NODE_SIZE,routingGraph} from '../src/routing.js';
import {sceneRouter} from '../src/route-session.js';
import {arrangeGraph} from '../src/layout.js';
const node=(id,x,y)=>({id,position:{x,y},measured:{width:NODE_SIZE,height:NODE_SIZE},data:{}});
const edge=(id,source,target,channels=['links'])=>({id,source,target,metadata:{channels}});
const points=route=>[route.sourcePoint,...route.bendPoints,route.targetPoint];
function assertClear(routes,nodes,edges){
 for(const [id,route] of routes){const e=edges.find(e=>e.id===id),p=points(route);
  for(let i=1;i<p.length;i++)for(let t=0;t<=1;t+=.025){const x=p[i-1].x+(p[i].x-p[i-1].x)*t,y=p[i-1].y+(p[i].y-p[i-1].y)*t;
   for(const n of nodes)if(![e.source,e.target].includes(n.id))assert.ok(!(x>n.position.x&&x<n.position.x+NODE_SIZE&&y>n.position.y&&y<n.position.y+NODE_SIZE),'route crosses '+n.id);
  }
 }
}
test('router receives free endpoints rather than fixed center-based pins',()=>{
 const graph=routingGraph([node('a',0,0),node('b',300,0)],[edge('ab','a','b')]);
 assert.equal(graph.children[0].ports,undefined);assert.equal(graph.edges[0].sourcePort,undefined);
});
test('libavoid chooses valid endpoints, avoids an obstacle and updates a moved obstacle',async()=>{
 const nodes=[node('a',0,0),node('b',360,0),node('c',360,160),node('block',180,0)],edges=[edge('ab','a','b'),edge('ac','a','c')];
 const router=sceneRouter();try{
  const routes=await router.route(routingGraph(nodes,edges));assert.equal(routes.size,2);assertClear(routes,nodes,edges);
  for(const route of routes.values())assert.ok(points(route).length<=8);
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

test('five-node pulse loop has bounded lengths and bends without hand-built trunks',async()=>{
 const nodes=[node('time',100,500),node('alice',490,670),node('bob',550,460),node('pulse',900,80),node('save',1000,215)];
 const edges=[['pulse','time'],['time','alice'],['time','bob'],['alice','save'],['bob','save'],['save','pulse']].map(([a,b])=>edge(a+b,a,b));
 const router=sceneRouter();try{
  const routes=await router.route(routingGraph(nodes,edges));assertClear(routes,nodes,edges);
  for(const [id,r] of routes){const p=points(r),length=p.slice(1).reduce((n,b,i)=>n+Math.abs(b.x-p[i].x)+Math.abs(b.y-p[i].y),0),direct=Math.abs(p[0].x-p.at(-1).x)+Math.abs(p[0].y-p.at(-1).y);
   assert.ok(length<=direct*2+NODE_SIZE*2,`${id}: excessive detour ${length}/${direct}`);assert.ok(p.length<=8,`${id}: excessive bends`);
   for(let i=2;i<p.length;i++){const a=p[i-2],b=p[i-1],c=p[i];assert.ok(!(a.x===b.x&&b.x===c.x&&(b.y-a.y)*(c.y-b.y)<0||a.y===b.y&&b.y===c.y&&(b.x-a.x)*(c.x-b.x)<0),id+': reverses on itself');}
  }
 }finally{router.destroy();}
});
