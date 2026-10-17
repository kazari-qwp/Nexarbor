// Presentation geometry only. Network edges retain their original IDs/direction.
// Shared-side port spacing follows Archify's deterministic endpoint-spread idea.
export const NODE_SIZE=92;
export function nodeBox(node){
  const width=node.measured?.width??node.width??NODE_SIZE,height=node.measured?.height??node.height??NODE_SIZE;
  return {id:node.id,x:node.position.x,y:node.position.y,width,height,cx:node.position.x+width/2,cy:node.position.y+height/2};
}
export function planPorts(nodes,edges){
  const boxes=new Map(nodes.map(n=>[n.id,nodeBox(n)])),groups=new Map(),plans=new Map();
  const add=(edge,end,box,other,side)=>{
    const key=box.id+'|'+side;const items=groups.get(key)??[];
    items.push({edge,end,box,other,side});groups.set(key,items);
  };
  for(const edge of edges){
    const from=boxes.get(edge.source),to=boxes.get(edge.target);if(!from||!to)continue;
    const dx=to.cx-from.cx,dy=to.cy-from.cy;
    const horizontal=Math.abs(dx)>=Math.abs(dy);
    const source=from===to?'right':horizontal?(dx>=0?'right':'left'):(dy>=0?'bottom':'top');
    const target=from===to?'top':horizontal?(dx>=0?'left':'right'):(dy>=0?'top':'bottom');
    plans.set(edge.id,{});add(edge,'source',from,to,source);add(edge,'target',to,from,target);
  }
  for(const items of groups.values()){
    const vertical=items[0].side==='left'||items[0].side==='right';
    items.sort((a,b)=>(vertical?a.other.cy-b.other.cy:a.other.cx-b.other.cx)||((a.edge.id+'|'+a.end).localeCompare(b.edge.id+'|'+b.end)));
    // Spread along a bounded arc on the circular node, away from corners.
    // Only equal connection semantics share a port/trunk. Incoming and outgoing
    // edges remain separate, as do channels, visibility and access parameters.
    const buckets=new Map();
    for(const item of items){
      const metadata=item.edge.metadata??{};
      const key=JSON.stringify([item.end,item.edge.direction,Object.keys(metadata).sort().map(k=>[k,k==='channels'?[...metadata[k]].sort():metadata[k]])]);
      const bucket=buckets.get(key)??[];bucket.push(item);buckets.set(key,bucket);
    }
    const step=Math.min(.22,1.2/Math.max(1,buckets.size-1));
    [...buckets.values()].forEach((bucket,index)=>{
      const item=bucket[0];
      const base={right:0,bottom:Math.PI/2,left:Math.PI,top:-Math.PI/2}[item.side];
      const offset=(index-(buckets.size-1)/2)*step;
      const angle=base+((item.side==='left'||item.side==='bottom')?-offset:offset);
      const point={x:item.box.cx+Math.cos(angle)*item.box.width/2,y:item.box.cy+Math.sin(angle)*item.box.height/2,side:item.side,portId:JSON.stringify([item.box.id,item.side,item.end,item.edge.direction,item.edge.metadata])};
      for(const member of bucket)plans.get(member.edge.id)[member.end]=point;
    });
  }
  return plans;
}

export function routingGraph(nodes,edges,ports=planPorts(nodes,edges)){
  const children=nodes.map(node=>{const b=nodeBox(node);return {id:node.id,x:b.x,y:b.y,width:b.width,height:b.height,ports:[]};});
  const boxes=new Map(children.map(n=>[n.id,n]));
  const connections=[];
  for(const edge of edges){
    const endpoints=ports.get(edge.id);if(!endpoints)continue;
    for(const end of ['source','target']){
      const point=endpoints[end],box=boxes.get(edge[end]);
      if(!box.ports.some(p=>p.id===point.portId))box.ports.push({id:point.portId,
        x:point.side==='left'?0:point.side==='right'?box.width:point.x-box.x,
        y:point.side==='top'?0:point.side==='bottom'?box.height:point.y-box.y,width:0,height:0,
        layoutOptions:{'elk.port.side':{left:'WEST',right:'EAST',top:'NORTH',bottom:'SOUTH'}[point.side]}});
    }
    connections.push({id:edge.id,source:edge.source,target:edge.target,sourcePort:endpoints.source.portId,targetPort:endpoints.target.portId});
  }
  return {id:'scene',children,edges:connections};
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
  if(!node)return point;
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
