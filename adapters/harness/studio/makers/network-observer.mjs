// Read-only projections of an explicit snapshot. This layer never discovers a live/global graph.
import {createHash} from 'node:crypto';
const copy=structuredClone,short=(s,n=160)=>String(s??'').slice(0,n),names=v=>Object.keys(v??{});
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
export function indexNetwork(document,previous={}){
 const nodes={...previous.nodes},edges={...previous.edges};
 let nextNode=Math.max(0,...Object.values(nodes).map(v=>Number(v.slice(1))))+1;
 let nextEdge=Math.max(0,...Object.values(edges).map(v=>Number(v.slice(1))))+1;
 for(const n of [...document.network.nodes].sort((a,b)=>a.node_id.localeCompare(b.node_id)))nodes[n.node_id]??='N'+nextNode++;
 const occurrence=new Map();
 for(const n of [...document.network.nodes].sort((a,b)=>a.node_id.localeCompare(b.node_id)))for(const e of n.connections?.interfaces??[]){
  const signature=hash([n.node_id,e]),count=occurrence.get(signature)??0;occurrence.set(signature,count+1);
  edges[signature+':'+count]??='E'+nextEdge++;
 }
 return {nodes,edges};
}
export class NetworkObserver{
 constructor(snapshot,id){
  this.snapshot=snapshot;this.id=id;this.nodes=snapshot.document.network.nodes;this.index=snapshot.observerIndex??indexNetwork(snapshot.document);
  this.byId=new Map(this.nodes.map(n=>[n.node_id,n]));this.byRef=new Map(this.nodes.map(n=>[this.index.nodes[n.node_id],n]));
  this.links=[];const occurrence=new Map();
  for(const n of this.nodes)for(const [i,e] of (n.connections?.interfaces??[]).entries()){
   const signature=hash([n.node_id,e]),count=occurrence.get(signature)??0;occurrence.set(signature,count+1);
   this.links.push({ref:this.index.edges[signature+':'+count],id:n.node_id+'|'+i,source:n.node_id,target:e.target_node_id,metadata:e.metadata??{}});
  }
  this.children=new Map();for(const n of this.nodes)if(n.type==='subnode')this.children.set(n.parameters?.parent_id,[...(this.children.get(n.parameters?.parent_id)??[]),n]);
 }
 check(args){if(!args||typeof args!=='object'||Array.isArray(args))throw Error('查询参数必须是 JSON 对象');for(const key of ['nodes','edges','channels','types','modules','fields'])if(args[key]!==undefined&&(!Array.isArray(args[key])||args[key].some(v=>typeof v!=='string')))throw Error(key+' 必须是字符串列表');if(args.channel_mode&&!['allow','deny'].includes(args.channel_mode))throw Error('channel_mode 仅支持 allow 或 deny');if(args.snapshot&&args.snapshot!==this.id)throw Error('快照已变化；请用当前快照重新查询，不能混用图片和编号。');}
 node(ref){const found=this.byRef.get(ref)??this.byId.get(ref);if(!found)throw Error('找不到节点 '+ref+'；编号仅用于当前咨询的快照。');return found;}
 ref(id){return this.index.nodes[id]??id;}
 refs(list,max=12){if(!Array.isArray(list)||!list.length||list.length>max)throw Error('请提供 1–'+max+' 个节点编号或真实 ID');return [...new Set(list.map(r=>this.node(r)))];}
 base(){return {snapshot:this.id,...(this.snapshot.source?{source:this.snapshot.source}:{})};}
 localTools(n){return [...new Set([...(n.offered_tools??[]).map(t=>t.ref),...names(n.modules).flatMap(id=>(this.snapshot.resources?.[id]?.release?.manifest?.agent_tools??[]).map(t=>'module:'+id+'/'+t.id))])];}
 passiveText(n){return n.type==='text_file'&&!n.execution&&!(n.offered_tools?.length)&&names(n.modules).every(id=>{const m=this.snapshot.resources?.[id]?.release?.manifest;return !!m&&!Object.keys(m.signals??{}).length&&!m.agent_tools?.length;});}
 summary(n){return {ref:this.ref(n.node_id),name:n.name,type:n.type,...(n.type==='subnode'?{parent:this.ref(n.parameters?.parent_id)}:{}),modules:names(n.modules).length,tools:this.localTools(n).length,...(this.children.has(n.node_id)?{subnodes:this.children.get(n.node_id).length}:{})};}
 brief(value,fields){
  if(fields?.length)value=Object.fromEntries(fields.filter(k=>Object.hasOwn(value??{},k)).map(k=>[k,value[k]]));
  if(Buffer.byteLength(JSON.stringify(value??null))<=6500)return copy(value);
  return {large:true,fields:names(value),hint:'内容较大。请用 fields 指定需要的顶层字段；文本正文可用 inspect_network 按行读取。'};
 }
 inspectNodes(args){
  this.check(args);const section=args.section??'modules';if(!['summary','modules','tools','config','state','settings'].includes(section))throw Error('未知节点查询部分');
  return {...this.base(),nodes:this.refs(args.nodes).map(n=>{
   const result={ref:this.ref(n.node_id),id:n.node_id,name:n.name,...(n.type==='subnode'?{parent:this.ref(n.parameters?.parent_id),use_parent_links:!!n.parameters?.use_parent_links,share_links:!!n.parameters?.share_links}:{})};
   if(section==='summary')return {...result,type:n.type,description:short(n.description),...(n.type==='text_file'?{file:n.parameters?.file_path}:{}),...(n.execution?{execution:{executor:n.execution.executor,channels:n.execution.channels,prepare:n.execution.prepare?.map(p=>({module:p.module,operation:p.operation,target:p.target}))}}:{}),...(n.type==='subnode'?{parent:this.ref(n.parameters?.parent_id),use_parent_links:n.parameters?.use_parent_links,share_links:n.parameters?.share_links}:{}),subnodes:(this.children.get(n.node_id)??[]).map(c=>this.summary(c)),modules:names(n.modules),offered_tools:(n.offered_tools??[]).map(t=>t.ref),local_tool_count:this.localTools(n).length};
   if(section==='settings')return {...result,settings:this.brief({parameters:n.parameters,execution:n.execution,divergence:n.divergence,module_strength:n.module_strength},args.fields)};
   const modules=Object.entries(n.modules??{}).filter(([id])=>!args.modules?.length||args.modules.includes(id));
   if(section==='tools')return {...result,offered_tools:n.offered_tools??[],module_tools:modules.flatMap(([id])=>(this.snapshot.resources?.[id]?.release?.manifest?.agent_tools??[]).map(t=>({ref:'module:'+id+'/'+t.id,name:t.name,operation:t.operation}))),subnodes:(this.children.get(n.node_id)??[]).map(c=>({ref:this.ref(c.node_id),name:c.name}))};
   if(section==='modules')return {...result,modules:modules.map(([id,spec])=>({id,name:this.snapshot.resources?.[id]?.release?.manifest?.name??id,strength:spec.access?.strength??n.module_strength,channels:spec.access?.channels??[],...(spec.access?.channel_mode?{channel_mode:spec.access.channel_mode}:{})})),subnodes:(this.children.get(n.node_id)??[]).map(c=>({ref:this.ref(c.node_id),name:c.name,modules:names(c.modules)}))};
   return {...result,modules:Object.fromEntries(modules.map(([id,spec])=>[id,this.brief(spec[section],args.fields)]))};
  })};
 }
 inspectEdges(args){
  this.check(args);if(!args.edges?.length&&!args.nodes?.length)throw Error('请指定 edges 或 nodes');
  if((args.edges?.length??0)>24)throw Error('每次最多查询 24 条连线');
  const nodeIds=args.nodes?new Set(this.refs(args.nodes).map(n=>n.node_id)):null;
  const chosen=args.edges?new Set(args.edges.map(r=>{const e=this.links.find(e=>e.ref===r||e.id===r);if(!e)throw Error('找不到连线 '+r);return e.ref;})):null;
  const filtered=this.links.filter(e=>(!chosen||chosen.has(e.ref))&&(!nodeIds||nodeIds.has(e.source)||nodeIds.has(e.target))&&this.channelMatches(e,args.channels,args.channel_mode));
  const {items,page,total,pages}=paginate(filtered,args,24);
  return {...this.base(),total,page,pages,edges:items.map(e=>({ref:e.ref,source:this.ref(e.source),target:this.ref(e.target),...copy(e.metadata)}))};
 }
 inspectModules(args){
  this.check(args);if(!Array.isArray(args.modules)||!args.modules.length||args.modules.length>8)throw Error('每次提供 1–8 个模块 ID');
  const section=args.section??'interface';if(!['interface','config_schema','state_schema','files'].includes(section))throw Error('未知模块查询部分');
  return {...this.base(),modules:[...new Set(args.modules)].map(id=>{
   const resource=this.snapshot.resources?.[id];if(!resource)return {id,unavailable:true};const manifest=resource.release.manifest;
   if(section==='files')return {id,files:names(resource.files)};
   if(section!=='interface')return {id,[section]:manifest[section]??{}};
   return {id,name:manifest.name,description:short(manifest.description,500),requires:manifest.requires??[],operations:(manifest.operations??[]).map(op=>({name:op.name,description:short(op.description,220),channels:op.channels??[],required:op.parameters?.required??[],parameters:names(op.parameters?.properties)})),tools:(manifest.agent_tools??[]).map(t=>({id:t.id,name:t.name,operation:t.operation,description:short(t.description,180)}))};
  })};
 }
 channelMatches(e,channels,mode='allow'){
  if(!channels?.length)return true;
  const own=e.metadata?.channels??[],denied=e.metadata?.attributes?.channel_mode==='deny';
  const match=channels.some(c=>denied?!own.includes(c):own.includes(c));return mode==='deny'?!match:match;
 }
 view(args={}){
  this.check(args);if(args.channel_mode&&!['allow','deny'].includes(args.channel_mode))throw Error('channel_mode 仅支持 allow 或 deny');
  const targeted=!!(args.query||args.types?.length||args.modules?.length),includeSubnodes=args.include_subnodes??targeted,includeText=args.include_text??targeted;
  const selectedEdges=new Set(this.snapshot.selection?.edges??[]),selectedIds=new Set(this.snapshot.selection?.nodes??[]);
  for(const e of this.links)if(selectedEdges.has(e.id)||selectedEdges.has(e.ref)){if(this.byId.has(e.source))selectedIds.add(e.source);if(this.byId.has(e.target))selectedIds.add(e.target);}
  const explicit=args.nodes?.length?this.refs(args.nodes,36):args.selected?[...selectedIds].map(id=>this.node(id)):null;
  const seeds=explicit?new Set(explicit.map(n=>n.node_id)):null;let candidates=seeds?new Set(seeds):new Set(this.byId.keys());
  const depth=args.hops??(seeds?1:0);if(!Number.isInteger(depth)||depth<0||depth>3)throw Error('hops 范围为 0–3');
  const links=this.links.filter(e=>this.channelMatches(e,args.channels,args.channel_mode));
  const expand=()=>{if(includeSubnodes){let previous=-1;while(previous!==candidates.size){previous=candidates.size;for(const n of this.nodes)if(n.type==='subnode'&&candidates.has(n.parameters?.parent_id))candidates.add(n.node_id);}}};
  expand();if(seeds)for(let i=0;i<depth;i++){const previous=new Set(candidates);for(const e of links)if(previous.has(e.source)||previous.has(e.target)){candidates.add(e.source);candidates.add(e.target);}expand();}
  const connected=args.channels?.length?new Set(links.flatMap(e=>[e.source,e.target])):null;
  let filtered=this.nodes.filter(n=>candidates.has(n.node_id)&&(!connected||connected.has(n.node_id)||seeds?.has(n.node_id))
   &&(includeSubnodes||n.type!=='subnode'||seeds?.has(n.node_id))&&(includeText||!this.passiveText(n)||seeds?.has(n.node_id))
   &&(!args.types?.length||args.types.includes(n.type))&&(!args.modules?.length||args.modules.some(m=>Object.hasOwn(n.modules??{},m)))
   &&(!args.query||[n.name,n.node_id,...names(n.modules)].join(' ').toLowerCase().includes(args.query.toLowerCase())));
  filtered.sort((a,b)=>Number(this.ref(a.node_id).slice(1))-Number(this.ref(b.node_id).slice(1)));
  // Image overviews include every matching node unless pagination was requested.
  // A short textual index is independent from the complete visual projection.
  const complete=args.image!==false&&args.page===undefined&&args.page_size===undefined;
  const {items,page,total,pages}=complete?{items:filtered,page:1,total:filtered.length,pages:1}:paginate(filtered,args,24,36),ids=new Set(items.map(n=>n.node_id));
  const visible=links.filter(e=>ids.has(e.source)&&ids.has(e.target));
  const grouped=new Map();for(const e of visible){const key=e.source+'\0'+e.target;let group=grouped.get(key);if(!group){group={source:this.ref(e.source),target:this.ref(e.target),refs:[],channels:new Set(),selected:false};grouped.set(key,group);}group.refs.push(e.ref);if(selectedEdges.has(e.id)||selectedEdges.has(e.ref))group.selected=true;for(const c of e.metadata.channels??[])group.channels.add((e.metadata.attributes?.channel_mode==='deny'?'!':'')+c);if(e.metadata.attributes?.channel_mode==='deny'&&!e.metadata.channels?.length)group.channels.add('*');}
  const channels=new Map();for(const e of visible)for(const c of e.metadata.channels??[]){const count=channels.get(c)??{allow_edges:0,deny_edges:0};count[e.metadata.attributes?.channel_mode==='deny'?'deny_edges':'allow_edges']++;channels.set(c,count);}
  const nodes=items.slice(0,args.image===false?items.length:24).map(n=>this.summary(n)),groups=[...grouped.values()].map(g=>({...g,channels:[...g.channels]}));
  const summary={...this.base(),counts:{total_nodes:this.nodes.length,total_edges:this.links.length,matched_nodes:total,shown_nodes:items.length,shown_edges:visible.length,boundary_edges:links.filter(e=>ids.has(e.source)!==ids.has(e.target)).length},page,pages,nodes,channels:[...channels].map(([name,count])=>({name,...count})),...(!seeds&&!targeted?{available_channels:[...new Set(this.links.flatMap(e=>e.metadata.channels??[]))]}:{}),filters:{include_subnodes:includeSubnodes,include_text:includeText,...Object.fromEntries(Object.entries(args).filter(([k])=>!['snapshot','image'].includes(k)))},hint:'编号筛选后不变。inspect_nodes 批量查看模块表；inspect_edges 查看准确方向与频道；inspect_modules 查看接口。虚线表示亚节点归属，不是网络连线。业务调用请使用 inspect_nodes 返回的真实 ID。'};
  if(items.length>nodes.length)summary.index_omitted=items.length-nodes.length;
  return {summary,scene:{snapshot:this.id,title:args.query?'筛选：'+short(args.query,50):seeds?'局部网络':this.snapshot.target?.kind==='preset'?this.snapshot.preset?.name??'预设网络':'网络总览',page,pages,counts:summary.counts,showEdgeIds:!!args.show_edge_ids,showChannels:!!args.show_channels,nodes:items.map(n=>({ref:this.ref(n.node_id),id:n.node_id,name:n.name,type:n.type,modules:n.modules?Object.fromEntries(names(n.modules).map(id=>[id,{}])):{},offered_tools:this.localTools(n).map(ref=>({ref})),parameters:n.type==='subnode'?{parent_id:n.parameters?.parent_id}:{},selected:(this.snapshot.selection?.nodes??[]).includes(n.node_id),subnodes:(this.children.get(n.node_id)??[]).length})),edges:groups,ownership:items.filter(n=>n.type==='subnode'&&ids.has(n.parameters?.parent_id)).map(n=>({source:this.ref(n.parameters.parent_id),target:this.ref(n.node_id)}))}};
 }
 async execute(name,args,render){
  if(name==='inspect_nodes')return this.inspectNodes(args);
  if(name==='inspect_edges')return this.inspectEdges(args);
  if(name==='inspect_modules')return this.inspectModules(args);
  if(name!=='view_network')throw Error('未知观察工具');
  this.check(args);
  if(args.region||args.view){
   if(typeof args.view!=='string'||!/^V[a-f0-9]{16}$/.test(args.view)||typeof args.region!=='string'||!/^R[1-9]\d{0,4}$/.test(args.region))throw Error('局部图需要概览返回的 view 和 region（如 R2）。');
   if(Object.keys(args).some(k=>!['snapshot','view','region','source','refresh','image'].includes(k)))throw Error('局部图沿用原概览的筛选和布局；改变筛选请重新请求概览。');
   if(args.image===false)throw Error('纯文本查询请使用 nodes/hops 或频道筛选，不使用图片区域。');
   const picture=await render({snapshot:this.id,view:args.view,region:args.region}),{image,...info}=picture;
   const refs=info.visible_nodes??[];delete info.visible_nodes;
   return this.picture({...this.base(),...info,nodes:refs.slice(0,24).map(r=>this.summary(this.node(r))),...(refs.length>24?{index_omitted:refs.length-24}:{}),hint:'局部与概览沿用同一布局和编号，窗口重叠至少28%。跨框连线可能被裁切；准确方向和属性用 inspect_edges 查询。'},image);
  }
  const view=this.view(args);if(args.image===false){const page=args.edge_page??1,pages=Math.max(1,Math.ceil(view.scene.edges.length/40));if(!Number.isInteger(page)||page<1||page>pages)throw Error('edge_page 超出范围，共 '+pages+' 页');return {...view.summary,edge_page:page,edge_pages:pages,edges:view.scene.edges.slice((page-1)*40,page*40).map(e=>({source:e.source,target:e.target,refs:e.refs.slice(0,8),parallel_edges:e.refs.length,channels:e.channels}))};}
  try{const rendered=await render(view.scene),{image,...info}=typeof rendered==='string'?{image:rendered}:rendered;return this.picture({...view.summary,...info,...(info.regions?.length?{detail_hint:'概览框内文字较小，需要时用 view_network({view:"'+info.view+'",region:"R1"}) 查看局部。布局和 N/E 编号不变；也可按节点或频道另开筛选视图。'}:{})},image);}
  catch(error){return {...view.summary,image_unavailable:short(error.message,240),hint:'图片暂不可用；可继续用编号批量查询。'+view.summary.hint};}
 }
 picture(summary,image){return {format:'nexarbor-tool-content/v1',content:[{type:'text',text:JSON.stringify(summary)},{type:'image',name:'网络-'+this.id.slice(0,8)+(summary.region?'-'+summary.region:'')+'.png',mediaType:'image/png',data:image}]};}
}
function paginate(items,args,size,max=size){const page=args.page??1,limit=args.page_size??size;if(!Number.isInteger(page)||page<1||!Number.isInteger(limit)||limit<1||limit>max)throw Error('分页参数无效，每页最多 '+max+' 项');const pages=Math.max(1,Math.ceil(items.length/limit));if(page>pages)throw Error('页码超出范围，共 '+pages+' 页');return {items:items.slice((page-1)*limit,page*limit),page,total:items.length,pages};}

