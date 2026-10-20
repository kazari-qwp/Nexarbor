import React from 'react';
import {Bookmark,MessageSquare,Trash2,FileText,FolderOpen} from 'lucide-react';
import {ContextMenu} from './context-menu.jsx';
export function CanvasMenu({value,onClose,onConsult,onDelete,onBookmark,bindings,disabled,onOpenText,onRevealText}){
 return <ContextMenu x={value.x} y={value.y} label="选区操作" onClose={onClose}>
  <div className="context-selection">选中 {value.selection.nodes.length} 个节点 · {value.selection.edges.length} 条连线</div>
  {onOpenText&&<button role="menuitem" onClick={onOpenText}><FileText/><span>打开文本文件</span></button>}
  {onRevealText&&<button role="menuitem" onClick={onRevealText}><FolderOpen/><span>在资源管理器中显示</span></button>}
  <button role="menuitem" onClick={onConsult}><MessageSquare/><span>咨询 Agent</span></button>
  <button role="menuitem" className="danger" disabled={disabled} onClick={onDelete}><Trash2/><span>删除</span><small aria-hidden="true">{bindings.remove}</small></button>
  <div role="separator" className="context-separator"/>
  <button role="menuitem" disabled={disabled} onClick={()=>onBookmark('external')}><Bookmark/><span>加入书签（包含外部链接）</span><small aria-hidden="true">{bindings.copyExternal}</small></button>
  <button role="menuitem" disabled={disabled} onClick={()=>onBookmark('internal')}><Bookmark/><span>加入书签（不包含外部链接）</span><small aria-hidden="true">{bindings.copyInternal}</small></button>
 </ContextMenu>;
}
