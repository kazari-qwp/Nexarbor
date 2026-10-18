import React,{useState} from 'react';
import {X,ChevronDown,Settings2} from 'lucide-react';
import {defaultShortcuts,shortcuts,keyName} from './shortcuts.js';
const modifiers=[['None','无'],['Shift','Shift'],['Control','Ctrl'],['Alt','Alt'],['Meta','Meta']];
export function ClientMenu({onShortcuts,onArchive}){
 const [open,setOpen]=useState(false);
 return <div className="client-menu" onMouseEnter={()=>setOpen(true)} onMouseLeave={()=>setOpen(false)} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false);}} onKeyDown={e=>{if(e.key==='Escape')setOpen(false);if(e.key==='ArrowDown')setOpen(true);}}>
  <button aria-haspopup="menu" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><Settings2 size={15}/>设置<ChevronDown size={12}/></button>
  {open&&<div role="menu" aria-label="设置菜单"><button role="menuitem" onClick={()=>{setOpen(false);onShortcuts();}}>自定义快捷键</button><button role="menuitem" onClick={()=>{setOpen(false);onArchive();}}>资源归档</button></div>}
 </div>;
}
export function ClientSettings({value,onSave,onClose}){
 const [draft,setDraft]=useState(()=>shortcuts(value)),[error,setError]=useState('');
 const update=(key,value)=>setDraft(d=>({...d,[key]:value}));
 const keyboard=[['copyInternal','内部复制／A 模式'],['copyExternal','保留外联／B 模式'],['deleteBookmark','删除悬停书签（留空跟随复制键）'],['savePreset','保存悬停网络书签至预设'],['save','保存草稿'],['remove','删除画布选中元素'],['undo','撤销'],['redo','重做'],['assetCut','资源目录：剪切'],['assetPaste','资源目录：粘贴'],['assetRename','资源目录：重命名'],['assetNewFolder','资源目录：新建文件夹'],['assetSelectAll','资源目录：全选当前目录'],['assetRemove','资源目录：删除文件夹／归档资源']];
 return <div className="modal-backdrop client-settings"><section className="modal" role="dialog" aria-modal="true" aria-label="客户端设置"><div className="modal-header"><h2>客户端设置 · 快捷操作</h2><button aria-label="关闭客户端设置" onClick={onClose}><X size={18}/></button></div>
 <p className="muted">点击按键框后按下新组合键。输入框和源码编辑器保留文本编辑快捷键。</p>
 {keyboard.map(([key,label])=><label key={key}>{label}<input aria-label={label} readOnly value={draft[key]} placeholder="未单独指定" onKeyDown={e=>{e.preventDefault();e.stopPropagation();if(e.key==='Backspace'&&key==='deleteBookmark')update(key,'');else{const name=keyName(e);if(name)update(key,name);}}}/></label>)}
 {[['multiSelect','累加点选修饰键'],['selectionWheel','滚轮扩缩选区修饰键']].map(([key,label])=><label key={key}>{label}<select aria-label={label} value={draft[key]} onChange={e=>update(key,e.target.value)}>{modifiers.filter(([id])=>id!=='None').map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>)}
 {[['linkDrag','拖动建立连接'],['renameBookmark','书签重命名']].map(([key,label])=><div className="settings-pointer" key={key}><strong>{label}</strong><select aria-label={label+'鼠标键'} value={draft[key].button} onChange={e=>update(key,{...draft[key],button:Number(e.target.value)})}>{[[0,'左键'],[1,'中键'],[2,'右键']].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select><select aria-label={label+'修饰键'} value={draft[key].modifier} onChange={e=>update(key,{...draft[key],modifier:e.target.value})}>{modifiers.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></div>)}
 {error&&<p className="notice" role="alert">{error}</p>}<div className="modal-actions"><button onClick={()=>setDraft(shortcuts(defaultShortcuts))}>恢复默认</button><button className="primary" onClick={async()=>{try{for(const resourceScope of [false,true]){const values=keyboard.filter(([key])=>key.startsWith('asset')===resourceScope).map(([key])=>draft[key]).filter(Boolean);if(new Set(values).size!==values.length)throw Error('同一操作区域的键盘快捷键不能重复');}if(!draft.copyInternal||!draft.copyExternal)throw Error('两种复制方式都需要快捷键');if(draft.linkDrag.button===0&&draft.linkDrag.modifier==='None')throw Error('左键拖线需要修饰键，避免覆盖普通节点拖动');await onSave(draft);onClose();}catch(e){setError(e.message);}}}>保存设置</button></div>
 </section></div>;
}
