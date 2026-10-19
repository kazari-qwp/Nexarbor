// 按屏幕像素命中真实 SVG 路径；缩放不会改变候选选择的容差。
export function segmentDistance(point,a,b){const dx=b.x-a.x,dy=b.y-a.y,t=Math.max(0,Math.min(1,((point.x-a.x)*dx+(point.y-a.y)*dy)/(dx*dx+dy*dy||1)));return Math.hypot(point.x-a.x-t*dx,point.y-a.y-t*dy);}
export function hitRenderedEdges(container,point,visible,tolerance=7){
 const hits=[];
 for(const edge of container.querySelectorAll('.react-flow__edge')){
  const id=edge.dataset.id;if(!visible.has(id))continue;
  const path=edge.querySelector('.react-flow__edge-path');if(!path)continue;
  const box=path.getBoundingClientRect();if(point.x<box.left-tolerance||point.x>box.right+tolerance||point.y<box.top-tolerance||point.y>box.bottom+tolerance)continue;
  const m=path.getScreenCTM();if(!m)continue;
  const length=path.getTotalLength(),count=Math.max(1,Math.min(8192,Math.ceil(length*Math.max(Math.hypot(m.a,m.b),Math.hypot(m.c,m.d))/3)));
  const at=i=>{const p=path.getPointAtLength(length*i/count);return {x:m.a*p.x+m.c*p.y+m.e,y:m.b*p.x+m.d*p.y+m.f};};
  let last=at(0),distance=Infinity;
  for(let i=1;i<=count;i++){const next=at(i);distance=Math.min(distance,segmentDistance(point,last,next));if(distance<=tolerance)break;last=next;}
  if(distance<=tolerance)hits.push(id);
 }
 return hits;
}
