// Observation-only placement. IDs, ownership and graph semantics never change.
// Treat ownership as a shorter local relationship; do not infer application roles.
const width=140,height=n=>n.type==='subnode'?86:164;
const extent=nodes=>({width:Math.max(1,...nodes.map(n=>n.x+n.width))-Math.min(0,...nodes.map(n=>n.x)),height:Math.max(1,...nodes.map(n=>n.y+n.height))-Math.min(0,...nodes.map(n=>n.y))});
export async function placeNetwork(scene,elk){
 if(!scene.nodes.length)return [];
 const seen=new Set(),edges=[...scene.ownership.map(e=>({...e,local:true})),...scene.edges].filter(e=>{
  const key=[e.source,e.target].sort().join('|');if(e.source===e.target||seen.has(key))return false;seen.add(key);return true;
 }).map((e,i)=>({id:String(i),sources:[e.source],targets:[e.target],layoutOptions:{'elk.stress.desiredEdgeLength':e.local?'100':'160'}}));
 let graph=await elk.layout({id:'observation',layoutOptions:{'elk.algorithm':'stress','elk.randomSeed':'1','elk.stress.iterationLimit':'160','elk.aspectRatio':'1.35'},children:scene.nodes.map(n=>({id:n.ref,width,height:height(n)})),edges});
 graph=await elk.layout({...graph,layoutOptions:{'elk.algorithm':'sporeOverlap','elk.randomSeed':'1','elk.spacing.nodeNode':'16','elk.overlapRemoval.runScanline':'true'}});
 let placed=graph.children;const box=extent(placed),ratio=box.width/box.height;
 // A chain can remain a long strip even in a distance-based layout. Fold its
 // existing spatial order into rows rather than spending most pixels on air.
 if(placed.length>=8&&(ratio>2.1||ratio<.6)){
  const horizontal=box.width>=box.height,ordered=[...placed].sort((a,b)=>(horizontal?a.x-b.x:a.y-b.y)||(horizontal?a.y-b.y:a.x-b.x));
  const columns=Math.max(2,Math.round(Math.sqrt(placed.length*1.35*180/width)));
  placed=ordered.map((n,i)=>{const row=Math.floor(i/columns),col=i%columns;return {...n,x:(row%2?columns-col-1:col)*(width+28),y:row*190};});
 }
 const original=new Map(scene.nodes.map(n=>[n.ref,n]));
 return placed.map(n=>({...original.get(n.id),x:n.x+14,y:n.y+30,width:original.get(n.id).type==='subnode'?106:112,height:original.get(n.id).type==='subnode'?38:112}));
}
