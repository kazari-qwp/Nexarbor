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
 const next=clone(document),batch=crypto.randomUUID().slice(0,8),mapping={},paths={};
 for(const node of bookmark.snapshot.nodes)mapping[node.node_id]=node.node_id+'-copy-'+batch;
 // 一个副本拥有自己的文档空间；引用同一源文档的副本节点仍共享该副本内的文档。
 for(const name of Object.keys(bookmark.snapshot.files))paths[name]='copies/'+batch+'/'+name.split(/[\\/]/).filter(p=>p&&p!=='.'&&p!=='..'&&!p.includes(':')).join('/');
 const ids=new Set([...next.network.nodes.map(n=>n.node_id),...Object.values(mapping)]),nodes=[];
 for(const original of bookmark.snapshot.nodes){
  let node=documentRefs(clone(original),paths);node.node_id=mapping[original.node_id];node.name=original.name+' 副本';node.context_cursor=null;
  node.management_parent_id=mapping[node.management_parent_id]??(ids.has(node.management_parent_id)?node.management_parent_id:'root');
  if(node.management_parent_id===node.node_id)node.management_parent_id='root';
  node.connections.interfaces=node.connections.interfaces.map(link=>({...link,target_node_id:mapping[link.target_node_id]??link.target_node_id})).filter(link=>ids.has(link.target_node_id));
  for(const [id,spec] of Object.entries(node.modules))spec.config=schemaRefs(spec.config,catalog[id]?.schema,mapping);
  nodes.push(node);
 }
 next.network.nodes.push(...nodes);next.files??={};for(const [name,content] of Object.entries(bookmark.snapshot.files))next.files[paths[name]]=content;
 const saved=bookmark.snapshot.positions??{},source=nodes.map((_,i)=>saved[bookmark.snapshot.nodes[i].node_id]??{x:(i%4)*150,y:Math.floor(i/4)*150});
 const minX=Math.min(...source.map(p=>p.x)),minY=Math.min(...source.map(p=>p.y)),layout={...positions};
 nodes.forEach((node,i)=>layout[node.node_id]={x:point.x+source[i].x-minX,y:point.y+source[i].y-minY});
 return {document:next,layout,nodes:nodes.map(n=>n.node_id)};
}

export function bookmarkChanges(before,after){
 return [...new Set([...before,...after].map(b=>b.id))].flatMap(id=>{const a=before.find(b=>b.id===id)??null,b=after.find(b=>b.id===id)??null;return JSON.stringify(a)===JSON.stringify(b)?[]:[{id,expected:a,value:b}];});
}

// 历史复用与书签共用粘贴逻辑。单边只带终点，起点由落点决定。
export function historyBookmark(entry,bookmarks=[],document,layout={}){
 const existing=entry.kind==='bookmark'?bookmarks.find(b=>b.id===entry.id):null;
 let snapshot=existing?.snapshot??entry.snapshot;
 if(entry.kind==='edge')snapshot={nodes:[],edges:[{metadata:clone(entry.metadata),target:entry.target}],files:{},positions:{}};
 else if(entry.kind==='node'&&document?.network.nodes.some(n=>n.node_id===entry.id))snapshot=copySubnet(document,[entry.id],'external',layout);
 if(!snapshot)throw Error('该历史条目没有可复用的副本');
 return {id:entry.id,name:entry.label,mode:existing?.mode??entry.mode??'external',snapshot:clone(snapshot)};
}
