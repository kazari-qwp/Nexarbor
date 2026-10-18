import {createHash} from 'node:crypto';

const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
// 历史身份来自配置。实例编号、画布位置、运行进度和文档副本路径不属于配置。
export function normalizeHistory(entry,modules={}){
 let config,kind=entry.kind;
 if(entry.asset){const {state,...asset}=entry.asset;config={asset};kind=asset.kind;}
 else if(entry.snapshot?.nodes?.length){
  const snapshot=entry.snapshot,nodes=snapshot.nodes,mapping=new Map(nodes.map((n,i)=>[n.node_id,'@'+i])),files=new Map(Object.entries(snapshot.files??{})),documents=[];
  const paths=new Map();
  const translate=value=>{
   if(typeof value==='string'){
    if(files.has(value)){if(!paths.has(value)){paths.set(value,'document:'+paths.size);documents.push(files.get(value));}return paths.get(value);}
    return value;
   }
   if(Array.isArray(value))return value.map(translate);
   if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,translate(value[k])]));
   return value;
  };
  const refs=(value,schema)=>schema?.format==='node-id'&&typeof value==='string'?(mapping.get(value)??value):Array.isArray(value)?value.map(v=>refs(v,schema?.items)):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,refs(v,schema?.properties?.[k])])):value;
  const normalized=nodes.map(node=>{
   const value=structuredClone(node);delete value.node_id;delete value.context_cursor;
   value.management_parent_id=mapping.get(node.management_parent_id)??null;
   for(const [id,spec] of Object.entries(value.modules??{})){delete spec.state;spec.config=refs(spec.config,modules?.[id]?.schema);}
   value.connections.interfaces=value.connections.interfaces.map(link=>({...link,target_node_id:mapping.get(link.target_node_id)??link.target_node_id}));
   return translate(value);
  });
  kind=nodes.length===1?'node':'network';config={nodes:normalized,documents};
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
