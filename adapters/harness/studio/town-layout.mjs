import fs from 'node:fs/promises';
import path from 'node:path';

// 只更新内置小镇的已知旧布局；不是旧模块协议兼容层，也不覆盖自制网络。
export function parallelTownDocument(document){
 const doc=structuredClone(document),nodes=doc.network?.nodes??[],by=new Map(nodes.map(n=>[n.node_id,n])),relay=by.get('world/settle');
 if(!relay||relay.name!=='活动汇合'||Object.keys(relay.modules??{}).length||(relay.offered_tools??[]).length||!by.has('world/time')||!by.has('world/save'))return {document:doc,changed:false};
 const actors=nodes.filter(n=>n.modules?.['agents.activity']).map(n=>n.node_id),group=new Set(['world/time','world/settle','world/save',...actors]);
 const tick=edge=>edge.metadata?.channels?.length===1&&edge.metadata.channels[0]==='tick';
 // 自定义非 tick 入边或业务状态意味着该节点已有别的用途，不擅自删除。
 if(nodes.some(n=>n.connections.interfaces.some(e=>e.target_node_id==='world/settle'&&!tick(e))))return {document:doc,changed:false};
 if(relay.connections.interfaces.some(e=>!tick(e)||e.target_node_id!=='world/save'))return {document:doc,changed:false};
 for(const n of nodes){
  n.connections.interfaces=n.connections.interfaces.filter(e=>!(group.has(n.node_id)&&group.has(e.target_node_id)&&tick(e)&&n.node_id!=='world/save'));
  const box=n.modules?.['messages.box'];if(n.modules?.['agents.activity']&&box){box.config.notify_activity=true;box.access.channels=[...new Set([...box.access.channels,'activity'])];}
 }
 const add=(from,to)=>by.get(from).connections.interfaces.push({target_node_id:to,metadata:{channels:['tick'],threshold:1,multiplier:1,attributes:{}}});
 for(const actor of actors){add('world/time',actor);add(actor,'world/save');}
 doc.network.nodes=nodes.filter(n=>n.node_id!=='world/settle');
 return {document:doc,changed:true};
}
export function currentTownDocument(document){
 const previous=parallelTownDocument(document),doc=previous.document,nodes=doc.network.nodes,observer=nodes.find(n=>n.node_id==='root');
 const unused=observer?.type==='node'&&observer.name==='小镇观察者'&&!observer.description&&
  !Object.keys(observer.modules??{}).length&&!(observer.offered_tools??[]).length&&!(observer.toolboxes??[]).length&&!(observer.expose??[]).length&&
  !Object.keys(observer.parameters??{}).length&&!observer.execution&&!observer.agent&&!observer.inputs&&!observer.context_cursor&&
  !(doc.network.delegations??[]).some(g=>g.source==='root'||g.target==='root')&&
  !observer.connections.interfaces.length&&!nodes.some(n=>n.connections.interfaces.some(e=>e.target_node_id==='root'));
 if(unused){doc.network.nodes=nodes.filter(n=>n!==observer);for(const node of doc.network.nodes)if(node.management_parent_id==='root')node.management_parent_id=null;}
 return {document:doc,changed:previous.changed||!!unused};
}
export function parallelTownTemplates(templates=[]){
 return structuredClone(templates).map(t=>{
  for(const n of t.document?.network?.nodes??[]){
   updateQueryActor(n);
   if(n.management_parent_id==='root')n.management_parent_id=null;
   for(const e of n.connections.interfaces)if(e.target_node_id==='world/settle'&&e.metadata.channels.includes('tick'))e.target_node_id='world/save';
   const box=n.modules?.['messages.box'];if(box&&n.modules?.['agents.activity']){box.config.notify_activity=true;box.access.channels=[...new Set([...box.access.channels,'activity'])];}
  }
  for(const a of t.attachments??[])if(a.source==='npc/lu'&&a.metadata.channels.includes('tick'))a.source='world/time';
  return t;
 });
}
export async function updateTownRuntime(rpc,directory){
 const marker=path.join(directory,'town-layout-v2.json');try{await fs.access(marker);return;}catch(error){if(error.code!=='ENOENT')throw error;}
 const state=await rpc('studio_state'),live=currentTownDocument(state.live.document),draft=state.draft?currentTownDocument(state.draft.document):null;
 if(live.changed||draft?.changed){
  // 当前后端已拥有工作区锁，尚未开放画布，也没有运行中的活动。
  await fs.writeFile(path.join(directory,'before-town-layout-v2.json'),JSON.stringify(state,null,2));
  if(live.changed){const result=await rpc('studio_apply',{document:live.document,base_commit:state.live.commit,layout:state.draft?.layout??{}});if(!result.valid)throw Error('更新小镇布局校验失败：'+JSON.stringify(result));}
  if(state.draft&&!state.draft.applied){
   const now=await rpc('studio_state');await rpc('studio_draft',{document:draft.document,expected_version:now.draft?.version??0,base_commit:now.live.commit,layout:state.draft.layout??{}});
  }
 }
 await fs.writeFile(marker,JSON.stringify({version:2,changed:live.changed,updatedAt:new Date().toISOString()}));
}

