import React,{useEffect,useState} from 'react';
import {Bookmark,History,Plus} from 'lucide-react';
import {pointerMatches,pointerLabel} from './shortcuts.js';
export const bookmarkType=book=>book.snapshot.nodes.length===0?'edge':book.snapshot.nodes.length===1?'node':book.mode;
function Thumbnail({book}){
 const nodes=book.snapshot.nodes;if(!nodes.length)return <svg viewBox="0 0 90 36"><path d="M 8 18 H 80 M 74 12 L 80 18 L 74 24"/></svg>;
 const positions=nodes.map((n,i)=>book.snapshot.positions?.[n.node_id]??{x:i%4*100,y:Math.floor(i/4)*100}),xs=positions.map(p=>p.x),ys=positions.map(p=>p.y),minX=Math.min(...xs),minY=Math.min(...ys),width=Math.max(...xs)-minX,height=Math.max(...ys)-minY;
 const point=i=>({x:width?(positions[i].x-minX)/width*70+10:45,y:height?(positions[i].y-minY)/height*22+7:18});
 return <svg viewBox="0 0 90 36">{nodes.flatMap((n,i)=>n.connections.interfaces.flatMap((l,j)=>{const index=nodes.findIndex(n=>n.node_id===l.target_node_id);if(index<0)return [];const a=point(i),b=point(index);return <path key={i+'-'+j} d={`M ${a.x} ${a.y} H ${(a.x+b.x)/2} V ${b.y} H ${b.x}`}/>;}))}{nodes.map((n,i)=><circle key={n.node_id} cx={point(i).x} cy={point(i).y} r="3"/>)}</svg>;
}
export function BookmarkDock({library,category,onCategory,onNewCategory,onHover,onLocate,onRename,bindings,focus}){
 const [frozenHistory,setFrozenHistory]=useState(null),[type,setType]=useState('all'),[page,setPage]=useState(0);
 const books=library.bookmarks.filter(b=>(b.category??'default')===category&&(type==='all'||bookmarkType(b)===type)),pages=Math.max(1,Math.ceil(books.length/6)),current=Math.min(page,pages-1);
 useEffect(()=>{setPage(0);},[category,type]);
 useEffect(()=>{if(!focus)return;setType('all');const all=library.bookmarks.filter(b=>(b.category??'default')===category);setPage(Math.max(0,Math.floor(all.findIndex(b=>b.id===focus)/6)));},[focus,category]);
 return <div className="bookmark-dock" onPointerLeave={()=>onHover(null)}>
  <section aria-label="书签区"><header><Bookmark size={14}/><strong>书签区</strong><select aria-label="书签分类" value={category} onChange={e=>onCategory(e.target.value)}>{library.categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select><button aria-label="新增书签分类" title="新增分类" onClick={onNewCategory}><Plus size={12}/></button><select aria-label="书签类型" value={type} onChange={e=>setType(e.target.value)}>{[['all','全部类型'],['internal','A 内部子网'],['external','B 保留外联'],['node','单独节点'],['edge','单独边']].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></header><div className="bookmark-items">
   {!books.length&&<p>选中元素按 {bindings.copyInternal} / {bindings.copyExternal} 保存。拖入画布使用；悬停按 {bindings.deleteBookmark||bindings.copyInternal+' / '+bindings.copyExternal} 删除。</p>}
   {books.slice(current*6,current*6+6).map(book=><button draggable key={book.id} className={'bookmark-card '+book.mode+(focus===book.id?' focused':'')} data-bookmark-id={book.id} aria-label={'书签 '+book.name} title={book.name+'\n'+(book.mode==='internal'?'A · 内部副本':'B · 保留外联')+'\n拖动使用；'+(bindings.deleteBookmark||bindings.copyInternal+' / '+bindings.copyExternal)+' 删除；'+pointerLabel(bindings.renameBookmark)+'重命名'}
    onPointerEnter={()=>onHover({kind:'bookmark',id:book.id})} onMouseDown={e=>{if(pointerMatches(e,bindings.renameBookmark)){e.preventDefault();onRename(book);}}} onAuxClick={e=>e.preventDefault()}
    onDragStart={e=>{e.dataTransfer.setData('application/x-nexarbor-bookmark',book.id);e.dataTransfer.effectAllowed='copy';}}>
    <Thumbnail book={book}/><span><b>{book.mode==='internal'?'A':'B'}</b> · {book.snapshot.nodes.length?book.snapshot.nodes.length+' 点':book.snapshot.edges.length+' 边'}</span></button>)}
  </div><footer><span>{books.length} 项 · {current+1}/{pages}</span>{pages>1&&<><button aria-label="上一页书签" disabled={!current} onClick={()=>setPage(current-1)}>上一页</button><button aria-label="下一页书签" disabled={current>=pages-1} onClick={()=>setPage(current+1)}>下一页</button></>}</footer></section>
  <section aria-label="历史区" onPointerEnter={()=>setFrozenHistory(library.history)} onPointerLeave={()=>{setFrozenHistory(null);onHover(null);}}><header><History size={14}/><strong>历史区</strong><span>复制键可复用 · 最近 100 项</span></header><div className="bookmark-history">
   {!library.history.length&&<p>创建、拖动节点和连接，或拖入书签时记录；普通点选不改变排序。</p>}
   {(frozenHistory??library.history).map(entry=><button key={entry.kind+entry.id} title={entry.label} onPointerEnter={()=>onHover({kind:'history',entry})} onClick={()=>onLocate(entry)}><i>{entry.kind==='node'?'点':entry.kind==='edge'?'边':'签'}</i><span>{entry.kind==='bookmark'?'子网书签':entry.label}</span></button>)}
  </div></section>
 </div>;
}
