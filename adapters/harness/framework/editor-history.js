import {singleOwnedNode} from '../../../shared/graph/ownership.js';
import {createHash} from 'node:crypto';

const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
// 历史身份来自配置。实例编号、画布位置、运行进度和文档副本路径不属于配置。
export function normalizeHistory(entry,modules={}){
 let config,kind=entry.kind;
 if(entry.asset){const {state,...asset}=entry.asset;config={asset};kind=asset.kind;}
 else if(entry.snapshot?.nodes?.length){
  const snapshot=entry.snapshot,nodes=snapshot.nodes,mapping=new Map(nodes.map((n,i)=>[n.node_id,'@'+i])),files=new Map(Object.entries(snapshot.files??{}).map(([name,value])=>[name.replaceAll('\\','/'),value])),documents=[];
  const folders=new Set(nodes.flatMap(n=>['directory','storage_path'].map(k=>n.parameters?.[k]).filter(v=>typeof v==='string').map(v=>v.replaceAll('\\','/').replace(/\/$/,''))));
  const paths=new Map();
  const translate=value=>{
   if(typeof value==='string'){
    const normalized=value.replaceAll('\\','/');
    if(folders.has(normalized)){if(!paths.has(normalized)){paths.set(normalized,'directory:'+paths.size);documents.push(Object.fromEntries([...files].filter(([name])=>name.startsWith(normalized+'/')).map(([name,data])=>[name.slice(normalized.length+1),data])));}return paths.get(normalized);}
    value=files.has(normalized)?normalized:value;
    if(files.has(value)){if(!paths.has(value)){paths.set(value,'document:'+paths.size);documents.push(files.get(value));}return paths.get(value);}
    return value;
   }
   if(Array.isArray(value))return value.map(translate);
   if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,translate(value[k])]));
   return value;
  };
  const refs=(value,schema)=>['node-id','node-reference'].includes(schema?.format)&&typeof value==='string'?(mapping.get(value)??value):Array.isArray(value)?value.map(v=>refs(v,schema?.items)):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,refs(v,schema?.properties?.[k])])):value;
  const normalized=nodes.map(node=>{
   const value=structuredClone(node);delete value.node_id;delete value.context_cursor;delete value.inputs;
   if(value.type==='subnode')value.parameters.parent_id=mapping.get(value.parameters.parent_id)??value.parameters.parent_id;
   for(const reference of value.execution?.prepare??[])if(reference.node)reference.node=mapping.get(reference.node)??reference.node;
   if(value.execution?.tool_sources)value.execution.tool_sources=value.execution.tool_sources.map(id=>mapping.get(id)??id);
   value.management_parent_id=mapping.get(node.management_parent_id)??null;
   for(const [id,spec] of Object.entries(value.modules??{})){delete spec.state;spec.config=refs(spec.config,modules?.[id]?.schema);}
   value.connections.interfaces=value.connections.interfaces.map(link=>({...link,target_node_id:mapping.get(link.target_node_id)??link.target_node_id}));
   return translate(value);
  });
  kind=snapshot.repeat_unit_count==null&&singleOwnedNode(nodes)?'node':'network';config={nodes:normalized,documents,...(snapshot.repeat_unit_count!=null?{repeat_unit_count:snapshot.repeat_unit_count,repeat_unit:snapshot.repeat_unit.map(id=>mapping.get(id)??id)}:{}),...(snapshot.edges?.length?{entries:snapshot.edges.map(e=>({metadata:e.metadata,...(e.target?{target:mapping.get(e.target)??e.target}:{})}))}:{})};
 }else if(entry.snapshot?.edges?.length||entry.metadata){
  kind='edge';config={edges:(entry.snapshot?.edges??[{metadata:entry.metadata,target:entry.target}]).map(e=>({metadata:e.metadata,...(e.target?{target:e.target}:{})}))};
 }
 if(!config)return entry;
 const configKey=createHash('sha256').update(JSON.stringify(ordered(config))).digest('hex');
 return {...entry,kind,id:'cfg-'+configKey,configKey};
}
export function compactHistory(entries,modules={}){
 const seen=new Set();return entries.map(entry=>normalizeHistory(entry,modules)).filter(entry=>{const key=entry.kind+':'+entry.id;if(seen.has(key))return false;seen.add(key);return true;}).slice(0,100);
}