// 内置小镇的查询配置：地图布局属于数据，不写入通用角色模块。
const townMapLayout=[['place/home1',.09,.09],['place/civil',.06,.53],['place/tavern',.33,.44],['place/hospital',.44,.06],['place/shop',.63,.39],['place/home2',.38,.84],['place/woods',.66,.96],['place/smith',.94,.34],['place/mine',.95,.82]].map(([node,x,y])=>({node,x,y}));
const townPlaceDescriptions={
 'place/home1':'居民住处。只有登记住在这里的角色可以使用休息服务，其他人可以通行。',
 'place/home2':'居民住处。只有登记住在这里的角色可以使用休息服务，其他人可以通行。',
 'place/civil':'办理结婚。双方本人到场并同意后，按当地协议办理登记。',
 'place/hospital':'办理出生。满足家庭协议等待时间和资格后，由待产者本人办理。',
 'place/tavern':'购买饮品。可以与同地人物交谈，具体价格以当地服务工具为准。',
 'place/shop':'买卖物品。可以买工具、出售矿石、木材和黄金，价格以当地服务工具为准。',
 'place/smith':'修理镐子。坏镐可以在此修理，需满足当地服务的费用和材料要求。',
 'place/woods':'砍树。持有斧头并满足行动点要求时，可以使用当地劳动服务。',
 'place/mine':'挖矿。持有完好镐子并满足行动点要求时，可以使用当地劳动服务。'
};
function updateQueryActor(node){
 const mount=node.modules?.['agents.context'];if(!mount)return;
 mount.config.map='';mount.config.map_title??='小镇道路图';mount.config.map_layout??=structuredClone(townMapLayout);
 // 地图读取权限由模块声明给定；Agent 工具不接受扩大强度或修改权限的参数。
 mount.access.strength=Math.max(mount.access.strength??node.module_strength??0,12);
 const help='需要了解地点用途时查询地点，需要查看道路图时查询地图。';if(!mount.config.common?.includes(help))mount.config.common=(mount.config.common??'')+'\n'+help;
}
export function queryTownDocument(document){
 const doc=structuredClone(document),nodes=doc.network?.nodes??[];
 if(!nodes.some(n=>n.node_id==='world/time')||!nodes.some(n=>n.node_id==='place/home1'))return {document:doc,changed:false};
 const before=JSON.stringify(doc);
 for(const node of nodes){updateQueryActor(node);const description=townPlaceDescriptions[node.node_id],place=node.modules?.['place.info'];if(description&&place){const old=node.name+'，使用本地服务，沿相邻道路移动。';if(!place.config.description||place.config.description===old)place.config.description=description;if(!node.description||node.description===old)node.description=description;}}
 return {document:doc,changed:JSON.stringify(doc)!==before};
}
export async function updateTownQueries(rpc,directory){
 const marker=path.join(directory,'town-queries-v1.json');try{await fs.access(marker);return;}catch(error){if(error.code!=='ENOENT')throw error;}
 const catalog=await rpc('studio_catalog');if(!catalog.library['agents.context']?.manifest.operations.some(op=>op.name==='map'))return;
 const state=await rpc('studio_state'),live=queryTownDocument(state.live.document),draft=state.draft?queryTownDocument(state.draft.document):null;
 if(live.changed||draft?.changed){await fs.writeFile(path.join(directory,'before-town-queries-v1.json'),JSON.stringify(state));
  if(live.changed){const result=await rpc('studio_apply',{document:live.document,base_commit:state.live.commit,layout:state.draft?.layout??{}});if(!result.valid)throw Error('小镇查询配置更新失败');}
  if(state.draft&&!state.draft.applied){const current=await rpc('studio_state');await rpc('studio_draft',{document:draft.document,expected_version:current.draft?.version??0,base_commit:current.live.commit,layout:state.draft.layout??{}});}
 }
 const workspaceFile=path.join(directory,'workspace-session.json');let workspace;
 try{workspace=JSON.parse(await fs.readFile(workspaceFile,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
 if(workspace?.document){const updated=queryTownDocument(workspace.document);if(updated.changed){await fs.writeFile(path.join(directory,'before-town-query-workspace-v1.json'),JSON.stringify(workspace));const current=await rpc('studio_state');workspace.document=updated.document;workspace.base_commit=current.live.commit;const temporary=workspaceFile+'.query-update.tmp';await fs.writeFile(temporary,JSON.stringify(workspace));await fs.rename(temporary,workspaceFile);}}
 await fs.writeFile(marker,JSON.stringify({version:1,changed:live.changed}));
}
