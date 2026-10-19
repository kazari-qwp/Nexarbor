import {useEffect,useRef,useState} from 'react';
import {copySubnet,pasteSubnet,selectionKey,historyBookmark} from './subnets.js';
import {shortcuts} from './shortcuts.js';
import {textPrompt} from './text-prompt.js';
import {isAsset,resource,assetHistory} from './resources.js';
const clone=value=>structuredClone(value);
const empty={version:0,bookmarks:[],history:[],presets:[],categories:[{id:'default',name:'默认分类'}],settings:{},assets:{}};
export function useBookmarks({api,context,onPaste,onEdgeTemplate,onLocate,onOpenAsset,onAssetAttach,note}){
 const [library,setLibrary]=useState(empty),[category,setCategory]=useState('default'),[focus,setFocus]=useState(null),[open,setOpen]=useState(true);
 const current=useRef(empty),latest=useRef(),hover=useRef(null),lastCopy=useRef(null),pointer=useRef(null);
 const queue=useRef(Promise.resolve()),pending=useRef(0),presetFolder=useRef(null),nodeFolder=useRef(null);
 const enqueue=job=>{pending.current++;const result=queue.current.then(job).finally(()=>pending.current--);queue.current=result.catch(()=>{});return result;};
 latest.current={context,onPaste,onEdgeTemplate,onLocate,onOpenAsset,onAssetAttach,note,category};
 const accept=value=>{if(value.version>=current.current.version){current.current=value;setLibrary(value);}return value;};
 useEffect(()=>{api('editor.library.index').then(accept).catch(note);},[]);
 useEffect(()=>{const track=e=>{pointer.current={x:e.clientX,y:e.clientY};};window.addEventListener('pointermove',track,true);return()=>window.removeEventListener('pointermove',track,true);},[]);
 const hovered=()=>{
  const point=pointer.current??hover.current?.point;if(!point)return hover.current;
  const element=document.elementFromPoint(point.x,point.y),book=element?.closest('[data-bookmark-id]'),history=element?.closest('[data-history-kind]'),item=element?.closest('[data-resource-kind]');
  let area=null;
  if(book||element?.closest('.bookmark-items'))area={kind:'bookmark',id:book?.dataset.bookmarkId??null,point};
  else if(history){const entry=current.current.history.find(e=>e.kind===history.dataset.historyKind&&e.id===history.dataset.historyId);if(entry)area={kind:'history',entry};}
  else if(item)area={kind:'resource',resource:{kind:item.dataset.resourceKind,id:item.dataset.resourceId}};
  else if(element?.closest('.node-link-gesture'))area={kind:'canvas'};
  hover.current=area;return area;
 };
 const hydrate=async value=>value.lazySnapshot?{...value,...await api('editor.resource.load',{kind:value.kind,id:value.resourceId}),lazySnapshot:false}:value;
 const update=p=>api('editor.library.update',{...p,summary:true}).then(accept);
 const record=entries=>{if(entries.length)enqueue(()=>update({action:'history.push',entries})).catch(latest.current.note);};
 const patch=changes=>update({action:'bookmark.patch',changes});
 const remove=async id=>{const book=current.current.bookmarks.find(b=>b.id===id);if(book)await patch([{id,expected:book,value:null}]);lastCopy.current=null;};
 const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
 const removeHovered=()=>{
  const point=hover.current?.point;if(!point)return Promise.resolve();
  return enqueue(async()=>{
   // 列表删除后会补位；鼠标静止时不会再触发 pointerenter，按当前落点重新命中。
   await frame();const element=document.elementFromPoint(point.x,point.y)?.closest('[data-bookmark-id]');
   if(!element)return;const id=element.dataset.bookmarkId;hover.current={kind:'bookmark',id,point};await remove(id);await frame();
  });
 };
 const copy=async(mode,frame)=>{
  const {area,ctx,category}=frame;let snapshot,signature,preset;
  if(area?.kind==='bookmark'){await remove(area.id);return;}
  if(area?.kind==='resource'){preset=resource(ctx.assetsCatalog,area.resource.kind,area.resource.id,current.current.assets);signature='resource:'+area.resource.kind+':'+area.resource.id;}
  else if(area?.kind==='history'&&isAsset(area.entry)){preset=historyBookmark(area.entry);signature='history:'+area.entry.kind+':'+area.entry.id;}
  else if(area?.kind==='history'){
   const e=area.entry;signature='history:'+e.kind+':'+e.id;preset=historyBookmark(e);
  }else{
   signature=selectionKey(ctx.selection);snapshot=copySubnet(ctx.document,ctx.selection.nodes,mode,ctx.layout,ctx.selection.edges);
  }
  if(preset&&!isAsset(preset)){
   preset=await hydrate(preset);
   const old=preset.snapshot;if(!old.nodes.length&&!old.edges?.length)throw Error('空网络没有可保存的书签内容');snapshot=old.nodes.length?{...copySubnet({network:{nodes:old.nodes},files:old.files},old.nodes.map(n=>n.node_id),mode,old.positions),...(old.edges?.length?{edges:clone(old.edges)}:{})}:{...clone(old),edges:old.edges.map(edge=>({metadata:clone(edge.metadata),...(mode==='external'&&edge.target?{target:edge.target}:{})}))};preset=null;
  }
  signature=category+':'+signature;
  if(frame.toggle!==false&&lastCopy.current?.signature===signature&&lastCopy.current.mode===mode&&current.current.bookmarks.some(b=>b.id===lastCopy.current.id)){await remove(lastCopy.current.id);return;}
  const book=preset?{id:crypto.randomUUID(),name:preset.name,description:preset.description,kind:preset.asset.kind,asset:clone(preset.asset),category,createdAt:Date.now()}:{id:crypto.randomUUID(),name:snapshot.nodes.length===1?snapshot.nodes[0].name:snapshot.nodes.length?snapshot.nodes.length+' 节点子网':'连接书签',mode,category,createdAt:Date.now(),snapshot};
  await patch([{id:book.id,expected:null,value:book}]);lastCopy.current=frame.toggle===false?null:{id:book.id,signature,mode};setFocus(book.id);setOpen(true);
 };
 const created=(before,after,layout={})=>{
  lastCopy.current=null;const entries=[],oldIds=new Set(before.network.nodes.map(n=>n.node_id));
  for(const n of after.network.nodes){
   if(!oldIds.has(n.node_id))entries.push({kind:'node',id:n.node_id,label:n.name,snapshot:copySubnet(after,[n.node_id],'external',layout)});
   const previous=before.network.nodes.find(o=>o.node_id===n.node_id)?.connections.interfaces.length??0;
   n.connections.interfaces.slice(previous).forEach((link,i)=>entries.push({kind:'edge',id:n.node_id+'|'+(previous+i),label:n.name+' → '+(after.network.nodes.find(t=>t.node_id===link.target_node_id)?.name??link.target_node_id),source:n.node_id,target:link.target_node_id,metadata:clone(link.metadata)}));
  }
  record(entries);
 };
 const usedBook=book=>record([isAsset(book)?assetHistory(book):{kind:'bookmark',id:book.id??book.resourceId??crypto.randomUUID(),label:book.name,mode:book.mode,snapshot:clone(book.snapshot)}]);
 const historyEntry=ref=>current.current.history.find(e=>e.kind===ref.kind&&e.id===ref.id);
 const usedHistory=ref=>{const entry=historyEntry(ref);if(entry)record([entry]);};
 const place=(book,point,usage)=>{
  const ctx=latest.current.context();
  if(isAsset(book)){const nodeId=document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id;if(!nodeId)throw Error('请把工具或模块拖到节点上');latest.current.onAssetAttach([book],nodeId);if(usage.usedBookmark)usedBook(book);else usedHistory(usage.usedHistory);return;}
  const source=document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id;
  const result=pasteSubnet(ctx.document,book,ctx.flow.screenToFlowPosition(point),ctx.catalog,ctx.layout,{source});
  const used=()=>usage.usedBookmark?usedBook(book):usedHistory(usage.usedHistory);
  if(result.edges){
   const source=document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id??'';
   const missing=result.edges.some(e=>!ctx.document.network.nodes.some(n=>n.node_id===e.target));
   if(source&&!missing){const next=clone(ctx.document),n=next.network.nodes.find(n=>n.node_id===source);for(const e of result.edges)n.connections.interfaces.push({target_node_id:e.target,metadata:clone(e.metadata)});latest.current.onPaste({document:next,layout:ctx.layout,nodes:[source]});used();}
   else{const templates=result.edges.map(e=>({source,target:ctx.document.network.nodes.some(n=>n.node_id===e.target)?e.target:'',...e.metadata,...usage}));latest.current.onEdgeTemplate({...templates[0],queue:templates.slice(1),point});}
  }else{latest.current.onPaste(result);used();}
 };
 const drop=(id,point)=>{const book=current.current.bookmarks.find(b=>b.id===id);if(!book)throw Error('书签已不存在');place(book,point,{usedBookmark:id});};
 const dropHistory=(ref,point)=>{const entry=historyEntry(ref);if(!entry)throw Error('该历史条目已移除');const ctx=latest.current.context();place(historyBookmark(entry,current.current.bookmarks,ctx.document,ctx.layout),point,{usedHistory:ref});};
 const dropResource=async(ref,point)=>{
  const ctx=latest.current.context(),presets=[...new Set(ref.ids??[ref.id])].map(id=>resource(ctx.assetsCatalog,ref.kind,id,current.current.assets));
  if(presets.every(isAsset)){const nodeId=document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id;if(!nodeId)throw Error('请把工具或模块拖到节点上');latest.current.onAssetAttach(presets,nodeId);record(presets.map(assetHistory));return;}
  for(let i=0;i<presets.length;i++)presets[i]=await hydrate(presets[i]);
  // 等待磁盘快照期间用户仍可编辑；只合并到最新草稿，避免覆盖其他操作。
  const latestContext=latest.current.context();
  let result={document:latestContext.document,layout:latestContext.layout,nodes:[]};const position=ctx.flow.screenToFlowPosition(point),ids=[];
  for(const [i,preset] of presets.entries()){result=pasteSubnet(result.document,preset,{x:position.x+i*150,y:position.y+i*70},ctx.catalog,result.layout,{source:presets.length===1?document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id:undefined});ids.push(...result.nodes);}
  latest.current.onPaste({...result,nodes:ids});presets.forEach(usedBook);
 };
 const openAsset=value=>latest.current.onOpenAsset({...clone(value),detailKey:crypto.randomUUID()});
 const saveAsset=value=>enqueue(async()=>{
  const old=value.sourceBookmark?current.current.bookmarks.find(b=>b.id===value.sourceBookmark):null;
  const book={id:old?.id??crypto.randomUUID(),name:value.name,description:value.description??'',...(isAsset(value)?{kind:value.asset.kind,asset:clone(value.asset)}:{mode:value.mode??'internal',snapshot:clone(value.snapshot)}),category:old?.category??latest.current.category,createdAt:old?.createdAt??Date.now()};
  await patch([{id:book.id,expected:old??null,value:book}]);setFocus(book.id);setCategory(book.category);setOpen(true);latest.current.note('当前配置已保存至书签');return book;
 });
 const locate=entry=>{
  if(isAsset(entry)||entry.snapshot){openAsset(historyBookmark(entry));return;}
  latest.current.onLocate(entry);
 };
 return {library,category,setCategory,focus,open,setOpen,hover,hovered,pending,afterPending:enqueue,
  copy:mode=>{const ctx=latest.current.context(),frame={area:hover.current?clone(hover.current):null,category:latest.current.category,ctx:{...ctx,document:clone(ctx.document),selection:clone(ctx.selection),layout:clone(ctx.layout)}};return enqueue(()=>copy(mode,frame));},
  copySelection:(mode,selection)=>{const ctx=latest.current.context(),frame={area:{kind:'canvas'},toggle:false,category:latest.current.category,ctx:{...ctx,document:clone(ctx.document),selection:clone(selection??ctx.selection),layout:clone(ctx.layout)}};return enqueue(()=>copy(mode,frame));},
  remove:id=>enqueue(()=>remove(id)),removeHovered,created,drop,dropHistory,dropResource,locate,record,usedHistory,saveAsset,
  openBook:book=>openAsset({...book,sourceBookmark:book.id}),
  savePreset:id=>enqueue(async()=>{const book=current.current.bookmarks.find(b=>b.id===id),node=!isAsset(book)&&book?.snapshot?.nodes.length===1;await update({action:node?'node.save':'preset.save',bookId:id,folder:node?nodeFolder.current:presetFolder.current});latest.current.note(node?'节点完整配置已保存到节点栏；官方目录或根目录下保存时归入“已保存节点”':'已保存到当前网络预设目录');}),
  saveNetwork:()=>enqueue(async()=>{const ctx=latest.current.context(),name=(await textPrompt('保存全网',(ctx.document.network.nodes[0]?.name??'未命名')+'网络'))?.trim();if(!name)return;await update({action:'network.save',name,document:clone(ctx.document),layout:clone(ctx.layout)});latest.current.note('完整网络已写入磁盘，位于“已存储网络”分类');}),
  folderChanged:(kind,id)=>{if(kind==='preset')presetFolder.current=id;if(kind==='node')nodeFolder.current=id;},
  reload:()=>enqueue(()=>api('editor.library.index').then(accept)),
  assetAction:p=>enqueue(()=>update(p)),
  bindings:shortcuts(library.settings.shortcuts),resetCopy:()=>{lastCopy.current=null;},
  async rename(book){const name=(await textPrompt('书签名称',book.name))?.trim();if(!name||name===book.name)return;await patch([{id:book.id,expected:book,value:{...book,name}}]);},
  async renameHistory(entry){const name=(await textPrompt('历史名称',entry.label))?.trim();if(!name||name===entry.label)return;await enqueue(()=>{const expected=historyEntry(entry);if(!expected)throw Error('历史条目已移除');return update({action:'history.rename',kind:entry.kind,id:entry.id,name,expected});});},
  async newCategory(){const name=(await textPrompt('新分类名称'))?.trim();if(!name)return;const item={id:crypto.randomUUID(),name};await update({action:'category.add',category:item});setCategory(item.id);},
  saveSettings:value=>enqueue(()=>update({action:'settings.save',settings:{...current.current.settings,shortcuts:value}})),
  saveView:value=>enqueue(()=>update({action:'settings.save',settings:{...current.current.settings,bookmarkView:value}})),
  togglePanel:side=>enqueue(()=>{const panels={...current.current.settings.panels};panels[side]=!panels[side];return update({action:'settings.save',settings:{...current.current.settings,panels}});}),
  savePanelWidth:(side,width)=>enqueue(()=>update({action:'settings.save',settings:{...current.current.settings,panels:{...current.current.settings.panels,[side+'Width']:width}}})),
  usedBookmark:id=>{const book=current.current.bookmarks.find(b=>b.id===id);if(book)usedBook(book);},
 };
}
