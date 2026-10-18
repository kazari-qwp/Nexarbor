import {useEffect,useRef,useState} from 'react';
import {bookmarkChanges,copySubnet,pasteSubnet,selectionKey,historyBookmark} from './subnets.js';
import {shortcuts} from './shortcuts.js';
import {textPrompt} from './text-prompt.js';
const clone=value=>structuredClone(value);
const empty={version:0,bookmarks:[],history:[],categories:[{id:'default',name:'默认分类'}],settings:{}};
export function useBookmarks({api,context,onPaste,onEdgeTemplate,onLocate,note,undo,redo}){
 const [library,setLibrary]=useState(empty),[category,setCategory]=useState('default'),[focus,setFocus]=useState(null),[open,setOpen]=useState(true);
 const current=useRef(empty),latest=useRef(),hover=useRef(null),lastCopy=useRef(null);
 const queue=useRef(Promise.resolve()),pending=useRef(0);
 const enqueue=job=>{pending.current++;const result=queue.current.then(job).finally(()=>pending.current--);queue.current=result.catch(()=>{});return result;};
 latest.current={context,onPaste,onEdgeTemplate,onLocate,note,category};
 const accept=value=>{if(value.version>=current.current.version){current.current=value;setLibrary(value);}return value;};
 useEffect(()=>{api('editor.library').then(accept).catch(note);},[]);
 const update=p=>api('editor.library.update',p).then(accept);
 const record=entries=>{if(entries.length)update({action:'history.push',entries}).catch(latest.current.note);};
 const patch=async(changes,recordUndo=true)=>{
  const before=clone(current.current.bookmarks),result=await update({action:'bookmark.patch',changes});
  if(recordUndo){undo.current.push({booksBefore:before,booksAfter:clone(result.bookmarks)});redo.current=[];}
  return result;
 };
 const remove=async id=>{const book=current.current.bookmarks.find(b=>b.id===id);if(book)await patch([{id,expected:book,value:null}]);lastCopy.current=null;};
 const copy=async(mode,frame)=>{
  const {area,ctx,category}=frame;let snapshot,signature;
  if(area?.kind==='bookmark'){await remove(area.id);return;}
  if(area?.kind==='history'){
   const e=area.entry;signature='history:'+e.kind+':'+e.id;
   if(e.kind==='edge')snapshot={nodes:[],edges:[{metadata:clone(e.metadata),...(mode==='external'?{target:e.target}:{})}],files:{},positions:{}};
   else if(e.kind==='bookmark'){
    const old=current.current.bookmarks.find(b=>b.id===e.id)?.snapshot??e.snapshot;if(!old)throw Error('该书签已不存在');
    if(!old.nodes.length)snapshot={...clone(old),edges:old.edges.map(edge=>({metadata:clone(edge.metadata),...(mode==='external'&&edge.target?{target:edge.target}:{})}))};
    else snapshot=copySubnet({network:{nodes:old.nodes},files:old.files},old.nodes.map(n=>n.node_id),mode,old.positions);
   }else{
    const exists=ctx.document.network.nodes.some(n=>n.node_id===e.id);
    snapshot=exists?copySubnet(ctx.document,[e.id],mode,ctx.layout):copySubnet({network:{nodes:e.snapshot.nodes},files:e.snapshot.files},e.snapshot.nodes.map(n=>n.node_id),mode,e.snapshot.positions);
   }
  }else{
   signature=selectionKey(ctx.selection);snapshot=copySubnet(ctx.document,ctx.selection.nodes,mode,ctx.layout,ctx.selection.edges);
  }
  signature=category+':'+signature;
  if(lastCopy.current?.signature===signature&&lastCopy.current.mode===mode&&current.current.bookmarks.some(b=>b.id===lastCopy.current.id)){await remove(lastCopy.current.id);return;}
  const book={id:crypto.randomUUID(),name:snapshot.nodes.length===1?snapshot.nodes[0].name:snapshot.nodes.length?snapshot.nodes.length+' 节点子网':'连接书签',mode,category,createdAt:Date.now(),snapshot};
  await patch([{id:book.id,expected:null,value:book}]);lastCopy.current={id:book.id,signature,mode};setFocus(book.id);setOpen(true);
 };
 const created=(before,after)=>{
  lastCopy.current=null;const entries=[],oldIds=new Set(before.network.nodes.map(n=>n.node_id));
  for(const n of after.network.nodes){
   if(!oldIds.has(n.node_id))entries.push({kind:'node',id:n.node_id,label:n.name,snapshot:copySubnet(after,[n.node_id],'external',{})});
   const previous=before.network.nodes.find(o=>o.node_id===n.node_id)?.connections.interfaces.length??0;
   n.connections.interfaces.slice(previous).forEach((link,i)=>entries.push({kind:'edge',id:n.node_id+'|'+(previous+i),label:n.name+' → '+(after.network.nodes.find(t=>t.node_id===link.target_node_id)?.name??link.target_node_id),source:n.node_id,target:link.target_node_id,metadata:clone(link.metadata)}));
  }
  record(entries);
 };
 const usedBook=book=>record([{kind:'bookmark',id:book.id,label:book.name,mode:book.mode,snapshot:clone(book.snapshot)}]);
 const historyEntry=ref=>current.current.history.find(e=>e.kind===ref.kind&&e.id===ref.id);
 const usedHistory=ref=>{const entry=historyEntry(ref);if(entry)record([entry]);};
 const place=(book,point,usage)=>{
  const ctx=latest.current.context(),result=pasteSubnet(ctx.document,book,ctx.flow.screenToFlowPosition(point),ctx.catalog,ctx.layout);
  const used=()=>usage.usedBookmark?usedBook(book):usedHistory(usage.usedHistory);
  if(result.edges){
   const source=document.elementFromPoint(point.x,point.y)?.closest('.react-flow__node')?.dataset.id??'';
   const missing=result.edges.some(e=>!ctx.document.network.nodes.some(n=>n.node_id===e.target));
   if(source&&!missing){const next=clone(ctx.document),n=next.network.nodes.find(n=>n.node_id===source);for(const e of result.edges)n.connections.interfaces.push({target_node_id:e.target,metadata:clone(e.metadata)});latest.current.onPaste({document:next,layout:ctx.layout,nodes:[source]});used();}
   else{const templates=result.edges.map(e=>({source,target:ctx.document.network.nodes.some(n=>n.node_id===e.target)?e.target:'',...e.metadata,...usage}));latest.current.onEdgeTemplate({...templates[0],queue:templates.slice(1)});}
  }else{latest.current.onPaste(result);used();}
 };
 const drop=(id,point)=>{const book=current.current.bookmarks.find(b=>b.id===id);if(!book)throw Error('书签已不存在');place(book,point,{usedBookmark:id});};
 const dropHistory=(ref,point)=>{const entry=historyEntry(ref);if(!entry)throw Error('该历史条目已移除');const ctx=latest.current.context();place(historyBookmark(entry,current.current.bookmarks,ctx.document,ctx.layout),point,{usedHistory:ref});};
 const locate=entry=>{
  if(entry.kind==='bookmark'){const book=current.current.bookmarks.find(b=>b.id===entry.id);if(!book){note('该书签已移除');return;}setCategory(book.category??'default');setFocus(book.id);return;}
  latest.current.onLocate(entry);
 };
 return {library,category,setCategory,focus,open,setOpen,hover,pending,afterPending:enqueue,
  copy:mode=>{const ctx=latest.current.context(),frame={area:hover.current?clone(hover.current):null,category:latest.current.category,ctx:{...ctx,document:clone(ctx.document),selection:clone(ctx.selection),layout:clone(ctx.layout)}};return enqueue(()=>copy(mode,frame));},
  remove:id=>enqueue(()=>remove(id)),created,drop,dropHistory,locate,record,usedHistory,
  bindings:shortcuts(library.settings.shortcuts),resetCopy:()=>{lastCopy.current=null;},
  async restore(frame,back){await patch(bookmarkChanges(back?frame.booksAfter:frame.booksBefore,back?frame.booksBefore:frame.booksAfter),false);lastCopy.current=null;},
  async rename(book){const name=(await textPrompt('书签名称',book.name))?.trim();if(!name||name===book.name)return;await patch([{id:book.id,expected:book,value:{...book,name}}]);},
  async newCategory(){const name=(await textPrompt('新分类名称'))?.trim();if(!name)return;const item={id:crypto.randomUUID(),name};await update({action:'category.add',category:item});setCategory(item.id);},
  saveSettings:value=>enqueue(()=>update({action:'settings.save',settings:{...current.current.settings,shortcuts:value}})),
  saveView:value=>enqueue(()=>update({action:'settings.save',settings:{...current.current.settings,bookmarkView:value}})),
  togglePanel:side=>enqueue(()=>{const panels={...current.current.settings.panels};panels[side]=!panels[side];return update({action:'settings.save',settings:{...current.current.settings,panels}});}),
  usedBookmark:id=>{const book=current.current.bookmarks.find(b=>b.id===id);if(book)usedBook(book);},
 };
}
