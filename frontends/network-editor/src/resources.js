const clone=value=>structuredClone(value);
export const isAsset=value=>!!value?.asset&&['tool','module'].includes(value.asset.kind);
export const resourceTitle=value=>`${value.name}：${value.description||'暂无描述'}`;
export const resourceId=value=>value.asset?.id??value.resourceId;
const definition=(catalog,kind,id)=>kind==='module'?catalog.modules?.[id]:kind==='tool'?catalog.tools?.find(t=>t.ref===id):catalog[kind==='node'?'nodes':'presets']?.find(t=>t.id===id);
export const resourceAvailable=(catalog,organization,kind,id)=>!!definition(catalog,kind,id)&&!organization?.[kind]?.items?.[id]?.archivedAt;
export function resource(catalog,kind,id,organization={}){
 const spec=definition(catalog,kind,id);if(!spec)throw Error('该资源已不在当前目录中');
 const item=organization[kind]?.items?.[id]??{};
 const base={kind,name:item.name??(kind==='module'?spec.label:spec.name),description:spec.description??''};
 return ['node','preset'].includes(kind)?{...base,resourceId:id,mode:spec.mode,snapshot:clone(spec.snapshot),file:spec.file,storageKind:spec.storageKind}:{...base,asset:kind==='module'?{kind,id,...clone(spec.defaults??{config:{},state:{},access:{strength:0,channels:[]}})}:{kind,id,channels:clone(spec.channels??['tools'])}};
}
export function resources(catalog,kind,organization={},includeArchived=false){
 const ids=kind==='module'?Object.keys(catalog.modules??{}):kind==='tool'?(catalog.tools??[]).map(t=>t.ref):(catalog[kind==='node'?'nodes':'presets']??[]).map(t=>t.id);return ids.filter(id=>includeArchived||resourceAvailable(catalog,organization,kind,id)).map(id=>resource(catalog,kind,id,organization));
}
export function attachResource(document,nodeId,asset,catalog,organization={}){
 if(!resourceAvailable(catalog,organization,asset.kind,asset.id))throw Error('资源已归档或删除，请先恢复');
 const next=clone(document),node=next.network.nodes.find(n=>n.node_id===nodeId);if(!node)throw Error('请把资源拖到节点上');
 const visiting=new Set(),done=new Set();
 const mount=(id,spec,explicit=false)=>{
  if(visiting.has(id))throw Error('模块依赖成环：'+id);
  if(done.has(id)&&!explicit)return;
  const definition=catalog.modules?.[id];if(!definition)throw Error('缺少依赖模块：'+id);
  if(definition.node_types&&!definition.node_types.includes(node.type))throw Error('此模块或依赖不支持该节点类型：'+id);
  if(!node.modules[id]&&!resourceAvailable(catalog,organization,'module',id))throw Error('依赖模块已归档或删除：'+id);
  visiting.add(id);for(const dependency of definition.requires??[])mount(dependency);visiting.delete(id);done.add(id);
  if(!node.modules[id]||explicit){const selected=spec??definition.defaults??{config:{},state:{},access:{strength:0,channels:[]}};node.modules[id]={config:clone(selected.config),state:clone(node.modules[id]?.state??selected.state??{}),access:clone(selected.access??definition.defaults?.access??{strength:0,channels:[]})};}
 };
 if(asset.kind==='module'){
  const definition=catalog.modules?.[asset.id];if(!definition)throw Error('模块已不在当前组件库');
  if(definition.node_types&&!definition.node_types.includes(node.type))throw Error('此模块不支持该节点类型');
  mount(asset.id,asset,true);
 }else if(asset.kind==='tool'){
  if(!catalog.tools?.some(t=>t.ref===asset.id))throw Error('工具已不在当前工具目录');
  const tool=catalog.tools.find(t=>t.ref===asset.id);for(const dependency of tool.requires??[])mount(dependency);
  if(tool.module){mount(tool.module);return next;}
  node.offered_tools??=[];const index=node.offered_tools.findIndex(t=>t.ref===asset.id),offer={ref:asset.id,channels:clone(asset.channels)};
  if(index<0)node.offered_tools.push(offer);else node.offered_tools[index]=offer;
 }else throw Error('无效资源类型');
 return next;
}
export function nodeTools(node,catalog){
 const offered=(node.offered_tools??[]).map(t=>clone(t)),seen=new Set(offered.map(t=>t.ref));
 for(const tool of catalog.tools??[])if(tool.module&&node.modules[tool.module]&&!seen.has(tool.ref)){offered.push({ref:tool.ref,channels:clone(tool.channels??[]),module:tool.module});seen.add(tool.ref);}
 return offered;
}
export function completeModules(document,catalog){
 let result=document;
 for(const node of document.network.nodes)for(const [id,spec] of Object.entries(node.modules??{}))if(catalog.modules?.[id])result=attachResource(result,node.node_id,{kind:'module',id,...clone(spec)},catalog);
 return result;
}
export function resourceRelations(value,catalog){
 const definition=value.asset?.kind==='module'?catalog.modules?.[value.asset.id]:catalog.tools?.find(t=>t.ref===value.asset?.id);
 return {modules:definition?.requires??[],tools:definition?.tools??[]};
}
export function attachResources(document,nodeId,assets,catalog,organization={}){
 if(!assets.length)throw Error('请选择工具或模块');return assets.reduce((next,asset)=>attachResource(next,nodeId,asset,catalog,organization),document);
}
export function folderResources(tree,entries,id){
 const folders=new Set([id]);for(const parent of folders)for(const f of tree.folders)if(f.parent===parent)folders.add(f.id);return entries.filter(e=>folders.has(tree.items[resourceId(e)]?.folder??null));
}
export const assetHistory=book=>({kind:book.asset.kind,id:book.id??book.asset.id,label:book.name,description:book.description??'',asset:clone(book.asset)});
export const contentType=value=>isAsset(value)?value.asset.kind:!value.snapshot?.nodes.length?'edge':value.snapshot.nodes.length===1?'node':'network';
export const matchesType=(value,type)=>type==='all'||contentType(value)===type||(['internal','external'].includes(type)&&contentType(value)==='network'&&value.mode===type);
