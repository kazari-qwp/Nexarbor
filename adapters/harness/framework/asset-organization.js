const kinds=new Set(['tool','module']);
const name=value=>{if(typeof value!=='string'||!value.trim()||value.length>160)throw Error('名称不能为空或超过 160 字');return value.trim();};
export function organizeAssets(library,p){
 if(!kinds.has(p.kind))throw Error('无效资源类型');
 library.assets??={};const tree=library.assets[p.kind]??={folders:[],items:{}};
 const folder=id=>{if(id==null)return null;const found=tree.folders.find(f=>f.id===id);if(!found)throw Error('资源文件夹已不存在');return found;};
 if(p.action==='asset.folder.create'){
  if(typeof p.id!=='string'||!p.id||tree.folders.some(f=>f.id===p.id))throw Error('文件夹编号无效或已存在');folder(p.parent);tree.folders.push({id:p.id,name:name(p.name),parent:p.parent??null});return;
 }
 const entry=p.entry;if(!entry||!['folder','item'].includes(entry.type)||typeof entry.id!=='string'||!entry.id)throw Error('请选择资源或文件夹');
 if(entry.type==='item'&&!Object.hasOwn(tree.items,entry.id))Object.defineProperty(tree.items,entry.id,{value:{folder:null},enumerable:true,writable:true,configurable:true});
 const selected=entry.type==='folder'?folder(entry.id):tree.items[entry.id];
 if(p.action==='asset.rename'){selected.name=name(p.name);return;}
 if(p.action!=='asset.move')throw Error('未知资源操作');
 folder(p.target);
 if(entry.type==='folder'){
  for(let ancestor=p.target;ancestor!=null;ancestor=folder(ancestor).parent)if(ancestor===entry.id)throw Error('不能把文件夹放入自身或子文件夹');
  selected.parent=p.target??null;
 }else selected.folder=p.target??null;
}
