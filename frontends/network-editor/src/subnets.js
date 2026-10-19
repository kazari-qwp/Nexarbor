const clone=value=>structuredClone(value);
const normalizePath=value=>value.replaceAll('\\','/');
const dataFiles=['file_path','content_path','metadata_path','db_path'];
const dataDirectories=['directory','storage_path'];
const ownedPaths=node=>[...dataFiles,...dataDirectories].map(key=>node.parameters?.[key]).filter(value=>typeof value==='string'&&value);
function requireData(nodes,files={}){
 const names=new Set(Object.keys(files).map(normalizePath));
 for(const node of nodes)for(const field of [...dataFiles,...dataDirectories]){
  const value=node.parameters?.[field];if(typeof value!=='string'||!value)continue;const path=normalizePath(value);
  if(path.startsWith('/')||path.includes(':')||path.split('/').some(part=>part==='..'||part==='.'))throw Error('请先把节点数据导入网络目录，再复制节点');
  if(dataFiles.includes(field)&&!names.has(path))throw Error('节点数据资源缺失，不能生成只有外观的副本：'+path);
 }
}

export const selectionKey=s=>JSON.stringify([s.nodes.slice().sort(),s.edges.slice().sort()]);

export function selectionStep(nodes,edges,selected,grow=true){
 const adjacency=new Map(nodes.map(n=>['n:'+n.id,new Set()]));
 for(const edge of edges){const key='e:'+edge.id;adjacency.set(key,new Set(['n:'+edge.source,'n:'+edge.target]));for(const id of [edge.source,edge.target])adjacency.get('n:'+id)?.add(key);}
 const current=new Set([...selected.nodes.map(id=>'n:'+id),...selected.edges.map(id=>'e:'+id)].filter(id=>adjacency.has(id)));
 if(grow){for(const id of [...current])for(const other of adjacency.get(id)??[])current.add(other);}
 else{
  let boundary=[...current].filter(id=>[...adjacency.get(id)].some(n=>!current.has(n)));
  if(!boundary.length)boundary=[...current].filter(id=>adjacency.get(id).size<=1);
  if(!boundary.length&&current.size)boundary=[...current].filter(id=>adjacency.get(id).size===Math.min(...[...current].map(n=>adjacency.get(n).size)));
  for(const id of boundary)current.delete(id);
 }
 return {nodes:[...current].filter(id=>id.startsWith('n:')).map(id=>id.slice(2)),edges:[...current].filter(id=>id.startsWith('e:')).map(id=>id.slice(2))};
}

