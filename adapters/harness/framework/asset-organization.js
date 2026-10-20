const kinds=new Set(['tool','module','skill','node','preset']);
const name=value=>{if(typeof value!=='string'||!value.trim()||value.length>160)throw Error('名称不能为空或超过 160 字');return value.trim();};
export function descendantFolders(tree,id){
 const result=new Set([id]);for(const parent of result)for(const f of tree.folders)if(f.parent===parent)result.add(f.id);return result;
}
export function organizeAssets(library,p,{ids=[]}={}){
 if(!kinds.has(p.kind))throw Error('无效资源类型');
 library.assets??={};const tree=library.assets[p.kind]??={folders:[],items:{}};
 const folder=id=>{if(id==null)return null;const found=tree.folders.find(f=>f.id===id);if(!found)throw Error('资源文件夹已不存在');return found;};
 if(p.action==='asset.folder.delete'&&p.ids){if(!Array.isArray(p.ids)||!p.ids.length)throw Error('请选择文件夹');for(const id of p.ids)organizeAssets(library,{...p,ids:undefined,id},{ids});return;}
 if(p.action==='asset.folder.create'){
  if(typeof p.id!=='string'||!p.id||tree.folders.some(f=>f.id===p.id))throw Error('文件夹编号无效或已存在');folder(p.parent);tree.folders.push({id:p.id,name:name(p.name),parent:p.parent??null});return;
 }
 if(p.action==='asset.folder.delete'){
  folder(p.id);if(p.id==null)throw Error('不能删除资源根目录');const descendants=descendantFolders(tree,p.id);if(tree.folders.some(f=>f.system&&descendants.has(f.id)))throw Error('系统分类不能删除');
  const resources=new Set([...ids,...Object.keys(tree.items)]);
  if([...resources].some(id=>(ids.includes(id)||!tree.items[id]?.deletedAt)&&descendants.has(tree.items[id]?.folder??null)))throw Error('文件夹或子目录内仍有资源，请先移走或彻底删除资源');
  tree.folders=tree.folders.filter(f=>!descendants.has(f.id));for(const item of Object.values(tree.items))if(descendants.has(item.folder))item.folder=null;return;
 }
 if(p.action==='asset.move'&&p.entries){
  if(!Array.isArray(p.entries)||!p.entries.length||p.entries.length>1000)throw Error('无效批量选择');
  for(const entry of p.entries)organizeAssets(library,{...p,entries:undefined,entry});return;
 }
 const entry=p.entry;if(!entry||!['folder','item'].includes(entry.type)||typeof entry.id!=='string'||!entry.id)throw Error('请选择资源或文件夹');
 if(entry.type==='item'&&!Object.hasOwn(tree.items,entry.id))Object.defineProperty(tree.items,entry.id,{value:{folder:null},enumerable:true,writable:true,configurable:true});
 const selected=entry.type==='folder'?folder(entry.id):tree.items[entry.id];
 if(entry.type==='folder'&&selected.system)throw Error('系统分类不能重命名或移动');
 if(p.action==='asset.rename'){selected.name=name(p.name);return;}
 if(p.action!=='asset.move')throw Error('未知资源操作');
 folder(p.target);
 if(entry.type==='folder'){
  for(let ancestor=p.target;ancestor!=null;ancestor=folder(ancestor).parent)if(ancestor===entry.id)throw Error('不能把文件夹放入自身或子文件夹');
  selected.parent=p.target??null;
 }else selected.folder=p.target??null;
}
