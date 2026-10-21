// Presentation geometry only. Network edges retain their original IDs/direction.
// Shared-side port spacing follows Archify's deterministic endpoint-spread idea.
export const NODE_SIZE=84;
export function nodeBox(node){
  const width=node.measured?.width??node.width??NODE_SIZE,height=node.measured?.height??node.height??NODE_SIZE;
  return {id:node.id,x:node.position.x,y:node.position.y,width,height,cx:node.position.x+width/2,cy:node.position.y+height/2};
}
// Let libavoid choose among the four shape sides. Fixed pins based only on
// relative centers can force a long detour when the surrounding graph changes.
export function routingGraph(nodes,edges){
  return {id:'scene',children:nodes.map(node=>{const b=nodeBox(node);return {id:node.id,x:b.x,y:b.y,width:b.width,height:b.height};}),
    edges:edges.map(edge=>({id:edge.id,source:edge.source,target:edge.target}))};
}

// Round the orthogonal polyline supplied by the routing library; no path search.
export function roundedRoute(points,radius=8){
  if(points.length<2)return '';
  let path=`M ${points[0].x} ${points[0].y}`;
  for(let i=1;i<points.length-1;i++){
    const a=points[i-1],b=points[i],c=points[i+1],before=Math.hypot(b.x-a.x,b.y-a.y),after=Math.hypot(c.x-b.x,c.y-b.y);
    if(!before||!after)continue;
    const r=Math.min(radius,before/2,after/2);
    path+=` L ${b.x+(a.x-b.x)*r/before} ${b.y+(a.y-b.y)*r/before} Q ${b.x} ${b.y} ${b.x+(c.x-b.x)*r/after} ${b.y+(c.y-b.y)*r/after}`;
  }
  return path+` L ${points.at(-1).x} ${points.at(-1).y}`;
}

export function circularEndpoint(point,side,node){
  if(!node||node.data?.node?.type==='subnode')return point;
  const b=nodeBox(node);
  // libavoid may nudge a terminal along the shape border. Follow its computed
  // coordinate rather than pulling it back to the originally requested pin.
  if(side==='east'||side==='west'){
    const offset=Math.max(-1,Math.min(1,(point.y-b.cy)/(b.height/2)));
    return {x:b.cx+(side==='east'?1:-1)*b.width/2*Math.sqrt(1-offset*offset),y:point.y};
  }
  const offset=Math.max(-1,Math.min(1,(point.x-b.cx)/(b.width/2)));
  return {x:point.x,y:b.cy+(side==='south'?1:-1)*b.height/2*Math.sqrt(1-offset*offset)};
}
