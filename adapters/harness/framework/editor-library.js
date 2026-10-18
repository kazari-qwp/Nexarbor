import {readFile,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {organizeAssets} from './asset-organization.js';

// 仅保存编辑资料，不参与网络运行和核心快照。
export function editorLibrary(directory,{catalog,inspect,purge}={}){
 const file=path.join(directory,'editor-library.json');let queue=Promise.resolve();
 const read=async()=>{let value;try{value=JSON.parse(await readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;value={version:0,bookmarks:[],history:[]};}return {categories:[{id:'default',name:'默认分类'}],settings:{},assets:{},...value};};
 const validAsset=asset=>{if(!asset||!['tool','module'].includes(asset.kind)||typeof asset.id!=='string'||!asset.id||asset.id.length>300)throw Error('无效工具或模块引用');if(asset.kind==='module'&&(!asset.config||typeof asset.config!=='object'||Array.isArray(asset.config)))throw Error('模块预设配置必须是对象');if(asset.kind==='tool'&&(!Array.isArray(asset.channels)||asset.channels.some(c=>typeof c!=='string')))throw Error('无效工具频道');};
 const valid=bookmark=>{
  if(bookmark?.asset){validAsset(bookmark.asset);if(bookmark.kind!==bookmark.asset.kind||typeof bookmark.id!=='string'||typeof bookmark.name!=='string'||!bookmark.name.trim()||bookmark.name.length>160)throw Error('无效资源书签');return;}
  if(!bookmark||typeof bookmark.id!=='string'||!['internal','external'].includes(bookmark.mode)||typeof bookmark.name!=='string'||!bookmark.name.trim()||bookmark.name.length>160||!Array.isArray(bookmark.snapshot?.nodes)||(!bookmark.snapshot.nodes.length&&!bookmark.snapshot.edges?.length))throw Error('无效的子网书签');
  if(!bookmark.snapshot.nodes.length&&bookmark.snapshot.edges.some(e=>Object.hasOwn(e,'source')||(bookmark.mode==='internal'&&Object.hasOwn(e,'target'))))throw Error('纯边书签不能保存起点，A 模式不能保存终点');
 };
 return async(operation,p={})=>{
  const result=queue.then(async()=>{
   const library=await read();if(operation==='editor.library')return library;
   if(operation==='editor.resource.inspect'){
    if(!inspect)throw Error('当前宿主不支持资源文件管理');const info=await inspect(p);
    if(library.bookmarks.some(b=>b.snapshot?.nodes.some(n=>p.kind==='module'?Object.hasOwn(n.modules??{},p.id):n.offered_tools?.some(t=>t.ref===p.id))))return {...info,canDelete:false,reason:[info.reason,'网络书签仍引用此资源'].filter(Boolean).join('；')};return info;
   }
   const changes=p.changes??[];
   const descriptors=p.action?.startsWith('asset.')&&catalog?await catalog():null;
   const definition=(kind,id)=>kind==='module'?descriptors?.modules?.[id]:descriptors?.tools?.find(t=>t.ref===id);
   if(p.action==='bookmark.patch'){
    for(const change of changes){if(typeof change.id!=='string')throw Error('书签编号无效');if(change.value){valid(change.value);if(change.value.id!==change.id||!library.categories.some(c=>c.id===(change.value.category??'default')))throw Error('书签编号或分类无效');}const current=library.bookmarks.find(b=>b.id===change.id)??null;if(JSON.stringify(current)!==JSON.stringify(change.expected??null))throw Error('书签已变化，请刷新后再试');}
    for(const change of changes){library.bookmarks=library.bookmarks.filter(b=>b.id!==change.id);if(change.value)library.bookmarks.push(change.value);}
    library.bookmarks.sort((a,b)=>b.createdAt-a.createdAt);
   }else if(p.action==='category.add'){
    if(typeof p.category?.id!=='string'||typeof p.category.name!=='string'||!p.category.name.trim()||p.category.name.length>80||library.categories.some(c=>c.id===p.category.id||c.name===p.category.name))throw Error('分类名称无效或已存在');library.categories.push(p.category);
   }else if(['asset.archive','asset.restore','asset.purge'].includes(p.action)){
    if(!['tool','module'].includes(p.kind))throw Error('无效资源类型');library.assets[p.kind]??={folders:[],items:{}};const tree=library.assets[p.kind];
    const entries=p.action==='asset.purge'?[{id:p.id}]:p.entries;if(!Array.isArray(entries)||!entries.length||entries.length>1000)throw Error('请选择资源');
    for(const {id} of entries){
     const spec=definition(p.kind,id);if(typeof id!=='string'||!spec)throw Error('资源已不在目录中');
     if(!Object.hasOwn(tree.items,id))Object.defineProperty(tree.items,id,{value:{folder:null},enumerable:true,writable:true,configurable:true});const item=tree.items[id];
     if(p.action==='asset.archive'){delete item.deletedAt;item.archivedAt=Date.now();item.resource={kind:p.kind,name:item.name??(p.kind==='module'?spec.label:spec.name),description:spec.description??'',asset:p.kind==='module'?{kind:p.kind,id,...structuredClone(spec.defaults)}:{kind:p.kind,id,channels:['tools']}};}
     else if(p.action==='asset.restore'){if(item.deletedAt)throw Error('资源已彻底删除');delete item.archivedAt;delete item.resource;}
     else{
      if(!item.archivedAt||p.confirm!==id)throw Error('请先归档并确认资源编号');
      if(library.bookmarks.some(b=>b.snapshot?.nodes.some(n=>p.kind==='module'?Object.hasOwn(n.modules??{},id):n.offered_tools?.some(t=>t.ref===id))))throw Error('网络书签仍引用此资源，请先处理书签');
      if(!inspect||!purge)throw Error('当前宿主不支持资源文件删除');const info=await inspect({kind:p.kind,id});if(!info.canDelete)throw Error(info.reason??'资源仍被使用');
      await purge({kind:p.kind,id,confirm:id});item.deletedAt=Date.now();delete item.archivedAt;delete item.resource;
      library.bookmarks=library.bookmarks.filter(b=>b.asset?.kind!==p.kind||b.asset.id!==id);library.history=library.history.filter(e=>e.asset?.kind!==p.kind||e.asset.id!==id);
     }
    }
   }else if(p.action?.startsWith('asset.')){
    const ids=p.kind==='module'?Object.keys(descriptors?.modules??{}):(descriptors?.tools??[]).map(t=>t.ref);organizeAssets(library,p,{ids});
   }else if(p.action==='history.rename'){
    const entry=library.history.find(e=>e.kind===p.kind&&e.id===p.id);if(!entry||JSON.stringify(entry)!==JSON.stringify(p.expected))throw Error('历史条目已变化，请重新操作');
    if(typeof p.name!=='string'||!p.name.trim()||p.name.length>160)throw Error('无效名称');entry.label=p.name.trim();entry.renamed=true;
   }else if(p.action==='settings.save'){
    if(!p.settings||typeof p.settings!=='object'||Array.isArray(p.settings))throw Error('无效客户端设置');library.settings=p.settings;
   }else if(p.action!=='history.push')throw Error('未知的编辑资料操作');
   for(const entry of p.action==='history.push'?p.entries??[]:[]){
    if(!['node','edge','bookmark','tool','module'].includes(entry.kind)||typeof entry.id!=='string'||typeof entry.label!=='string')throw Error('无效历史条目');
    if(['tool','module'].includes(entry.kind)||entry.asset){validAsset(entry.asset);if(entry.kind!==entry.asset.kind)throw Error('历史资源类型不一致');}
    const old=library.history.find(e=>e.kind===entry.kind&&e.id===entry.id);library.history=library.history.filter(e=>e.kind!==entry.kind||e.id!==entry.id);library.history.unshift({...entry,...(old?.renamed?{label:old.label,renamed:true}:{}),time:Date.now()});
   }
   library.history=library.history.slice(0,100);library.version++;
   const encoded=JSON.stringify(library);if(Buffer.byteLength(encoded)>8_000_000)throw Error('书签资料超过 8 MB，请移除不需要的书签');
   const temporary=file+'.'+randomUUID()+'.tmp';await writeFile(temporary,encoded);await rename(temporary,file);return library;
  });queue=result.catch(()=>{});return result;
 };
}
