// Undirected distances preserve neighbourhoods; ownership stays a short local relation.
// This is presentation only: no edge direction, ID or node ownership is changed.
export async function denseLayout(nodes,edges,elk){
 if(!nodes.length)return [];
 const ids=new Set(nodes.map(n=>n.id)),seen=new Set();
 const links=edges.filter(e=>{
  if(!ids.has(e.source)||!ids.has(e.target)||e.source===e.target)return false;
  const key=[e.source,e.target].sort().join('|');if(seen.has(key))return false;seen.add(key);return true;
 }).map((e,i)=>({id:String(i),sources:[e.source],targets:[e.target],layoutOptions:{'elk.stress.desiredEdgeLength':e.ownership?'100':'155'}}));
 let graph=await elk.layout({id:'dense',layoutOptions:{'elk.algorithm':'stress','elk.randomSeed':'1','elk.stress.iterationLimit':'160','elk.aspectRatio':'1.35'},children:nodes,edges:links});
 graph=await elk.layout({...graph,layoutOptions:{'elk.algorithm':'sporeOverlap','elk.randomSeed':'1','elk.spacing.nodeNode':'28','elk.overlapRemoval.runScanline':'true'}});
 let placed=graph.children;
 const minX=Math.min(...placed.map(n=>n.x)),minY=Math.min(...placed.map(n=>n.y));
 const width=Math.max(...placed.map(n=>n.x+n.width))-minX,height=Math.max(...placed.map(n=>n.y+n.height))-minY;
 if(placed.length>=8&&(width/height>2.1||width/height<.6)){
  const horizontal=width>=height,ordered=[...placed].sort((a,b)=>(horizontal?a.x-b.x:a.y-b.y)||(horizontal?a.y-b.y:a.x-b.x));
  const cellW=Math.max(...placed.map(n=>n.width))+32,cellH=Math.max(...placed.map(n=>n.height))+42;
  const columns=Math.max(2,Math.round(Math.sqrt(placed.length*1.35*cellH/cellW)));
  placed=ordered.map((n,i)=>{const row=Math.floor(i/columns),col=i%columns;return {...n,x:(row%2?columns-col-1:col)*cellW,y:row*cellH};});
 }
 return placed;
}
