// Pure, atomic resource assembly. Used by the editor and the transport host.
export function assembleResources(document,nodeId,assets,catalog,{available=()=>true}={}){
 const next=structuredClone(document),node=next.network.nodes.find(n=>n.node_id===nodeId);
 if(!node)throw Error('请把资源拖到节点上');
 const visiting=new Set(),done=new Set(),copy=structuredClone;
 const mount=(kind,id,spec,explicit=false)=>{
  const key=kind+':'+id;
  if(visiting.has(key))throw Error('资源依赖成环：'+key);
  if(done.has(key)&&!explicit)return;
  const definition=kind==='module'?catalog.modules?.[id]:kind==='skill'?catalog.skills?.[id]:catalog.tools?.find(t=>t.ref===id);
  if(!definition||definition.available===false)throw Error('缺少依赖资源：'+key);
  const installed=kind==='module'?node.modules?.[id]:kind==='skill'?node.skills?.includes(id):node.offered_tools?.some(t=>t.ref===id);
  if(!installed&&!available(kind,id))throw Error('资源已归档或删除：'+key);
  if(kind==='skill'&&node.type!=='agent')throw Error('Skill 需要装配到 Agent 节点');
  if(kind==='module'&&definition.node_types&&!definition.node_types.includes(node.type==='subnode'?'node':node.type))throw Error('此模块或依赖不支持该节点类型：'+id);
  visiting.add(key);
  for(const dependency of definition.requires??[])mount('module',dependency);
  if(kind==='skill'){
   for(const dependency of definition.skills??[])mount('skill',dependency);
   for(const dependency of definition.tools??[])mount('tool',dependency);
  }
  if(kind==='tool'&&definition.module)mount('module',definition.module);
  visiting.delete(key);done.add(key);
  if(kind==='module'){
   node.modules??={};
   if(!node.modules[id]||explicit){const selected=spec??definition.defaults??{};node.modules[id]={config:copy(selected.config??{}),state:copy(node.modules[id]?.state??selected.state??{}),access:copy(selected.access??node.modules[id]?.access??definition.defaults?.access??{strength:0,channels:[]})};}
  }else if(kind==='skill')node.skills=[...new Set([...(node.skills??[]),id])];
  else if(!definition.module){node.offered_tools??=[];const index=node.offered_tools.findIndex(t=>t.ref===id),offer={ref:id,channels:copy(spec?.channels??definition.channels??['tools'])};if(index<0)node.offered_tools.push(offer);else if(explicit)node.offered_tools[index]=offer;}
 };
 for(const asset of assets)mount(asset.kind,asset.id,asset,asset.kind!=='skill');
 return next;
}
