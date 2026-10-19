import React,{useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,ArrowUp,ChevronRight,Box,Wrench,Network,Folder,FolderPlus,Pencil,Scissors,ClipboardPaste,Archive,Trash2,Files,Plus,Save} from 'lucide-react';
import {resources,resourceTitle,resourceId,folderResources} from './resources.js';
import {keyMatches} from './shortcuts.js';
import {textPrompt} from './text-prompt.js';
import './resources.css';
import {ResourceBadges} from './resource-badges.jsx';

export function ResourceLibrary({catalog,organization={},onAction,onOpen,onCreateModule,onSaveNetwork,onFolderChange,onLoadTools,onNavigate,focus,bindings,note}){
 const [clipboard,setClipboard]=useState(null);
 return <>{['node','tool','module','preset'].map(kind=><ResourceExplorer key={kind} kind={kind} catalog={catalog} tree={organization[kind]??{folders:[],items:{}}} organization={organization} onAction={onAction} onOpen={onOpen} onCreateModule={onCreateModule} onSaveNetwork={onSaveNetwork} onFolderChange={onFolderChange} onLoadTools={onLoadTools} onNavigate={onNavigate} focus={focus} clipboard={clipboard} onClipboard={setClipboard} bindings={bindings} note={note}/>)}</>;
}
function ResourceExplorer({kind,catalog,tree,organization,onAction,onOpen,onCreateModule,onSaveNetwork,onFolderChange,onLoadTools,onNavigate,focus,clipboard,onClipboard,bindings,note}){
 const label={node:'节点',tool:'工具',module:'模块',preset:'网络预设'}[kind],Icon=kind==='tool'?Wrench:kind==='preset'?Network:Box;
 const [selected,setSelected]=useState([]),[navigation,setNavigation]=useState({path:[null],index:0}),[menu,setMenu]=useState(null);const menuRef=useRef(),explorerRef=useRef();
 const folders=tree.folders,entries=resources(catalog,kind,organization),allEntries=resources(catalog,kind,organization,true),requested=navigation.path[navigation.index],current=folders.some(f=>f.id===requested)?requested:null;
 const parent=folders.find(f=>f.id===current)?.parent??null,crumbs=[];
 useEffect(()=>onFolderChange?.(kind,current),[kind,current]);
 for(let id=current;id!=null;){const folder=folders.find(f=>f.id===id);if(!folder)break;crumbs.unshift(folder);id=folder.parent;}
 const navigate=id=>{setMenu(null);setSelected([]);if(id!==current)setNavigation(old=>({path:[...old.path.slice(0,old.index+1),id],index:old.index+1}));};
 useEffect(()=>{
  if(focus?.kind!==kind)return;
  const entry=entries.find(e=>resourceId(e)===focus.id);if(!entry)return;
  const folder=tree.items[focus.id]?.folder??null;
  navigate(folders.some(f=>f.id===folder)?folder:null);setSelected([{type:'item',id:focus.id}]);explorerRef.current.open=true;
  const frame=requestAnimationFrame(()=>{const target=[...explorerRef.current.querySelectorAll('[data-resource-id]')].find(e=>e.dataset.resourceId===focus.id);target?.scrollIntoView({block:'nearest',inline:'nearest'});target?.focus({preventScroll:true});});return()=>cancelAnimationFrame(frame);
 },[focus?.serial]);
 const step=amount=>{setMenu(null);setSelected([]);setNavigation(old=>({...old,index:old.index+amount}));};
 const run=fn=>{setMenu(null);return Promise.resolve().then(fn).catch(note);};
 const newFolder=()=>run(async()=>{const name=(await textPrompt('新建'+label+'文件夹'))?.trim();if(!name)return;const id=crypto.randomUUID();await onAction({action:'asset.folder.create',kind,id,name,parent:current});setSelected([{type:'folder',id}]);});
 const rename=()=>run(async()=>{if(selected.length!==1)return;const entry=selected[0],old=entry.type==='folder'?folders.find(f=>f.id===entry.id)?.name:entries.find(e=>resourceId(e)===entry.id)?.name;const name=(await textPrompt('重命名'+label+'资源',old))?.trim();if(name&&name!==old)await onAction({action:'asset.rename',kind,entry,name});});
 const same=(a,b)=>a.type===b.type&&a.id===b.id;
 const cut=()=>{setMenu(null);if(selected.length)onClipboard({kind,entries:selected});};
 const cutContents=()=>{setMenu(null);if(selected.length!==1||selected[0].type!=='folder')return;const entries=folderResources(tree,allEntries,selected[0].id).map(e=>({type:'item',id:resourceId(e)}));if(!entries.length){note('目录及子目录没有资源');return;}onClipboard({kind,entries});note('已剪切 '+entries.length+' 项资源，进入目标文件夹后粘贴');};
 const paste=()=>run(async()=>{if(!clipboard||clipboard.kind!==kind)return;await onAction({action:'asset.move',kind,entries:clipboard.entries,target:current});setSelected(clipboard.entries);onClipboard(null);});
 const archive=selection=>run(async()=>{const entries=selection.filter(e=>e.type==='item');if(!entries.length)return;await onAction({action:'asset.archive',kind,entries});setSelected([]);});
 const removeFolders=()=>run(async()=>{await onAction({action:'asset.folder.delete',kind,ids:selected.filter(e=>e.type==='folder').map(e=>e.id)});setSelected([]);});
 const remove=()=>{if(selected.every(e=>e.type==='folder'))return removeFolders();if(selected.every(e=>e.type==='item'))return archive(selected);note('请分开选择文件夹与资源进行删除或归档');};
 const choose=(entry,event)=>{setMenu(null);setSelected(old=>event?.ctrlKey?(old.some(e=>same(e,entry))?old.filter(e=>!same(e,entry)):[...old,entry]):[entry]);};
 const context=(event,entry=null)=>{event.preventDefault();event.stopPropagation();if(!entry)setSelected([]);else if(!selected.some(e=>same(e,entry)))setSelected([entry]);setMenu({x:Math.max(4,Math.min(event.clientX,window.innerWidth-240)),y:Math.max(4,Math.min(event.clientY,window.innerHeight-300))});};
 const entryClass=entry=>(selected.some(e=>same(e,entry))?'selected ':'')+(clipboard?.kind===kind&&clipboard.entries.some(e=>same(e,entry))?'cut':'');
 const visibleFolders=folders.filter(f=>f.parent===current).sort((a,b)=>a.name.localeCompare(b.name)),visibleEntries=entries.filter(e=>(tree.items[resourceId(e)]?.folder??null)===current).sort((a,b)=>a.name.localeCompare(b.name));
 const selectAll=()=>setSelected([...visibleFolders.map(f=>({type:'folder',id:f.id})),...visibleEntries.map(e=>({type:'item',id:resourceId(e)}))]);
 const drag=(event,entry)=>{setMenu(null);const selection=selected.some(e=>same(e,entry))?selected:[entry],ids=[...new Set(selection.flatMap(e=>e.type==='item'?[e.id]:folderResources(tree,entries,e.id).map(r=>resourceId(r))))];if(!ids.length){event.preventDefault();return;}event.dataTransfer.setData('application/x-nexarbor-resource',JSON.stringify({kind,ids}));event.dataTransfer.effectAllowed='copy';};
 useEffect(()=>{if(!menu)return;const close=e=>{if(!menuRef.current?.contains(e.target))setMenu(null);};window.addEventListener('pointerdown',close,true);return()=>window.removeEventListener('pointerdown',close,true);},[menu]);
 return <details ref={explorerRef} className="resource-library" data-resource-library={kind} onToggle={event=>{if(event.target===event.currentTarget&&event.currentTarget.open&&kind==='tool')onLoadTools?.();}} onKeyDown={e=>{if(e.target.closest('input,textarea,[contenteditable=true]'))return;if(e.key==='Escape'){setMenu(null);return;}if(e.altKey&&e.key==='ArrowUp'&&current!=null){e.preventDefault();navigate(parent);return;}for(const [binding,action] of [[bindings.assetNewFolder,newFolder],[bindings.assetRename,rename],[bindings.assetCut,cut],[bindings.assetPaste,paste],[bindings.assetSelectAll,selectAll],[bindings.assetRemove,remove]])if(keyMatches(e,binding)){e.preventDefault();e.stopPropagation();action();return;}}}>
  <summary><Icon size={14}/><strong>{label}栏</strong></summary><div className="resource-explorer" aria-label={label+'目录'}>
   <div className="resource-navigation"><div className="resource-navigation-buttons"><button aria-label={label+'返回'} title="返回" disabled={!navigation.index} onClick={()=>step(-1)}><ArrowLeft size={13}/></button><button aria-label={label+'前进'} title="前进" disabled={navigation.index>=navigation.path.length-1} onClick={()=>step(1)}><ArrowRight size={13}/></button><button aria-label={label+'上一级'} title="上一级 · Alt+↑" disabled={current==null} onClick={()=>navigate(parent)}><ArrowUp size={13}/></button></div>
    <nav className="resource-breadcrumbs" aria-label={label+'路径'}><button aria-label={'全部'+label} onClick={()=>navigate(null)}><Icon size={12}/>{label}</button>{crumbs.map(folder=><React.Fragment key={folder.id}><ChevronRight size={10}/><button aria-label={label+'路径 '+folder.name} title={folder.name} onClick={()=>navigate(folder.id)}>{folder.name}</button></React.Fragment>)}</nav>
   </div>
   <div className="resource-items" tabIndex={0} aria-label={label+'目录内容'} onContextMenu={e=>context(e)} onClick={e=>{if(e.target===e.currentTarget){setSelected([]);setMenu(null);}}}>
    {['module','tool','preset'].includes(kind)&&<button className="resource-create" aria-label={kind==='module'?'制作新模块':kind==='tool'?'制作新工具':'制作网络预设'} onClick={()=>onCreateModule(current,kind)}><Plus size={13}/>{kind==='module'?'制作新模块':kind==='tool'?'制作新工具':'制作网络预设'}</button>}
    {kind==='preset'&&<><button className="resource-create" aria-label="保存全网" onClick={()=>onSaveNetwork().catch(note)}><Save size={13}/>保存全网</button>{catalog.presetErrors?.map(error=><p className="notice" key={error}>{error}</p>)}</>}
    {kind==='tool'&&!catalog.toolsReady&&<p className="muted" role="status">{catalog.toolError||'正在读取官方工具目录…'}{catalog.toolError&&<button onClick={onLoadTools}>重试</button>}</p>}
    {kind==='node'&&catalog.nodeErrors?.map(error=><p className="notice" key={error}>{error}</p>)}
    {visibleFolders.map(folder=><button key={folder.id} className={'resource-folder '+entryClass({type:'folder',id:folder.id})} aria-pressed={selected.some(e=>e.type==='folder'&&e.id===folder.id)} draggable data-resource-folder={folder.id} aria-label={label+'文件夹 '+folder.name} title={folder.name} onClick={e=>choose({type:'folder',id:folder.id},e)} onDoubleClick={()=>navigate(folder.id)} onContextMenu={e=>context(e,{type:'folder',id:folder.id})} onDragStart={e=>drag(e,{type:'folder',id:folder.id})}><Folder size={14}/><span>{folder.name}</span></button>)}
    {visibleEntries.map(entry=><div className="resource-row" key={resourceId(entry)}><button className={'resource-item '+entryClass({type:'item',id:resourceId(entry)})} aria-pressed={selected.some(e=>e.type==='item'&&e.id===resourceId(entry))} draggable data-resource-kind={kind} data-resource-id={resourceId(entry)} title={resourceTitle(entry)} aria-label={label+'资源 '+entry.name} onClick={e=>{choose({type:'item',id:resourceId(entry)},e);if(!e.ctrlKey)onOpen(entry);}} onContextMenu={e=>context(e,{type:'item',id:resourceId(entry)})} onDragStart={e=>drag(e,{type:'item',id:resourceId(entry)})}><Icon size={13}/><span>{entry.name}</span></button>{['module','tool'].includes(kind)&&<ResourceBadges value={entry} catalog={catalog} onNavigate={onNavigate}/>}<button className="archive-resource" aria-label={'归档'+label+' '+entry.name} title="归档" onClick={()=>archive([{type:'item',id:resourceId(entry)}])}><Archive size={12}/></button></div>)}
   </div>
  </div>{menu&&<div ref={menuRef} className="resource-context-menu" role="menu" aria-label={label+'目录操作'} style={{left:menu.x,top:menu.y}} onContextMenu={e=>{e.preventDefault();e.stopPropagation();}}>{[[FolderPlus,'新建文件夹',bindings.assetNewFolder,newFolder,false],[Pencil,'重命名',bindings.assetRename,rename,selected.length!==1],[Scissors,'剪切',bindings.assetCut,cut,!selected.length],[Files,'剪切目录内全部资源','',cutContents,selected.length!==1||selected[0]?.type!=='folder'],[ClipboardPaste,'粘贴',bindings.assetPaste,paste,!clipboard||clipboard.kind!==kind],[Archive,'归档资源','',()=>archive(selected),!selected.some(e=>e.type==='item')],[Trash2,'删除文件夹',bindings.assetRemove,removeFolders,!selected.length||selected.some(e=>e.type!=='folder')]].map(([Action,name,key,fn,disabled])=><button role="menuitem" key={name} aria-label={label+name} disabled={disabled} onClick={fn}><Action size={13}/><span>{name}</span><small>{key}</small></button>)}</div>}
 </details>;
}
