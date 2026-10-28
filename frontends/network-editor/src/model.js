import {edgeMetadata} from '../../shared/graph/links.js';
import {nodeDimensions} from './graph-appearance.js';
export const clone=value=>structuredClone(value);
export function edgesOf(document){
 return document.network.nodes.flatMap(node=>(node.links??[]).map((link,index)=>({id:`${node.node_id}|${index}`,source:node.node_id,target:link.target_id,index,metadata:edgeMetadata(link)})));
}
export function nodeKind(node){
  const modules=Object.fromEntries((node.tables?.modules??[]).map(item=>[item.module_id,item]));
  if(modules['world.resident'])return '居民';
  if(modules['world.address'])return '场所';
  if(node.type==='agent')return 'Agent';
  if(node.type==='markdown')return '文本';
  if(node.type==='pulse')return '脉冲';
  if(['value','csv','sqlite','knowledge_collection','knowledge_catalog','llamaindex'].includes(node.type))return '数据';
  if(modules['context.sources'])return '上下文';
  if(Object.keys(modules).some(x=>x.startsWith('world.')))return '业务';
  return '节点';
}
export const colors={'居民':'#3ce79e','Agent':'#3ce79e','场所':'#7bafff','文本':'#ffcf59','脉冲':'#ba8cff','数据':'#ffcf59','上下文':'#ffcf59','业务':'#b6d8f0','节点':'#b6d8f0','亚节点':'#d08fff'};
export function layoutNodes(document,saved={}){
  const counters={},positions={};
  for(const node of document.network.nodes){
    const kind=nodeKind(node);if(kind==='文本')continue;
    const column={'场所':0,'业务':1,'居民':2,'Agent':2,'脉冲':3,'节点':3,'数据':4,'上下文':4}[kind];
    const row=counters[column]??0;counters[column]=row+1;
    positions[node.node_id]={x:column*270,y:row*115};
  }
  // Keep supporting documents in a compact grid below the active network.
  const documentRow=Math.max(0,...Object.values(counters))+1;let documentIndex=0;
  const placed={};
  const position=(node,seen=new Set())=>{if(seen.has(node.node_id))return saved[node.node_id]??{x:0,y:0};seen.add(node.node_id);if(placed[node.node_id])return placed[node.node_id];return placed[node.node_id]=saved[node.node_id]??positions[node.node_id];};
  return document.network.nodes.map(node=>{
    const kind=nodeKind(node);
    if(kind==='文本'){positions[node.node_id]={x:(documentIndex%5)*270,y:(documentRow+Math.floor(documentIndex/5))*115};documentIndex++;}
    return {id:node.node_id,type:'network',...nodeDimensions(node.type),measured:nodeDimensions(node.type),position:position(node),data:{node,kind}};
  });
}
export function removeNode(document,id){
 const next=clone(document);next.network.nodes=next.network.nodes.filter(node=>node.node_id!==id);
 for(const node of next.network.nodes)node.links=(node.links??[]).filter(link=>link.target_id!==id);
 if(next.network.properties){delete next.network.properties[id];for(const value of Object.values(next.network.properties))if(value.management_parent_id===id)value.management_parent_id=null;}
 return next;
}
const edgeChannels=edge=>edge.metadata.channels.length?edge.metadata.channels:[null];
export const connectionChannels=edges=>[...new Set(edges.filter(e=>!e.ownership).flatMap(edgeChannels))];
export function filterGraph(nodes,edges,{query='',kinds=null,channels=null,local=null}){
  const reached=local?new Set([local.actor,...Object.values(local.reachable).flat().map(x=>x.id)]):null;
  const hosts=new Map(nodes.map(node=>[node.id,node.data.host?.node_id??node.id]));
  const views=local?Object.entries(local.reachable).map(([channel,items])=>[channel,new Set([local.actor,...items.map(item=>item.id)])]):null;
  const selectedEdges=edges.filter(edge=>{
    if(edge.ownership)return true;
    const allows=channel=>edge.metadata.attributes?.channel_mode==='deny'?!edge.metadata.channels.includes(channel):edgeChannels(edge).includes(channel);
    if(channels!==null&&!channels.some(allows))return false;
    return !views||views.some(([channel,ids])=>allows(channel)&&ids.has(hosts.get(edge.source))&&ids.has(hosts.get(edge.target)));
  });
  const restrictedChannels=channels!==null&&(!channels.length||!connectionChannels(edges).every(c=>channels.includes(c)));
  const channelNodes=restrictedChannels?new Set(selectedEdges.filter(e=>!e.ownership).flatMap(e=>[e.source,e.target])):null;
  if(channelNodes)for(const node of nodes)if(node.data.host&&channelNodes.has(node.id))channelNodes.add(node.data.host.node_id);
  const visible=nodes.filter(n=>(kinds===null||kinds.includes(n.data.kind))&&(!query||`${n.id} ${n.data.node.name}`.toLowerCase().includes(query.toLowerCase()))&&(!reached||reached.has(n.data.host?.node_id??n.id))&&(!channelNodes||channelNodes.has(n.id)));
  const ids=new Set(visible.map(n=>n.id));return {nodes:visible,edges:selectedEdges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
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
