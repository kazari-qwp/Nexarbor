import {denseLayout} from './dense-layout.js';
export async function placeNetwork(scene,elk){
 const original=new Map(scene.nodes.map(n=>[n.ref,n]));
 const placed=await denseLayout(scene.nodes.map(n=>({id:n.ref,width:n.type==='module_view'?92:140,height:n.type==='module_view'?66:164})),[...scene.ownership.map(e=>({...e,ownership:true})),...scene.edges],elk);
 return placed.map(n=>({...original.get(n.id),x:n.x+14,y:n.y+30,width:original.get(n.id).type==='module_view'?72:112,height:original.get(n.id).type==='module_view'?28:112}));
}