export function copySubnet(document,ids,mode,layout={},selectedEdges=[]){
 const selected=new Set(ids),nodes=clone(document.network.nodes.filter(n=>selected.has(n.node_id)));
 if(!nodes.length){
  const edges=document.network.nodes.flatMap(n=>n.connections.interfaces.flatMap((link,i)=>selectedEdges.includes(n.node_id+'|'+i)?[{metadata:clone(link.metadata),...(mode==='external'?{target:link.target_node_id}:{})}]:[]));
  if(!edges.length)throw Error('请先选中需要复制的节点或连接');
  return {nodes:[],edges,files:{},positions:{}};
 }
 requireData(nodes,document.files);
 for(const node of nodes){node.context_cursor=null;if(mode==='internal')node.connections.interfaces=node.connections.interfaces.filter(link=>selected.has(link.target_node_id));}
 // 文档作为独立副本保留，粘贴时只映射明确的路径字段。
 const names=new Set(),files=document.files??{},entries=Object.keys(files);const scan=value=>{if(typeof value==='string'){const normalized=normalizePath(value);for(const name of entries)if(normalizePath(name)===normalized)names.add(name);}else if(Array.isArray(value))value.forEach(scan);else if(value&&typeof value==='object')Object.values(value).forEach(scan);};scan(nodes.map(n=>n.type==='value'?{...n,parameters:{}}:n));
 for(const node of nodes)for(const root of ownedPaths(node))for(const name of entries)if(normalizePath(name).startsWith(normalizePath(root).replace(/\/$/,'')+'/'))names.add(name);
 // 显式选中的外部入边作为无头接入口保存；只记书签内的终点，不记原起点。
 const incoming=document.network.nodes.filter(n=>!selected.has(n.node_id)).flatMap(n=>n.connections.interfaces.flatMap((link,i)=>selectedEdges.includes(n.node_id+'|'+i)&&selected.has(link.target_node_id)?[{target:link.target_node_id,metadata:clone(link.metadata)}]:[]));
 return {nodes,...(incoming.length?{edges:incoming}:{}),files:Object.fromEntries([...names].map(name=>[name,clone(document.files[name])])),positions:Object.fromEntries(ids.filter(id=>layout[id]).map(id=>[id,clone(layout[id])]))};
}
function schemaRefs(value,schema,mapping){
 if(schema?.format==='node-id'&&typeof value==='string')return mapping[value]??value;
 if(Array.isArray(value))return value.map(v=>schemaRefs(v,schema?.items,mapping));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,schemaRefs(v,schema?.properties?.[k],mapping)]));
 return value;
}
function documentRefs(value,paths){
 if(Array.isArray(value))return value.map(v=>documentRefs(v,paths));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,(k==='file'||k==='path'||k==='document'||k==='directory'||k.endsWith('_path'))&&typeof v==='string'&&paths[v]?paths[v]:documentRefs(v,paths)]));
 return value;
}
export function pasteSubnet(document,bookmark,point,catalog={},positions={},options={}){
 if(!bookmark.snapshot.nodes.length){if(bookmark.snapshot.edges?.length)return {edges:clone(bookmark.snapshot.edges)};throw Error('空网络没有可拖入的节点，请使用“打开完整网络”');}
 requireData(bookmark.snapshot.nodes,bookmark.snapshot.files);
 const next=clone(document),nonce=crypto.randomUUID(),mapping=Object.create(null),paths=Object.create(null),allocated=new Set(next.network.nodes.map(n=>n.node_id));
 let batch=nonce,space=1;while(Object.keys(next.files??{}).some(name=>name.startsWith('copies/'+batch+'/')))batch=nonce+'-'+space++;
 if(new Set(bookmark.snapshot.nodes.map(n=>n.node_id)).size!==bookmark.snapshot.nodes.length)throw Error('副本中有重复节点编号');
 for(const node of bookmark.snapshot.nodes){
  const base=node.node_id.split('-copy-')[0].slice(0,120)+'-copy-'+batch;let id=base,index=1;
  while(allocated.has(id))id=base+'-'+index++;
  mapping[node.node_id]=id;allocated.add(id);
 }
 // 独立资源空间同时覆盖正文、数据库和整个知识目录；嵌入模型不属于节点数据。
 const copiedPath=name=>'copies/'+batch+'/'+normalizePath(name).split('/').filter(p=>p&&p!=='.'&&p!=='..'&&!p.includes(':')).join('/');
 for(const name of [...Object.keys(bookmark.snapshot.files),...bookmark.snapshot.nodes.flatMap(ownedPaths)])paths[name]=copiedPath(name);
 const ids=new Set([...next.network.nodes.map(n=>n.node_id),...Object.values(mapping)]),nodes=[];
 for(const original of bookmark.snapshot.nodes){
  let node=documentRefs({...clone(original),parameters:{}},paths);node.parameters=clone(original.parameters);for(const field of [...dataFiles,...dataDirectories])if(typeof node.parameters[field]==='string'&&paths[node.parameters[field]])node.parameters[field]=paths[node.parameters[field]];node.node_id=mapping[original.node_id];node.context_cursor=null;
  for(const reference of node.execution?.prepare??[])if(reference.node)reference.node=mapping[reference.node]??reference.node;
  node.management_parent_id=mapping[node.management_parent_id]??(ids.has(node.management_parent_id)?node.management_parent_id:null);
  if(node.management_parent_id===node.node_id)node.management_parent_id=null;
  node.connections.interfaces=node.connections.interfaces.map(link=>({...link,target_node_id:mapping[link.target_node_id]??link.target_node_id})).filter(link=>ids.has(link.target_node_id));
  for(const [id,spec] of Object.entries(node.modules)){
   spec.config=schemaRefs(spec.config,catalog[id]?.schema,mapping);
   spec.state=schemaRefs(spec.state,catalog[id]?.state_schema,mapping);
  }
  nodes.push(node);
 }
 next.network.nodes.push(...nodes);next.files??={};for(const [name,content] of Object.entries(bookmark.snapshot.files))next.files[paths[name]]=clone(content);
 // 只按快照的最终结构判断，和选择／保存入口及数组顺序无关。
 const incoming=(bookmark.snapshot.edges??[]).filter(e=>!e.source),entry=incoming.length===1?incoming[0]:null,from=next.network.nodes.find(n=>n.node_id===options.source),entryTarget=entry&&mapping[entry.target];
 const attachedEntry=!!(from&&entryTarget);if(attachedEntry)from.connections.interfaces.push({target_node_id:entryTarget,metadata:clone(entry.metadata)});
 const placement=attachedEntry?{x:point.x+140,y:point.y-40}:point;
 const saved=bookmark.snapshot.positions??{},source=nodes.map((_,i)=>saved[bookmark.snapshot.nodes[i].node_id]??{x:(i%4)*150,y:Math.floor(i/4)*150});
 const minX=Math.min(...source.map(p=>p.x)),minY=Math.min(...source.map(p=>p.y)),layout={...positions};
 nodes.forEach((node,i)=>layout[node.node_id]={x:placement.x+source[i].x-minX,y:placement.y+source[i].y-minY});
 return {document:next,layout,nodes:nodes.map(n=>n.node_id),attachedEntry};
}

// 历史复用与书签共用粘贴逻辑。单边只带终点，起点由落点决定。
export function historyBookmark(entry,bookmarks=[],document,layout={}){
 if(entry.asset)return {id:entry.id,kind:entry.kind,name:entry.label,description:entry.description??'',asset:clone(entry.asset)};
 let snapshot=entry.snapshot;
 if(!snapshot&&entry.kind==='edge')snapshot={nodes:[],edges:[{metadata:clone(entry.metadata),...(entry.target?{target:entry.target}:{})}],files:{},positions:{}};
 if(!snapshot)throw Error('该历史条目没有可复用的副本');
 return {id:entry.id,name:entry.label,mode:entry.mode??'external',snapshot:clone(snapshot)};
}
