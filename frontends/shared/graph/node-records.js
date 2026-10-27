// Editor helpers address the actual serialized records in place.
export const moduleTable=node=>Object.fromEntries((node.tables?.modules??[]).map(item=>[item.module_id,item]));
export const moduleAccess=record=>Object.fromEntries(['channels','strength','channel_mode'].filter(key=>record[key]!==undefined).map(key=>[key,record[key]]));
export function setModule(node,id,record){
 node.tables??={modules:[]};const index=node.tables.modules.findIndex(item=>item.module_id===id),value={...record,module_id:id};
 if(index<0)node.tables.modules.push(value);else node.tables.modules[index]=value;
}
export function removeModule(node,id){node.tables.modules=node.tables.modules.filter(item=>item.module_id!==id);}
export const nodeSkills=node=>node.execution?.skills??[];
export function setSkills(node,skills){node.execution??={executor:'harness'};node.execution.skills=skills;}
export const offeredPorts=(node,properties={})=>properties[node.node_id]?.offered_ports??[];
export function setPorts(node,properties,offers){
 properties[node.node_id]??={};properties[node.node_id].offered_ports=offers;
 const selected=new Set(offers.map(item=>item.ref));
 const prune=group=>{if(!group?.members)return;group.members=group.members.filter(item=>!item.host_ref||selected.has(item.host_ref));for(const item of group.members)prune(item);};
 prune(node.tables?.tools);for(const module of node.tables?.modules??[])prune(module.tools);
}
