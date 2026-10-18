const clone=value=>structuredClone(value);
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
 for(const node of nodes){node.context_cursor=null;if(mode==='internal')node.connections.interfaces=node.connections.interfaces.filter(link=>selected.has(link.target_node_id));}
 // 文档作为独立副本保留，粘贴时只映射明确的路径字段。
 const names=new Set();const scan=value=>{if(typeof value==='string'&&Object.hasOwn(document.files??{},value))names.add(value);else if(Array.isArray(value))value.forEach(scan);else if(value&&typeof value==='object')Object.values(value).forEach(scan);};scan(nodes);
 return {nodes,files:Object.fromEntries([...names].map(name=>[name,document.files[name]])),positions:Object.fromEntries(ids.filter(id=>layout[id]).map(id=>[id,clone(layout[id])]))};
}
function schemaRefs(value,schema,mapping){
 if(schema?.format==='node-id'&&typeof value==='string')return mapping[value]??value;
 if(Array.isArray(value))return value.map(v=>schemaRefs(v,schema?.items,mapping));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,schemaRefs(v,schema?.properties?.[k],mapping)]));
 return value;
}
function documentRefs(value,paths){
 if(Array.isArray(value))return value.map(v=>documentRefs(v,paths));
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,(k==='file'||k==='path'||k==='document'||k.endsWith('_path'))&&typeof v==='string'&&paths[v]?paths[v]:documentRefs(v,paths)]));
 return value;
}
export function pasteSubnet(document,bookmark,point,catalog={},positions={}){
 if(!bookmark.snapshot.nodes.length)return {edges:clone(bookmark.snapshot.edges)};
 const next=clone(document),nonce=crypto.randomUUID(),mapping=Object.create(null),paths=Object.create(null),allocated=new Set(next.network.nodes.map(n=>n.node_id));
 let batch=nonce,space=1;while(Object.keys(next.files??{}).some(name=>name.startsWith('copies/'+batch+'/')))batch=nonce+'-'+space++;
 if(new Set(bookmark.snapshot.nodes.map(n=>n.node_id)).size!==bookmark.snapshot.nodes.length)throw Error('副本中有重复节点编号');
 for(const node of bookmark.snapshot.nodes){
  const base=node.node_id.split('-copy-')[0].slice(0,120)+'-copy-'+batch;let id=base,index=1;
  while(allocated.has(id))id=base+'-'+index++;
  mapping[node.node_id]=id;allocated.add(id);
 }
 // 一个副本拥有自己的文档空间；引用同一源文档的副本节点仍共享该副本内的文档。
 for(const name of Object.keys(bookmark.snapshot.files))paths[name]='copies/'+batch+'/'+name.split(/[\\/]/).filter(p=>p&&p!=='.'&&p!=='..'&&!p.includes(':')).join('/');
 const ids=new Set([...next.network.nodes.map(n=>n.node_id),...Object.values(mapping)]),nodes=[];
 for(const original of bookmark.snapshot.nodes){
  let node=documentRefs(clone(original),paths);node.node_id=mapping[original.node_id];node.context_cursor=null;
  node.management_parent_id=mapping[node.management_parent_id]??(ids.has(node.management_parent_id)?node.management_parent_id:'root');
  if(node.management_parent_id===node.node_id)node.management_parent_id='root';
  node.connections.interfaces=node.connections.interfaces.map(link=>({...link,target_node_id:mapping[link.target_node_id]??link.target_node_id})).filter(link=>ids.has(link.target_node_id));
  for(const [id,spec] of Object.entries(node.modules)){
   spec.config=schemaRefs(spec.config,catalog[id]?.schema,mapping);
   spec.state=schemaRefs(spec.state,catalog[id]?.state_schema,mapping);
  }
  nodes.push(node);
 }
 next.network.nodes.push(...nodes);next.files??={};for(const [name,content] of Object.entries(bookmark.snapshot.files))next.files[paths[name]]=content;
 const saved=bookmark.snapshot.positions??{},source=nodes.map((_,i)=>saved[bookmark.snapshot.nodes[i].node_id]??{x:(i%4)*150,y:Math.floor(i/4)*150});
 const minX=Math.min(...source.map(p=>p.x)),minY=Math.min(...source.map(p=>p.y)),layout={...positions};
 nodes.forEach((node,i)=>layout[node.node_id]={x:point.x+source[i].x-minX,y:point.y+source[i].y-minY});
 return {document:next,layout,nodes:nodes.map(n=>n.node_id)};
}

// 历史复用与书签共用粘贴逻辑。单边只带终点，起点由落点决定。
export function historyBookmark(entry,bookmarks=[],document,layout={}){
 if(entry.asset)return {id:entry.id,kind:entry.kind,name:entry.label,description:entry.description??'',asset:clone(entry.asset)};
 let snapshot=entry.snapshot;
 if(!snapshot&&entry.kind==='edge')snapshot={nodes:[],edges:[{metadata:clone(entry.metadata),...(entry.target?{target:entry.target}:{})}],files:{},positions:{}};
 if(!snapshot)throw Error('该历史条目没有可复用的副本');
 return {id:entry.id,name:entry.label,mode:entry.mode??'external',snapshot:clone(snapshot)};
}
