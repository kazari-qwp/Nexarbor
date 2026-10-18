const clone=value=>structuredClone(value);
export const isAsset=value=>!!value?.asset&&['tool','module'].includes(value.asset.kind);
export const resourceTitle=value=>`${value.name}：${value.description||'暂无描述'}`;
export function resource(catalog,kind,id,organization={}){
 const definition=kind==='module'?catalog.modules?.[id]:catalog.tools?.find(t=>t.ref===id);if(!definition)throw Error('该资源已不在当前目录中');
 const item=organization[kind]?.items?.[id]??{};
 return {kind,name:item.name??(kind==='module'?definition.label:definition.name),description:definition.description??'',asset:kind==='module'?{kind,id,...clone(definition.defaults??{config:{},state:{},access:{strength:0,channels:[]}})}:{kind,id,channels:['tools']}};
}
export function resources(catalog,kind,organization={}){
 const ids=kind==='module'?Object.keys(catalog.modules??{}):(catalog.tools??[]).map(t=>t.ref);return ids.map(id=>resource(catalog,kind,id,organization));
}
export function attachResource(document,nodeId,asset,catalog){
 const next=clone(document),node=next.network.nodes.find(n=>n.node_id===nodeId);if(!node)throw Error('请把资源拖到节点上');
 if(asset.kind==='module'){
  const definition=catalog.modules?.[asset.id];if(!definition)throw Error('模块已不在当前组件库');
  if(definition.node_types&&!definition.node_types.includes(node.type))throw Error('此模块不支持该节点类型');
  node.modules[asset.id]={config:clone(asset.config),state:clone(node.modules[asset.id]?.state??asset.state??{}),access:clone(asset.access??definition.defaults?.access??{strength:0,channels:[]})};
 }else if(asset.kind==='tool'){
  if(!catalog.tools?.some(t=>t.ref===asset.id))throw Error('工具已不在当前工具目录');
  node.offered_tools??=[];const index=node.offered_tools.findIndex(t=>t.ref===asset.id),offer={ref:asset.id,channels:clone(asset.channels)};
  if(index<0)node.offered_tools.push(offer);else node.offered_tools[index]=offer;
 }else throw Error('无效资源类型');
 return next;
}
export const assetHistory=book=>({kind:book.asset.kind,id:book.id??book.asset.id,label:book.name,description:book.description??'',asset:clone(book.asset)});
export const contentType=value=>isAsset(value)?value.asset.kind:!value.snapshot?.nodes.length?'edge':value.snapshot.nodes.length===1?'node':'network';
export const matchesType=(value,type)=>type==='all'||contentType(value)===type||(['internal','external'].includes(type)&&contentType(value)==='network'&&value.mode===type);
