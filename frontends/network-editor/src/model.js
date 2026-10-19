export const clone=value=>structuredClone(value);
export function edgesOf(document){
  return document.network.nodes.flatMap(node=>[...node.connections.interfaces.map((link,index)=>({id:`${node.node_id}|${index}`,source:node.node_id,target:link.target_node_id,index,metadata:link.metadata})),...(node.type==='subnode'&&node.parameters.parent_id?[{id:'ownership:'+node.node_id,source:node.parameters.parent_id,target:node.node_id,ownership:true,metadata:{channels:[],attributes:{}}}]:[])]);
}
export function nodeKind(node){
  if(node.type==='subnode')return '亚节点';
  if(node.modules['world.resident'])return '居民';
  if(node.modules['world.address'])return '场所';
  if(node.type==='agent')return 'Agent';
  if(node.type==='text_file')return '文本';
  if(node.type==='pulse')return '脉冲';
  if(['value','csv','sqlite','knowledge_collection','llamaindex'].includes(node.type))return '数据';
  if(node.modules['context.sources'])return '上下文';
  if(Object.keys(node.modules).some(x=>x.startsWith('world.')))return '业务';
  return '节点';
}
export const colors={'居民':'#78d8bc','Agent':'#78d8bc','场所':'#8fb7f5','文本':'#d8c080','脉冲':'#c5a7f0','数据':'#d8c080','上下文':'#d8c080','业务':'#a4afc0','节点':'#a4afc0','亚节点':'#bc9cdf'};
export function layoutNodes(document,saved={}){
  const counters={},positions={};
  for(const node of document.network.nodes){
    const kind=nodeKind(node);if(kind==='文本')continue;
    if(kind==='亚节点'){positions[node.node_id]={x:0,y:0};continue;}
    const column={'场所':0,'业务':1,'居民':2,'Agent':2,'脉冲':3,'节点':3,'数据':4,'上下文':4}[kind];
    const row=counters[column]??0;counters[column]=row+1;
    positions[node.node_id]={x:column*270,y:row*115};
  }
  // Keep supporting documents in a compact grid below the active network.
  const documentRow=Math.max(0,...Object.values(counters))+1;let documentIndex=0;
  const byId=new Map(document.network.nodes.map(n=>[n.node_id,n]));const placed={};
  const position=(node,seen=new Set())=>{if(seen.has(node.node_id))return saved[node.node_id]??{x:0,y:0};seen.add(node.node_id);if(placed[node.node_id])return placed[node.node_id];if(node.type==='subnode'&&byId.has(node.parameters.parent_id)){const parent=byId.get(node.parameters.parent_id),base=position(parent,seen),siblings=document.network.nodes.filter(n=>n.type==='subnode'&&n.parameters.parent_id===parent.node_id),index=siblings.indexOf(node);return placed[node.node_id]=saved[node.node_id]??{x:base.x+155,y:base.y+index*64};}return placed[node.node_id]=saved[node.node_id]??positions[node.node_id];};
  return document.network.nodes.map(node=>{
    const kind=nodeKind(node);
    if(kind==='文本'){positions[node.node_id]={x:(documentIndex%5)*270,y:(documentRow+Math.floor(documentIndex/5))*115};documentIndex++;}
    return {id:node.node_id,type:'network',width:node.type==='subnode'?106:92,height:node.type==='subnode'?38:92,measured:{width:node.type==='subnode'?106:92,height:node.type==='subnode'?38:92},position:position(node),data:{node,kind}};
  });
}
export function removeNode(document,id){
  const next=clone(document),removed=new Set([id]);for(let size=-1;size!==removed.size;){size=removed.size;for(const n of next.network.nodes)if(n.type==='subnode'&&removed.has(n.parameters.parent_id))removed.add(n.node_id);}next.network.nodes=next.network.nodes.filter(n=>!removed.has(n.node_id));
  if(next.network.delegations)next.network.delegations=next.network.delegations.filter(g=>g.source!==id&&g.target!==id);
  for(const n of next.network.nodes){
    for(const d of Object.keys(n.connections))n.connections[d]=n.connections[d].filter(e=>!removed.has(e.target_node_id));
    if(n.management_parent_id===id)n.management_parent_id=null;
  }
  return next;
}
const edgeChannels=edge=>edge.metadata.channels.length?edge.metadata.channels:[null];
export const connectionChannels=edges=>[...new Set(edges.filter(e=>!e.ownership).flatMap(edgeChannels))];
export function filterGraph(nodes,edges,{query='',kinds=null,channels=null,local=null}){
  const reached=local?new Set([local.actor,...Object.values(local.paths).flat().map(x=>x.id)]):null;
  const selectedEdges=edges.filter(e=>e.ownership||channels===null||((e.metadata.attributes?.channel_mode==='deny')?channels.some(c=>!e.metadata.channels.includes(c)):edgeChannels(e).some(c=>channels.includes(c))));
  const restrictedChannels=channels!==null&&(!channels.length||!connectionChannels(edges).every(c=>channels.includes(c)));
  const channelNodes=restrictedChannels?new Set(selectedEdges.flatMap(e=>[e.source,e.target])):null;
  const visible=nodes.filter(n=>(kinds===null||kinds.includes(n.data.kind))&&(!query||`${n.id} ${n.data.node.name}`.toLowerCase().includes(query.toLowerCase()))&&(!reached||reached.has(n.id))&&(!channelNodes||channelNodes.has(n.id)));
  const traversed=local?new Map():null;
  if(local)for(const item of Object.values(local.paths).flat())for(let i=1;i<item.path.length;i++){const pair=`${item.path[i-1]}|${item.path[i]}`,grants=traversed.get(pair)??new Set();for(const channel of item.channels)grants.add(channel);traversed.set(pair,grants);}
  const ids=new Set(visible.map(n=>n.id));return {nodes:visible,edges:selectedEdges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&(!traversed||(e.metadata.channels.some(c=>traversed.get(`${e.source}|${e.target}`)?.has(c)))))};
}

// Newly visible items rise above existing ones, including re-enabled filters.
export function stackVisible(previous,nodes,edges){
 const next={serial:previous?.serial??0,nodes:{},edges:{}};
 for(const [kind,items] of [['edges',edges],['nodes',nodes]])for(const item of items)
  next[kind][item.id]=previous?.[kind]?.[item.id]??++next.serial;
 return next;
}

export function channelColor(channels){
 let hash=0;
 for(const c of [...channels].sort().join('|'))hash=(hash*31+c.charCodeAt(0))>>>0;
 return channels.length?`hsl(${hash%360} 38% 65%)`:'#8193a5';
}