const str={type:'string'},list=(max=12)=>({type:'array',items:str,maxItems:max,minItems:1}),integer=(max)=>({type:'integer',minimum:1,maximum:max}),tool=(name,description,properties,required=[])=>({name,description,parameters:{type:'object',properties:{snapshot:str,...properties},required,additionalProperties:false}});
export const observerTools=[
 tool('view_network','查看带 N节点/E连线编号的网络图片和简短索引。初次默认总览：折叠亚节点、隐藏纯资料文本，活动文本仍显示。图片包含所有匹配节点，文字索引最多24项；小图直接清晰显示，大图自动画 R区域框，返回 view；用 view+region(如 R2) 按需查看重叠局部，沿用原布局/筛选，不能同时传新筛选。也可 nodes+hops 看邻域，按类型/模块/频道/名称筛选；include_subnodes/include_text 展开，show_edge_ids/show_channels 按需标注。只读，编号跨筛选稳定。image=false 为分页紧凑拓扑；显式 page/page_size 可分页图片。',{view:str,region:str,nodes:list(36),selected:{type:'boolean'},hops:{type:'integer',minimum:0,maximum:3},include_subnodes:{type:'boolean'},include_text:{type:'boolean'},types:list(),modules:list(),channels:list(24),channel_mode:{enum:['allow','deny']},query:str,show_edge_ids:{type:'boolean'},show_channels:{type:'boolean'},image:{type:'boolean',default:true},edge_page:integer(10000),page:integer(10000),page_size:integer(36)}),
 tool('inspect_nodes','一次读取 1–12 个 N编号或真实 ID。默认 section=modules：本节点模块表，另列亚节点，不混装配表。summary 看节点说明/亚节点/执行入口；settings 看节点参数和执行绑定；tools 看工具；config 是配置，state 是快照中的运行状态，勿把初始配置当现状；仅需要时查询，可用 modules 和 fields 缩小到具体模块、顶层字段。',{nodes:list(),section:{enum:['summary','modules','tools','config','state','settings']},modules:list(),fields:list(24)},['nodes']),
 tool('inspect_edges','一次读取最多 24 个 E编号，或指定最多 12 个 nodes 查询相邻边。返回精确方向、频道、阈值等；平行边各有独立编号。支持频道筛选和分页。',{edges:list(24),nodes:list(),channels:list(24),channel_mode:{enum:['allow','deny']},page:integer(10000),page_size:integer(24)}),
 tool('inspect_modules','一次查看 1–8 个本快照已用模块接口：说明、操作及参数名、直接依赖、携带工具。需要时用 section=config_schema/state_schema/files；源码或教程用 read_resource 按文件/行读取。不会自动读取模块状态或源码正文。',{modules:list(8),section:{enum:['interface','config_schema','state_schema','files']}},['modules'])
];

export const observerResourceTool=tool('read_resource','按需读取已用模块的文档和源码；省略 file 只列文件和说明。正文按行分页，最多300行。接口或 Schema 优先 inspect_modules。',{module:str,file:str,start_line:integer(1000000),line_count:integer(300)},['module']);
export function readObservedResource(snapshot,snapshotId,args){
 const resource=snapshot.resources?.[args.module];if(!resource)throw Error('模块不在当前授权快照内');
 if(!args.file)return {snapshot:snapshotId,module:args.module,name:resource.release.manifest.name,description:short(resource.release.manifest.description,300),files:names(resource.files)};
 if(!Object.hasOwn(resource.files,args.file))throw Error('文件不在当前模块快照内');
 const lines=String(resource.files[args.file]).split('\n'),start=Math.max(0,(args.start_line??1)-1),count=Math.min(300,Math.max(1,args.line_count??100));
 return {snapshot:snapshotId,module:args.module,file:args.file,total_lines:lines.length,text:lines.slice(start,start+count).join('\n')};
}
