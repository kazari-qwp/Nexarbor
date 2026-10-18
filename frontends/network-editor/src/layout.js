import {NODE_SIZE} from './routing.js';
// ELK performs layer ordering/crossing minimization. This only translates models.
export async function arrangeGraph(nodes,edges,elk,obstacles=[],{compact=false}={}){
  if(!nodes.length)return {};
  const ids=new Set(nodes.map(n=>n.id));
  const result=await elk.layout({id:'layout',layoutOptions:{'elk.algorithm':'layered','elk.direction':'RIGHT','elk.edgeRouting':'ORTHOGONAL',
    'elk.layered.crossingMinimization.strategy':'LAYER_SWEEP','elk.layered.thoroughness':'24',
    'elk.layered.mergeEdges':'true','elk.spacing.nodeNode':compact?'36':'64','elk.layered.spacing.nodeNodeBetweenLayers':compact?'72':'140',
    'elk.spacing.componentComponent':compact?'56':'90','elk.randomSeed':'1'},
    children:nodes.map(n=>({id:n.id,width:NODE_SIZE,height:NODE_SIZE})),
    edges:edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({id:e.id,sources:[e.source],targets:[e.target]})),
  });
  const anchor={x:Math.min(...nodes.map(n=>n.position.x)),y:Math.min(...nodes.map(n=>n.position.y))};
  const origin={x:Math.min(...result.children.map(n=>n.x)),y:Math.min(...result.children.map(n=>n.y))};
  const boxes=result.children.map(n=>({...n,x:n.x-origin.x,y:n.y-origin.y}));
  const width=Math.max(...boxes.map(n=>n.x+n.width)),height=Math.max(...boxes.map(n=>n.y+n.height));
  const gap=40,xs=new Set([anchor.x]),ys=new Set([anchor.y]);
  for(const n of obstacles){xs.add(n.position.x-width-gap);xs.add(n.position.x+NODE_SIZE+gap);ys.add(n.position.y-height-gap);ys.add(n.position.y+NODE_SIZE+gap);}
  const candidates=[...xs].flatMap(x=>[...ys].map(y=>({x,y}))).sort((a,b)=>((a.x-anchor.x)**2+(a.y-anchor.y)**2)-((b.x-anchor.x)**2+(b.y-anchor.y)**2));
  const offset=candidates.find(p=>boxes.every(b=>obstacles.every(n=>b.x+p.x+b.width+gap<=n.position.x||b.x+p.x>=n.position.x+NODE_SIZE+gap||b.y+p.y+b.height+gap<=n.position.y||b.y+p.y>=n.position.y+NODE_SIZE+gap)))??anchor;
  return Object.fromEntries(boxes.map(n=>[n.id,{x:n.x+offset.x,y:n.y+offset.y}]));
}
