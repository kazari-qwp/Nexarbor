import React,{useEffect,useRef,useState} from 'react';
import {Bookmark,History,Plus,LayoutGrid,List,Save,Trash2} from 'lucide-react';
import {pointerMatches} from './shortcuts.js';
import {historyBookmark} from './subnets.js';
import {isAsset,matchesType,resourceTitle,resourceAvailable} from './resources.js';
import './bookmark-dock.css';

export const bookmarkType=book=>isAsset(book)?book.asset.kind:book.snapshot.nodes.length===0?'edge':book.snapshot.nodes.length===1?'node':book.mode;
const filters=[['all','全部类型'],['node','单节点'],['edge','单边'],['network','网络'],['tool','工具'],['module','模块']];
function AssetPreview({book,catalog}){
 const [failed,setFailed]=useState(false),preview=book.asset.kind==='module'?catalog?.modules?.[book.asset.id]?.preview:null;
 useEffect(()=>setFailed(false),[preview]);
 return preview&&!failed?<img className="resource-preview" src={preview} alt={book.name} draggable={false} onError={()=>setFailed(true)}/>:<span className="resource-name">{book.name}</span>;
}
function Thumbnail({book}){
 const nodes=book.snapshot.nodes;
 if(!nodes.length)return <svg viewBox="0 0 60 40" aria-hidden="true"><path d="M 10 20 H 50"/></svg>;
 if(nodes.length===1)return <svg viewBox="0 0 60 40" aria-hidden="true"><circle className="single-node" cx="30" cy="20" r="6"/></svg>;
 const positions=nodes.map((n,i)=>book.snapshot.positions?.[n.node_id]??{x:i%4*100,y:Math.floor(i/4)*100});
 const xs=positions.map(p=>p.x),ys=positions.map(p=>p.y),minX=Math.min(...xs),minY=Math.min(...ys),width=Math.max(...xs)-minX,height=Math.max(...ys)-minY,scale=Math.min(70/Math.max(width,1),32/Math.max(height,1));
 const point=i=>({x:(positions[i].x-minX-width/2)*scale+45,y:(positions[i].y-minY-height/2)*scale+26});
 return <svg viewBox="0 0 90 52" aria-hidden="true">{nodes.flatMap((n,i)=>n.connections.interfaces.flatMap((l,j)=>{const index=nodes.findIndex(n=>n.node_id===l.target_node_id);if(index<0)return [];const a=point(i),b=point(index);return <path key={i+'-'+j} d={`M ${a.x} ${a.y} H ${(a.x+b.x)/2} V ${b.y} H ${b.x}`}/>;}))}{nodes.map((n,i)=><circle key={n.node_id} cx={point(i).x} cy={point(i).y} r="3.5"/>)}</svg>;
}
function historyPreview(entry,books){
 try{return historyBookmark(entry,books);}catch{return {mode:'external',snapshot:{nodes:entry.kind==='node'?[{node_id:entry.id}]:[]}};}
}
export function BookmarkDock({library,catalog,category,onCategory,onNewCategory,onHover,onLocate,onRename,onRenameHistory,onOpenBook,onSavePreset,onRemove,bindings,focus,view='thumbnail',onView}){
 const [type,setType]=useState('all'),[historyType,setHistoryType]=useState('all'),[page,setPage]=useState(0),[capacity,setCapacity]=useState(6),[menu,setMenu]=useState(null);
 const menuRef=useRef();
 useEffect(()=>{if(!menu)return;const close=e=>{if(!menuRef.current?.contains(e.target))setMenu(null);};const escape=e=>{if(e.key==='Escape')setMenu(null);};window.addEventListener('pointerdown',close,true);window.addEventListener('keydown',escape,true);return()=>{window.removeEventListener('pointerdown',close,true);window.removeEventListener('keydown',escape,true);};},[menu]);
 const items=useRef(),compact=view==='thumbnail',pageSize=compact?capacity:6;
 const available=b=>!isAsset(b)||resourceAvailable(catalog,library.assets,b.asset.kind,b.asset.id);
 const books=library.bookmarks.filter(b=>(b.category??'default')===category&&matchesType(b,type)&&available(b)),pages=Math.max(1,Math.ceil(books.length/pageSize)),current=Math.min(page,pages-1);
 useEffect(()=>{const element=items.current;const observer=new ResizeObserver(()=>{const cols=Math.max(1,Math.floor((element.clientWidth-14+6)/54)),rows=Math.max(1,Math.floor((element.clientHeight-14+6)/46));setCapacity(cols*rows);});observer.observe(element);return()=>observer.disconnect();},[]);
 useEffect(()=>{setPage(0);},[category,type,view]);
 useEffect(()=>{if(!focus)return;setType('all');const all=library.bookmarks.filter(b=>(b.category??'default')===category);setPage(Math.max(0,Math.floor(all.findIndex(b=>b.id===focus)/pageSize)));},[focus,category,pageSize]);
 return <div className={'bookmark-dock '+view+'-view'} onPointerLeave={()=>onHover(null)}>
  <section aria-label="书签区"><header><Bookmark size={14}/><strong>书签区</strong><select aria-label="书签分类" value={category} onChange={e=>onCategory(e.target.value)}>{library.categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select><button aria-label="新增书签分类" title="新增分类" onClick={onNewCategory}><Plus size={12}/></button><select aria-label="书签类型" value={type} onChange={e=>setType(e.target.value)}>{[...filters,['internal','A 内部复制'],['external','B 保留外联']].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select><button className="dock-view-toggle" aria-label={compact?'切换为文字视图':'切换为缩略图视图'} title={compact?'切换为文字视图':'切换为缩略图视图'} onClick={()=>onView(compact?'text':'thumbnail')}>{compact?<List size={14}/>:<LayoutGrid size={14}/>}</button></header><div className="bookmark-items" ref={items}>
   {!books.length&&<p>选中元素按 {bindings.copyInternal} / {bindings.copyExternal} 保存。拖入画布使用；悬停按 {bindings.deleteBookmark||bindings.copyInternal+' / '+bindings.copyExternal} 删除。</p>}
   {books.slice(current*pageSize,current*pageSize+pageSize).map(book=><button draggable key={book.id} className={'bookmark-card '+(isAsset(book)?'asset-card '+book.asset.kind:book.mode)+(focus===book.id?' focused':'')} data-bookmark-id={book.id} aria-label={'书签 '+book.name} title={isAsset(book)?resourceTitle(book):book.name} onClick={()=>onOpenBook?.(book)}
    onContextMenu={e=>{e.preventDefault();e.stopPropagation();if(pointerMatches(e,bindings.renameBookmark))return;setMenu({book,x:Math.min(e.clientX,window.innerWidth-220),y:Math.min(e.clientY,window.innerHeight-100)});}} onPointerEnter={e=>onHover({kind:'bookmark',id:book.id,point:{x:e.clientX,y:e.clientY}})} onPointerMove={e=>onHover({kind:'bookmark',id:book.id,point:{x:e.clientX,y:e.clientY}})} onMouseDown={e=>{if(pointerMatches(e,bindings.renameBookmark)){e.preventDefault();onRename(book);}}} onAuxClick={e=>e.preventDefault()}
    onDragStart={e=>{e.dataTransfer.setData('application/x-nexarbor-bookmark',book.id);e.dataTransfer.effectAllowed='copy';}}>
    {isAsset(book)?<AssetPreview book={book} catalog={catalog}/>:<><Thumbnail book={book}/>{!compact&&<span><b>{book.mode==='internal'?'A':'B'}</b> · {book.snapshot.nodes.length?book.snapshot.nodes.length+' 点':book.snapshot.edges.length+' 边'}</span>}</>}</button>)}
  </div><footer><span>{books.length} 项 · {current+1}/{pages}</span>{pages>1&&<><button aria-label="上一页书签" disabled={!current} onClick={()=>setPage(current-1)}>上一页</button><button aria-label="下一页书签" disabled={current>=pages-1} onClick={()=>setPage(current+1)}>下一页</button></>}</footer></section>
  <section aria-label="历史区" onPointerLeave={()=>onHover(null)}><header><History size={14}/><strong>历史区</strong><span title="复制键可复用；拖入画布使用">最近 100 项</span><select aria-label="历史类型" value={historyType} onChange={e=>setHistoryType(e.target.value)}>{filters.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></header><div className="bookmark-history">
   {!library.history.length&&<p>创建或使用节点、边、书签时记录。</p>}
   {library.history.map(entry=>({entry,book:historyPreview(entry,library.bookmarks)})).filter(({book})=>matchesType(book,historyType)&&available(book)).map(({entry,book})=><button className={'history-card '+(isAsset(book)?'asset-card '+book.asset.kind:book.mode)} draggable key={entry.kind+entry.id} data-history-kind={entry.kind} data-history-id={entry.id} aria-label={'历史 '+entry.label} title={isAsset(book)?resourceTitle(book):entry.label} onPointerEnter={()=>onHover({kind:'history',entry})} onClick={()=>onLocate(entry)} onMouseDown={e=>{if(pointerMatches(e,bindings.renameBookmark)){e.preventDefault();onRenameHistory?.(entry);}}} onAuxClick={e=>e.preventDefault()} onDragStart={e=>{e.dataTransfer.setData('application/x-nexarbor-history',JSON.stringify({kind:entry.kind,id:entry.id}));e.dataTransfer.effectAllowed='copy';}}>{isAsset(book)?<AssetPreview book={book} catalog={catalog}/>:compact?<Thumbnail book={book}/>:<><i>{entry.kind==='node'?'点':entry.kind==='edge'?'边':'签'}</i><span>{entry.kind==='bookmark'?'子网书签':entry.label}</span></>}</button>)}
  </div></section>
  {menu&&<div className="resource-context-menu" ref={menuRef} role="menu" aria-label="书签操作" style={{left:menu.x,top:menu.y}}><button role="menuitem" aria-label="保存书签至网络预设" disabled={isAsset(menu.book)||menu.book.snapshot?.nodes.length<2} title="网络书签保存至当前浏览的预设目录" onClick={()=>{onSavePreset(menu.book.id);setMenu(null);}}><Save size={13}/><span>保存</span><small>{bindings.savePreset}</small></button><button role="menuitem" aria-label="删除书签" onClick={()=>{onRemove(menu.book.id);setMenu(null);}}><Trash2 size={13}/><span>删除</span></button></div>}
 </div>;
}
