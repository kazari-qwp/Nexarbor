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
export function parallelTownTemplates(templates=[]){
 return structuredClone(templates).map(t=>{
  for(const n of t.document?.network?.nodes??[]){
   for(const e of n.connections.interfaces)if(e.target_node_id==='world/settle'&&e.metadata.channels.includes('tick'))e.target_node_id='world/save';
   const box=n.modules?.['messages.box'];if(box&&n.modules?.['agents.activity']){box.config.notify_activity=true;box.access.channels=[...new Set([...box.access.channels,'activity'])];}
  }
  for(const a of t.attachments??[])if(a.source==='npc/lu'&&a.metadata.channels.includes('tick'))a.source='world/time';
  return t;
 });
}
export async function updateTownRuntime(rpc,directory){
 const marker=path.join(directory,'town-parallel-layout-v1.json');try{await fs.access(marker);return;}catch(error){if(error.code!=='ENOENT')throw error;}
 const state=await rpc('studio_state'),live=parallelTownDocument(state.live.document),draft=state.draft?parallelTownDocument(state.draft.document):null;
 if(live.changed||draft?.changed){
  // 当前后端已拥有工作区锁，尚未开放画布，也没有运行中的活动。
  await fs.writeFile(path.join(directory,'before-town-parallel-layout.json'),JSON.stringify(state,null,2));
  if(live.changed){const result=await rpc('studio_apply',{document:live.document,base_commit:state.live.commit,layout:state.draft?.layout??{}});if(!result.valid)throw Error('更新小镇布局校验失败：'+JSON.stringify(result));}
  if(state.draft&&!state.draft.applied){
   const now=await rpc('studio_state');await rpc('studio_draft',{document:draft.document,expected_version:now.draft?.version??0,base_commit:now.live.commit,layout:state.draft.layout??{}});
  }
 }
 await fs.writeFile(marker,JSON.stringify({version:1,changed:live.changed,updatedAt:new Date().toISOString()}));
}
