export const clone=value=>structuredClone(value);
export function edgesOf(document){
  return document.network.nodes.flatMap(node=>Object.entries(node.connections).flatMap(([direction,links])=>links.map((link,index)=>({
    id:`${node.node_id}|${direction}|${index}`,source:node.node_id,target:link.target_node_id,
    direction:direction==='read_interfaces'?'read':'write',index,metadata:link.metadata,
  }))));
}
export function nodeKind(node){
  if(node.modules['world.resident'])return '居民';
  if(node.modules['world.address'])return '场所';
  if(node.type==='agent')return 'Agent';
  if(node.type==='text_file')return '文本';
  if(node.type==='pulse')return '脉冲';
  if(node.modules['context.sources'])return '上下文';
  if(Object.keys(node.modules).some(x=>x.startsWith('world.')))return '业务';
  return '节点';
}
export const colors={'居民':'#78d8bc','Agent':'#78d8bc','场所':'#8fb7f5','文本':'#d8c080','脉冲':'#c5a7f0','上下文':'#d8c080','业务':'#a4afc0','节点':'#a4afc0'};
export function layoutNodes(document,saved={}){
  const counters={},positions={};
  for(const node of document.network.nodes){
    const kind=nodeKind(node);if(kind==='文本')continue;
    const column={'场所':0,'业务':1,'居民':2,'Agent':2,'脉冲':3,'节点':3,'上下文':4}[kind];
    const row=counters[column]??0;counters[column]=row+1;
    positions[node.node_id]={x:column*270,y:row*115};
  }
  // Keep supporting documents in a compact grid below the active network.
  const documentRow=Math.max(0,...Object.values(counters))+1;let documentIndex=0;
  return document.network.nodes.map(node=>{
    const kind=nodeKind(node);
    if(kind==='文本'){positions[node.node_id]={x:(documentIndex%5)*270,y:(documentRow+Math.floor(documentIndex/5))*115};documentIndex++;}
    return {id:node.node_id,type:'network',position:saved[node.node_id]??positions[node.node_id],data:{node,kind}};
  });
}
export function removeNode(document,id){
  if(id==='root')throw new Error('根节点不能删除');
  const next=clone(document);next.network.nodes=next.network.nodes.filter(n=>n.node_id!==id);
  for(const n of next.network.nodes){
    for(const d of Object.keys(n.connections))n.connections[d]=n.connections[d].filter(e=>e.target_node_id!==id);
    if(n.management_parent_id===id)n.management_parent_id=null;
  }
  return next;
}
const edgeChannels=edge=>edge.metadata.channels.length?edge.metadata.channels:[null];
export const connectionChannels=edges=>[...new Set(edges.flatMap(edgeChannels))];
export function filterGraph(nodes,edges,{query='',kinds=null,channels=null,local=null,direction='both'}){
  const reached=local?new Set([local.actor,...Object.values(local.paths).flat().map(x=>x.id)]):null;
  const selectedEdges=edges.filter(e=>(direction==='both'||e.direction===direction)&&(channels===null||edgeChannels(e).some(c=>channels.includes(c))));
  const restrictedChannels=channels!==null&&(!channels.length||!connectionChannels(edges).every(c=>channels.includes(c)));
  const channelNodes=restrictedChannels?new Set(selectedEdges.flatMap(e=>[e.source,e.target])):null;
  const visible=nodes.filter(n=>(kinds===null||kinds.includes(n.data.kind))&&(!query||`${n.id} ${n.data.node.name}`.toLowerCase().includes(query.toLowerCase()))&&(!reached||reached.has(n.id))&&(!channelNodes||channelNodes.has(n.id)));
  const traversed=local?new Set(Object.entries(local.paths).flatMap(([d,paths])=>paths.flatMap(p=>p.path.slice(1).map((id,i)=>`${d}|${p.path[i]}|${id}`)))):null;
  const ids=new Set(visible.map(n=>n.id));return {nodes:visible,edges:selectedEdges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&(!traversed||traversed.has(`${e.direction}|${e.source}|${e.target}`)))};
}
