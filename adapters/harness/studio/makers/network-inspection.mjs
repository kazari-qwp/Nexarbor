// Agent-facing projections of a fixed snapshot; stored graphs stay unchanged.
const clone=structuredClone;
const nonempty=value=>value!=null&&(typeof value==='string'?value.length>0:typeof value!=='object'||Object.keys(value).length>0);
const keys=value=>Object.keys(value??{});
const present=value=>Object.fromEntries(Object.entries(value).filter(([,v])=>nonempty(v)));

export function responseFormat(value='concise'){
 if(!['concise','detailed'].includes(value))throw Error('response_format 仅支持 concise（简略）或 detailed（详细）');
 return value;
}

function nodeSummary(node){
 return present({node_id:node.node_id,name:node.name,type:node.type,description:node.description,
  management_parent_id:node.management_parent_id,
  ...(node.type==='subnode'?{parameters:node.parameters}:{}),
  divergence:node.divergence,module_strength:node.module_strength,
  modules:keys(node.modules),offered_tools:node.offered_tools});
}

function compactEdges(nodes,target){
 const links=nodes.flatMap(node=>(node.connections?.interfaces??[]).flatMap((edge,index)=>{
  if(target&&node.node_id!==target&&edge.target_node_id!==target)return [];
  const metadata=edge.metadata??{};
  return [{id:node.node_id+'|'+index,source:node.node_id,target:edge.target_node_id,
   metadata:{...metadata,threshold:metadata.threshold??0,multiplier:metadata.multiplier??1,channels:metadata.channels??[],attributes:metadata.attributes??{}}}];
 }));
 if(!links.length)return {edges:[]};
 // State the common rule once. Each edge explicitly supplies its exceptions.
 const defaults={};for(const key of ['threshold','multiplier','channels','attributes']){
  const counts=new Map();let best=0;for(const link of links){const value=link.metadata[key],signature=JSON.stringify(value),count=(counts.get(signature)??0)+1;counts.set(signature,count);if(count>best){best=count;defaults[key]=value;}}
 }
 return {edge_defaults:defaults,edges:links.map(({metadata,...edge})=>({...edge,...Object.fromEntries(Object.entries(metadata).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(defaults[key])))}))};
}

function moduleCatalog(snapshot,nodes){
 return [...new Set(nodes.flatMap(node=>keys(node.modules)))].map(id=>{
  const manifest=snapshot.resources?.[id]?.release?.manifest;
  return present({id,name:manifest?.name});
 });
}

function overview(document){
 const network=document.network,nodes=network.nodes,edges=compactEdges(nodes);
 return {counts:{nodes:nodes.length,edges:edges.edges.length,files:keys(document.files).length},
  nodes:nodes.map(nodeSummary),...edges,...present({delegations:network.delegations,repeat_unit:network.repeat_unit,repeat_unit_count:network.repeat_unit_count})};
}

const hint='边上省略的属性使用 edge_defaults；完整参数和状态用 response_format="detailed"。';

export function inspectNetwork(snapshot,snapshotId,args={}){
 const format=responseFormat(args.response_format),network=snapshot.document.network,nodes=network.nodes;
 const base={snapshot:snapshotId,response_format:format};
 if(args.node){
  const node=nodes.find(node=>node.node_id===args.node);if(!node)throw Error('节点不在本轮快照内');
  const incoming=nodes.flatMap(n=>(n.connections?.interfaces??[]).filter(edge=>edge.target_node_id===node.node_id).map(edge=>({source:n.node_id,...edge})));
  if(format==='detailed')return clone({...base,node,incoming});
  const modules=Object.fromEntries(Object.entries(node.modules??{}).map(([id,spec])=>[id,present({name:snapshot.resources?.[id]?.release?.manifest?.name,access:spec.access})]));
  return clone({...base,node:present({...nodeSummary(node),modules}),...compactEdges(nodes,node.node_id),detail_hint:hint});
 }
 if(format==='detailed'){
  const {nodes:allNodes,...properties}=network;
  return clone({...base,target:snapshot.target,selection:snapshot.selection,nodes:allNodes,network_properties:properties,files:keys(snapshot.document.files),...(snapshot.preset?{preset:{name:snapshot.preset.name,document:snapshot.preset.document}}:{})});
 }
 const preset=snapshot.preset;
 return clone({...base,target:snapshot.target,selection:snapshot.selection,
  ...overview(snapshot.document),module_catalog:moduleCatalog(snapshot,[...nodes,...(preset?.document.network.nodes??[])]),
  ...(preset?{preset:{name:preset.name,...overview(preset.document)}}:{}),
  detail_hint:hint});
}
