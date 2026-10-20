// Choose a few useful windows, rather than slicing a fixed magnification into
// many nearly identical crops. Bounds always refer to the same overview layout.
export const regionColors=['#43cfff','#ffbd38','#d08fff','#4de59b'];
export function planRegions(bounds,size,{nodes=[],minimumScale=.72,overlap=.2}={}){
 const [x,y,width,height]=bounds,available={width:size.width-40,height:size.height-168};
 const scale=Math.min(available.width/width,available.height/height);
 if(scale>=minimumScale)return {scale,overlap,regions:[]};
 const maxCells=nodes.length?Math.min(36,Math.max(2,Math.ceil(nodes.length/8))):36;
 let best;
 for(let columns=1;columns<=maxCells;columns++)for(let rows=1;rows*columns<=maxCells;rows++){
  if(rows*columns===1)continue;
  // Solve the span from the grid count, so overlap stays 20% even at the end.
  const w=width/(columns-(columns-1)*overlap),h=height/(rows-(rows-1)*overlap);
  const zoom=Math.min(available.width/w,available.height/h);if(zoom<minimumScale)continue;
  let regions=[];for(let row=0;row<rows;row++)for(let col=0;col<columns;col++){
   const box=[x+col*w*(1-overlap),y+row*h*(1-overlap),w,h];
   regions.push({row:row+1,column:col+1,bounds:box,color:regionColors[(col+2*row)%regionColors.length],complete:completeRefs(nodes,box)});
  }
  if(nodes.length){
   regions=regions.filter(r=>r.complete.length);
   if(new Set(regions.flatMap(r=>r.complete)).size!==nodes.length)continue;
   // Drop a sparse window if every node in it is already fully covered nearby.
   for(const r of [...regions].sort((a,b)=>a.complete.length-b.complete.length))if(r.complete.length<10&&r.complete.every(ref=>regions.some(other=>other!==r&&other.complete.includes(ref))))regions=regions.filter(other=>other!==r);
  }
  const repeated=nodes.length?Math.max(0,regions.reduce((n,r)=>n+r.complete.length,0)/nodes.length-1):0;
  const sparse=nodes.length>=20?regions.reduce((n,r)=>n+Math.max(0,10-r.complete.length)/5,0):0;
  const score=regions.length+Math.max(0,.95-zoom)*12+repeated+sparse;
  if(!best||score<best.score)best={score,regions};
 }
 return {scale,overlap,regions:(best?.regions??[]).map((r,i)=>({...r,id:'R'+(i+1)}))};
}
export function visibleRefs(nodes,bounds){
 const [x,y,w,h]=bounds;
 return nodes.filter(n=>n.x+n.width>=x&&n.x<=x+w&&n.y+n.height+26>=y&&n.y-30<=y+h).map(n=>n.ref);
}
export function completeRefs(nodes,bounds){
 const [x,y,w,h]=bounds;
 return nodes.filter(n=>n.x>=x&&n.x+n.width<=x+w&&n.y-30>=y&&n.y+n.height+(n.subnodes?28:4)<=y+h).map(n=>n.ref);
}
export function regionAnchors(nodes,bounds){
 const refs=new Set(completeRefs(nodes,bounds)),priority=n=>n.type==='pulse'?0:n.type==='agent'?1:n.type==='subnode'?3:n.type==='text_file'?4:2;
 return nodes.filter(n=>refs.has(n.ref)).sort((a,b)=>priority(a)-priority(b)||a.y-b.y).slice(0,3).map(n=>({ref:n.ref,name:n.name}));
}
