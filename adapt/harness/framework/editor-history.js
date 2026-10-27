import {singleOwnedNode} from '../../../frontends/shared/graph/ownership.js';
import {createHash} from 'node:crypto';

const ordered=value=>Array.isArray(value)?value.map(ordered):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,ordered(value[key])])):value;
// 历史身份来自配置。实例编号、画布位置、运行进度和文档副本路径不属于配置。
export function normalizeHistory(entry,modules={}){
 let config,kind=entry.kind;
 if(entry.asset){const {state,...asset}=entry.asset;config={asset};kind=asset.kind;}
 else if(entry.snapshot?.nodes?.length){
  const snapshot=entry.snapshot,nodes=snapshot.nodes,mapping=new Map(nodes.map((n,i)=>[n.node_id,'@'+i])),files=new Map(Object.entries(snapshot.files??{}).map(([name,value])=>[name.replaceAll('\\','/'),value])),documents=[];
  const folders=new Set(nodes.filter(n=>n.data?.directory).map(n=>n.data.path.replaceAll('\\','/').replace(/\/$/,'')));
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
   delete value.agent;
   for(const reference of value.execution?.prepare??[])if(reference.node)reference.node=mapping.get(reference.node)??reference.node;
   value.tables??={modules:[]};
   const aliases=new Map(),properties=structuredClone(snapshot.properties?.[node.node_id]??{});
   for(const offer of properties.offered_ports??[])aliases.set('ext_'+createHash('sha256').update(node.node_id+'\0'+offer.ref).digest('hex').slice(0,24),offer.ref);
   for(const spec of value.tables.modules){
    const source=createHash('sha256').update(node.node_id+'\0'+spec.module_id).digest('hex').slice(0,24);
    for(const tool of modules?.[spec.module_id]?.agent_tools??[])aliases.set('mod_'+createHash('sha256').update(source+'\0'+tool.id).digest('hex').slice(0,24),'module:'+spec.module_id+'/'+tool.id);
    delete spec.state;delete spec.published;delete spec.tools;delete spec.description;delete spec.modules;
    spec.config=refs(spec.config,modules?.[spec.module_id]?.config_schema);
   }
   const toolConfig=item=>!item||typeof item!=='object'?item:item.tool?{tool:aliases.get(item.tool)??item.tool,...(item.factory_module?{factory_module:item.factory_module}:{})}:Object.fromEntries(Object.entries(item).map(([key,entry])=>[key,key==='members'?entry.map(toolConfig):entry]));
   value.tables.tools=toolConfig(value.tables.tools);
   value.links=value.links.map(link=>({...link,target_id:mapping.get(link.target_id)??link.target_id}));
   for(const field of ['management_parent_id','parent_id'])if(Object.hasOwn(properties,field))properties[field]=mapping.get(properties[field])??null;
   if(Object.keys(properties).length)value.properties=properties;
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
