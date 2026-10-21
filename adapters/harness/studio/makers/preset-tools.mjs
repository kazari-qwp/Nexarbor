import {createHash} from 'node:crypto';
import {storedNetworks} from '../../framework/stored-networks.js';
import {pasteSubnet} from '../../../../shared/graph/subnets.js';
const entries=preset=>(preset.snapshot.edges??[]).filter(edge=>!edge.source&&edge.target).map(edge=>{const node=preset.snapshot.nodes.find(item=>item.node_id===edge.target);return {node:edge.target,name:node?.name??edge.target,modules:Object.keys(node?.modules??{}),channels:edge.metadata?.channels??[]};});
const digest=text=>createHash('sha256').update(text).digest('hex');
export async function catalogPresets(manager,args={}){
 const store=storedNetworks(manager.directory);
 if(args.id){const preset=await store.load(args.id);return {id:preset.id,name:preset.name,description:preset.description,node_count:preset.snapshot.nodes.length,repeat_unit_count:preset.repeat_unit_count??null,modules:[...new Set(preset.snapshot.nodes.flatMap(node=>Object.keys(node.modules??{})))],entries:entries(preset),hint:'instantiate_preset 返回实际创建的节点编号映射，再用 edit_network 接线。'};}
 const {presets,errors}=await store.list({summary:true});const query=(args.query??'').toLowerCase();const matches=presets.filter(item=>(item.name+' '+item.description+' '+item.id).toLowerCase().includes(query)),offset=args.offset??0,limit=args.limit??12;
 return {total:matches.length,presets:matches.slice(offset,offset+limit).map(item=>({id:item.id,name:item.name,description:item.description,node_count:item.nodeCount,repeat_unit_count:item.repeat_unit_count??null})),...(offset+limit<matches.length?{next_offset:offset+limit}:{}),...(errors.length?{errors}: {})};
}
export async function instantiatePreset(manager,job,args){
 const preset=await storedNetworks(manager.directory).load(args.id),catalog=await manager.rpc('studio_catalog');
 const hidden=new Set(job.hidden_modules??[]);for(const node of preset.snapshot.nodes)for(const module of Object.keys(node.modules??{})){if(hidden.has(module))throw Error('预设包含隐藏组件：'+module);if(!catalog.library[module]?.available)throw Error('请先安装预设依赖模块：'+module);}
 const snapshot=await manager.rpc('preset_expand',{snapshot:preset.snapshot,...(args.count!==undefined?{count:args.count}:{})});
 const work=await manager.rpc('studio_read',{id:job.workspace}),file=args.path??'network.json';if(!file.endsWith('.json'))throw Error('网络产物使用自有 JSON 文件');
 const text=work.files[file]??'',document=text?JSON.parse(text):{network:{version:8,nodes:[],signals:{},delegations:[]},files:{}};
 const schemas=Object.fromEntries(Object.entries(catalog.library).map(([id,release])=>[id,{schema:release.manifest.config_schema,state_schema:release.manifest.state_schema}]));
 const result=pasteSubnet(document,{...preset,snapshot},{x:args.x??0,y:args.y??0},schemas);
 await manager.rpc('studio_save',{id:job.workspace,file,content:JSON.stringify(result.document,null,2)+'\n',expected:digest(text)});
 return {preset:args.id,file,created_nodes:result.nodes.length,created_files:Object.keys(snapshot.files??{}).length,nodes:Object.fromEntries(snapshot.nodes.map((node,index)=>[node.node_id,result.nodes[index]])),entries:entries({...preset,snapshot}).map(entry=>({...entry,node:result.nodes[snapshot.nodes.findIndex(node=>node.node_id===entry.node)]})),hint:'这些是实际节点编号；用 edit_network 连接组入口，修改根节点的 prepare/tool_sources 时也使用实际编号。'};
}
