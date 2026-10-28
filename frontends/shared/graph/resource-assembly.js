import {copyJson} from '../json-copy.js';
import {moduleTable,moduleAccess,setModule,nodeSkills,setSkills,offeredPorts,setPorts} from './node-records.js';
export const initialModuleAccess=(document,nodeId,value={})=>({...value,strength:value.strength??document.network.properties?.[nodeId]?.module_strength??1});
// Pure, atomic resource assembly. Used by the editor and the transport host.
export function assembleResources(document,nodeId,assets,catalog,{available=()=>true}={}){
 const next=copyJson(document),node=next.network.nodes.find(n=>n.node_id===nodeId);
 if(!node)throw Error('请把资源拖到节点上');
 const visiting=new Set(),done=new Set(),copy=copyJson,properties=next.network.properties??={};
 const mount=(kind,id,spec,explicit=false)=>{
  const key=kind+':'+id;
  if(visiting.has(key))throw Error('资源依赖成环：'+key);
  if(done.has(key)&&!explicit)return;
  const definition=kind==='module'?catalog.modules?.[id]:kind==='skill'?catalog.skills?.[id]:catalog.tools?.find(t=>t.ref===id);
  if(!definition||definition.available===false)throw Error('缺少依赖资源：'+key);
  const installed=kind==='module'?moduleTable(node)[id]:kind==='skill'?nodeSkills(node).includes(id):offeredPorts(node,properties).some(t=>t.ref===id);
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
   const previous=moduleTable(node)[id];
   if(!previous||explicit){const selected=spec??definition.defaults??{};setModule(node,id,{...previous,config:copy(selected.config??{}),state:copy(previous?.state??selected.state??{}),...initialModuleAccess(next,nodeId,copy(selected.access??(previous?moduleAccess(previous):definition.defaults?.access??{channels:[]})))});}
  }else if(kind==='skill')setSkills(node,[...new Set([...nodeSkills(node),id])]);
  else if(!definition.module){const offers=offeredPorts(node,properties),index=offers.findIndex(t=>t.ref===id),offer={ref:id,channels:copy(spec?.channels??definition.channels??['tools'])};if(index<0)offers.push(offer);else if(explicit)offers[index]=offer;setPorts(node,properties,offers);}
 };
 for(const asset of assets)mount(asset.kind,asset.id,asset,asset.kind!=='skill');
 return next;
}
