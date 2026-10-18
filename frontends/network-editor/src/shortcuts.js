export const defaultShortcuts={copyInternal:'A',copyExternal:'B',deleteBookmark:'',save:'Ctrl+S',remove:'Delete',undo:'Ctrl+Z',redo:'Ctrl+Y',assetCut:'Ctrl+X',assetPaste:'Ctrl+V',assetRename:'F2',assetNewFolder:'Ctrl+Shift+N',multiSelect:'Shift',selectionWheel:'Shift',linkDrag:{button:2,modifier:'None'},renameBookmark:{button:1,modifier:'None'}};
export const shortcuts=value=>({...defaultShortcuts,...value,linkDrag:{...defaultShortcuts.linkDrag,...value?.linkDrag},renameBookmark:{...defaultShortcuts.renameBookmark,...value?.renameBookmark}});
export function keyName(event){
 const key=event.key===' '?'Space':event.key.length===1?event.key.toUpperCase():event.key;
 if(['Control','Shift','Alt','Meta'].includes(key))return '';
 return [...(event.ctrlKey?['Ctrl']:[]),...(event.metaKey?['Meta']:[]),...(event.altKey?['Alt']:[]),...(event.shiftKey?['Shift']:[]),key].join('+');
}
export const keyMatches=(event,binding)=>!!binding&&keyName(event)===binding;
export const modifierMatches=(event,modifier)=>modifier==='None'||!!event[{Shift:'shiftKey',Control:'ctrlKey',Alt:'altKey',Meta:'metaKey'}[modifier]];
export const pointerMatches=(event,binding)=>event.button===Number(binding.button)&&modifierMatches(event,binding.modifier);
export const pointerLabel=binding=>[binding.modifier==='None'?'':binding.modifier==='Control'?'Ctrl':binding.modifier,['左键','中键','右键'][binding.button]].filter(Boolean).join('+');
