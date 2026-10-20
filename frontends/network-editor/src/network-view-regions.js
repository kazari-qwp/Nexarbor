// Every detail window uses the same world coordinates as its overview.
// Overlap preserves crossings and nearby landmarks when moving between windows.
export function planRegions(bounds, size, {minimumScale=.75, detailScale=1.1, overlap=.28}={}){
 const [x,y,width,height]=bounds,available={width:size.width-40,height:size.height-168};
 const scale=Math.min(available.width/width,available.height/height);
 if(scale>=minimumScale)return {scale,regions:[]};
 const spanX=Math.min(width,available.width/detailScale),spanY=Math.min(height,available.height/detailScale);
 const columns=Math.max(1,Math.ceil((width-spanX)/(spanX*(1-overlap)))+1),rows=Math.max(1,Math.ceil((height-spanY)/(spanY*(1-overlap)))+1);
 const stepX=columns>1?(width-spanX)/(columns-1):0,stepY=rows>1?(height-spanY)/(rows-1):0;
 const regions=[];for(let row=0;row<rows;row++)for(let col=0;col<columns;col++)regions.push({id:'R'+(regions.length+1),row:row+1,column:col+1,bounds:[x+stepX*col,y+stepY*row,spanX,spanY]});
 return {scale,regions};
}
export function visibleRefs(nodes,bounds){
 const [x,y,w,h]=bounds;
 return nodes.filter(n=>n.x+n.width>=x&&n.x<=x+w&&n.y+n.height+26>=y&&n.y-30<=y+h).map(n=>n.ref);
}
export function regionAnchors(nodes,bounds){
 const [x,y,w,h]=bounds,priority=n=>n.type==='pulse'?0:n.type==='agent'?1:n.type==='subnode'?3:n.type==='text_file'?4:2;
 return nodes.filter(n=>n.x>=x&&n.x+n.width<=x+w&&n.y>=y&&n.y+n.height<=y+h).sort((a,b)=>priority(a)-priority(b)||a.y-b.y).slice(0,3).map(n=>({ref:n.ref,name:n.name}));
}
