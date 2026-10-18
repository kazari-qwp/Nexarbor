import React,{useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,ArrowUp,ChevronRight,Box,Wrench,Folder,FolderPlus,Pencil,Scissors,ClipboardPaste} from 'lucide-react';
import {resources,resourceTitle} from './resources.js';
import {keyMatches} from './shortcuts.js';
import {textPrompt} from './text-prompt.js';
import './resources.css';

export function ResourceLibrary({catalog,organization={},onAction,onOpen,bindings,note}){
 const [clipboard,setClipboard]=useState(null);
 return <>{['tool','module'].map(kind=><ResourceExplorer key={kind} kind={kind} catalog={catalog} tree={organization[kind]??{folders:[],items:{}}} organization={organization} onAction={onAction} onOpen={onOpen} clipboard={clipboard} onClipboard={setClipboard} bindings={bindings} note={note}/>)}</>;
}
function ResourceExplorer({kind,catalog,tree,organization,onAction,onOpen,clipboard,onClipboard,bindings,note}){
 const label=kind==='tool'?'工具':'模块',Icon=kind==='tool'?Wrench:Box;
 const [selected,setSelected]=useState(null),[navigation,setNavigation]=useState({path:[null],index:0}),[menu,setMenu]=useState(null);const menuRef=useRef();
 const folders=tree.folders,entries=resources(catalog,kind,organization),requested=navigation.path[navigation.index],current=folders.some(f=>f.id===requested)?requested:null;
 const parent=folders.find(f=>f.id===current)?.parent??null,crumbs=[];
 for(let id=current;id!=null;){const folder=folders.find(f=>f.id===id);if(!folder)break;crumbs.unshift(folder);id=folder.parent;}
 const navigate=id=>{setMenu(null);setSelected(null);if(id!==current)setNavigation(old=>({path:[...old.path.slice(0,old.index+1),id],index:old.index+1}));};
 const step=amount=>{setMenu(null);setSelected(null);setNavigation(old=>({...old,index:old.index+amount}));};
 const run=fn=>{setMenu(null);return Promise.resolve().then(fn).catch(note);};
 const newFolder=()=>run(async()=>{const name=(await textPrompt('新建'+label+'文件夹'))?.trim();if(!name)return;const id=crypto.randomUUID();await onAction({action:'asset.folder.create',kind,id,name,parent:current});setSelected({type:'folder',id});});
 const rename=()=>run(async()=>{if(!selected)return;const old=selected.type==='folder'?folders.find(f=>f.id===selected.id)?.name:entries.find(e=>e.asset.id===selected.id)?.name;const name=(await textPrompt('重命名'+label+'资源',old))?.trim();if(name&&name!==old)await onAction({action:'asset.rename',kind,entry:selected,name});});
 const cut=()=>{setMenu(null);if(selected)onClipboard({kind,...selected});};
 const paste=()=>run(async()=>{if(!clipboard||clipboard.kind!==kind)return;await onAction({action:'asset.move',kind,entry:{type:clipboard.type,id:clipboard.id},target:current});setSelected({type:clipboard.type,id:clipboard.id});onClipboard(null);});
 const choose=(entry,context=false)=>{setSelected(entry);if(!context)setMenu(null);};
 const context=(event,entry=null)=>{event.preventDefault();event.stopPropagation();choose(entry,true);setMenu({x:Math.max(4,Math.min(event.clientX,window.innerWidth-200)),y:Math.max(4,Math.min(event.clientY,window.innerHeight-190))});};
 const entryClass=entry=>(selected?.type===entry.type&&selected.id===entry.id?'selected ':'')+(clipboard?.kind===kind&&clipboard.type===entry.type&&clipboard.id===entry.id?'cut':'');
 useEffect(()=>{if(!menu)return;const close=e=>{if(!menuRef.current?.contains(e.target))setMenu(null);};window.addEventListener('pointerdown',close,true);return()=>window.removeEventListener('pointerdown',close,true);},[menu]);
 return <details className="resource-library" data-resource-library={kind} onKeyDown={e=>{if(e.target.closest('input,textarea,[contenteditable=true]'))return;if(e.key==='Escape'){setMenu(null);return;}if(e.altKey&&e.key==='ArrowUp'&&current!=null){e.preventDefault();navigate(parent);return;}for(const [binding,action] of [[bindings.assetNewFolder,newFolder],[bindings.assetRename,rename],[bindings.assetCut,cut],[bindings.assetPaste,paste]])if(keyMatches(e,binding)){e.preventDefault();e.stopPropagation();action();return;}}}>
  <summary><Icon size={14}/><strong>{label}栏</strong></summary><div className="resource-explorer" aria-label={label+'目录'}>
   <div className="resource-navigation"><div className="resource-navigation-buttons"><button aria-label={label+'返回'} title="返回" disabled={!navigation.index} onClick={()=>step(-1)}><ArrowLeft size={13}/></button><button aria-label={label+'前进'} title="前进" disabled={navigation.index>=navigation.path.length-1} onClick={()=>step(1)}><ArrowRight size={13}/></button><button aria-label={label+'上一级'} title="上一级 · Alt+↑" disabled={current==null} onClick={()=>navigate(parent)}><ArrowUp size={13}/></button></div>
    <nav className="resource-breadcrumbs" aria-label={label+'路径'}><button aria-label={'全部'+label} onClick={()=>navigate(null)}><Icon size={12}/>{label}</button>{crumbs.map(folder=><React.Fragment key={folder.id}><ChevronRight size={10}/><button aria-label={label+'路径 '+folder.name} title={folder.name} onClick={()=>navigate(folder.id)}>{folder.name}</button></React.Fragment>)}</nav>
   </div>
   <div className="resource-items" tabIndex={0} aria-label={label+'目录内容'} onContextMenu={e=>context(e)} onClick={e=>{if(e.target===e.currentTarget){setSelected(null);setMenu(null);}}}>
    {folders.filter(f=>f.parent===current).sort((a,b)=>a.name.localeCompare(b.name)).map(folder=><button key={folder.id} className={'resource-folder '+entryClass({type:'folder',id:folder.id})} data-resource-folder={folder.id} aria-label={label+'文件夹 '+folder.name} title={folder.name} onClick={()=>choose({type:'folder',id:folder.id})} onDoubleClick={()=>navigate(folder.id)} onContextMenu={e=>context(e,{type:'folder',id:folder.id})}><Folder size={14}/><span>{folder.name}</span></button>)}
    {entries.filter(e=>(tree.items[e.asset.id]?.folder??null)===current).sort((a,b)=>a.name.localeCompare(b.name)).map(entry=><button className={'resource-item '+entryClass({type:'item',id:entry.asset.id})} draggable key={entry.asset.id} data-resource-kind={kind} data-resource-id={entry.asset.id} title={resourceTitle(entry)} aria-label={label+'资源 '+entry.name} onClick={()=>{choose({type:'item',id:entry.asset.id});onOpen(entry);}} onContextMenu={e=>context(e,{type:'item',id:entry.asset.id})} onDragStart={e=>{setMenu(null);e.dataTransfer.setData('application/x-nexarbor-resource',JSON.stringify({kind,id:entry.asset.id}));e.dataTransfer.effectAllowed='copy';}}><Icon size={13}/><span>{entry.name}</span></button>)}
   </div>
  </div>{menu&&<div ref={menuRef} className="resource-context-menu" role="menu" aria-label={label+'目录操作'} style={{left:menu.x,top:menu.y}} onContextMenu={e=>{e.preventDefault();e.stopPropagation();}}>{[[FolderPlus,'新建文件夹',bindings.assetNewFolder,newFolder,false],[Pencil,'重命名',bindings.assetRename,rename,!selected],[Scissors,'剪切',bindings.assetCut,cut,!selected],[ClipboardPaste,'粘贴',bindings.assetPaste,paste,!clipboard||clipboard.kind!==kind]].map(([Action,name,key,fn,disabled])=><button role="menuitem" key={name} aria-label={label+name} disabled={disabled} onClick={fn}><Action size={13}/><span>{name}</span><small>{key}</small></button>)}</div>}
 </details>;
}
