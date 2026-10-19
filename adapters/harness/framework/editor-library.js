import {singleOwnedNode,ownershipRoots} from '../../../shared/graph/ownership.js';
import {projectDirectory} from './project-directory.js';
import {readFile,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {organizeAssets} from './asset-organization.js';
import {normalizeHistory,compactHistory} from './editor-history.js';
import {storedNetworks,storedNodes} from './stored-networks.js';

// 仅保存编辑资料，不参与网络运行和核心快照。
export function editorLibrary(directory,{catalog,inspect,purge,runtime}={}){
 const file=path.join(projectDirectory(directory),'editor-library.json'),store=storedNetworks(directory),nodeStore=storedNodes(directory);let queue=Promise.resolve();
 const read=async()=>{let value;try{value=JSON.parse(await readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;value={version:0,bookmarks:[],history:[]};}const library={categories:[{id:'default',name:'默认分类'}],settings:{},assets:{},presets:[],nodeTemplates:[],...value};return library;};
 const write=async library=>{library.version++;const {presets,presetErrors,nodeTemplates,nodeErrors,...metadata}=library;const encoded=JSON.stringify(metadata);if(Buffer.byteLength(encoded)>8_000_000)throw Error('书签资料超过 8 MB，请移除不需要的书签');const temporary=file+'.'+randomUUID()+'.tmp';await writeFile(temporary,encoded);await rename(temporary,file);return library;};
 const validAsset=asset=>{if(!asset||!['tool','module'].includes(asset.kind)||typeof asset.id!=='string'||!asset.id||asset.id.length>300)throw Error('无效工具或模块引用');if(asset.kind==='module'&&(!asset.config||typeof asset.config!=='object'||Array.isArray(asset.config)))throw Error('模块预设配置必须是对象');if(asset.kind==='tool'&&(!Array.isArray(asset.channels)||asset.channels.some(c=>typeof c!=='string')))throw Error('无效工具频道');};
 const valid=bookmark=>{
  if(bookmark?.asset){validAsset(bookmark.asset);if(bookmark.kind!==bookmark.asset.kind||typeof bookmark.id!=='string'||typeof bookmark.name!=='string'||!bookmark.name.trim()||bookmark.name.length>160)throw Error('无效资源书签');return;}
  if(!bookmark||typeof bookmark.id!=='string'||!['internal','external'].includes(bookmark.mode)||typeof bookmark.name!=='string'||!bookmark.name.trim()||bookmark.name.length>160||!Array.isArray(bookmark.snapshot?.nodes)||(!bookmark.snapshot.nodes.length&&!bookmark.snapshot.edges?.length))throw Error('无效的子网书签');
  if(!bookmark.snapshot.nodes.length&&bookmark.snapshot.edges.some(e=>Object.hasOwn(e,'source')||(bookmark.mode==='internal'&&Object.hasOwn(e,'target'))))throw Error('纯边书签不能保存起点，A 模式不能保存终点');
 };
 return async(operation,p={})=>{
  if(operation==='editor.resource.load'){if(!['node','preset'].includes(p.kind))throw Error('该资源无需加载网络快照');return (p.kind==='node'?nodeStore:store).load(p.id);}
  const result=queue.then(async()=>{
   const library=await read();
   const summary=operation==='editor.library.index'||p.summary===true;
   // 删除模块前仍检查所有磁盘预设的真实引用；目录展示无需读取正文。
   const options={summary:summary&&!((operation==='editor.resource.inspect'||p.action==='asset.purge')&&['module','tool'].includes(p.kind))};
   const [stored,nodes]=await Promise.all([store.list(options),nodeStore.list(options)]);library.presets=stored.presets;library.presetErrors=stored.errors;library.nodeTemplates=nodes.presets;library.nodeErrors=nodes.errors;
   const presetTree=library.assets.preset??={folders:[],items:{}};
   if(!presetTree.folders.some(f=>f.id==='stored-networks'))presetTree.folders.unshift({id:'stored-networks',name:'已存储网络',parent:null,system:true});
   for(const preset of library.presets)if(!Object.hasOwn(presetTree.items,preset.id))presetTree.items[preset.id]={folder:presetTree.folders.some(f=>f.id===preset.display_folder)?preset.display_folder:preset.storageKind==='network'?'stored-networks':null};
   const descriptors=catalog?await catalog():null;library.history=compactHistory(library.history,descriptors?.modules);
   const nodeTree=library.assets.node??={folders:[],items:{}};
   for(const [id,name] of [['official-nodes','官方节点'],['stored-nodes','已保存节点']])if(!nodeTree.folders.some(f=>f.id===id))nodeTree.folders.push({id,name,parent:null,system:true});
   const inOfficial=id=>{const seen=new Set();for(;id!=null&&!seen.has(id);id=nodeTree.folders.find(f=>f.id===id)?.parent){if(id==='official-nodes')return true;seen.add(id);}return false;};
   for(const spec of descriptors?.nodes??[])nodeTree.items[spec.id]={...nodeTree.items[spec.id],folder:'official-nodes'};
   for(const spec of library.nodeTemplates)if(!Object.hasOwn(nodeTree.items,spec.id))nodeTree.items[spec.id]={folder:nodeTree.folders.some(f=>f.id===spec.display_folder)&&!inOfficial(spec.display_folder)?spec.display_folder:'stored-nodes'};
   const definitions=kind=>kind==='module'?Object.entries(descriptors?.modules??{}).map(([id,spec])=>({id,...spec})):kind==='tool'?(descriptors?.tools??[]).map(t=>({...t,id:t.ref})):kind==='preset'?library.presets:[...(descriptors?.nodes??[]),...library.nodeTemplates];
   const definition=(kind,id)=>definitions(kind).find(s=>s.id===id);
   let reconciled=false;
   for(const kind of ['module','tool'])for(const spec of definitions(kind))if(spec.display_folder!==undefined&&!Object.hasOwn(library.assets[kind]?.items??{},spec.id)){
    const tree=library.assets[kind]??={folders:[],items:{}};tree.items[spec.id]={folder:tree.folders.some(f=>f.id===spec.display_folder)?spec.display_folder:null};reconciled=true;
   }
   if(operation==='editor.library'||operation==='editor.library.index')return reconciled?write(library):library;
   if(operation==='editor.resource.inspect'){
    if(p.kind==='node')return library.nodeTemplates.some(n=>n.id===p.id)?nodeStore.inspect(p.id):{canDelete:false,reason:'官方节点模板不可彻底删除，可以归档或恢复'};
    if(p.kind==='preset')return store.inspect(p.id);
    if(!inspect)throw Error('当前宿主不支持资源文件管理');const info=await inspect(p);
    if([...library.bookmarks,...library.presets,...library.nodeTemplates].some(b=>b.snapshot?.nodes.some(n=>p.kind==='module'?Object.hasOwn(n.modules??{},p.id):n.offered_tools?.some(t=>t.ref===p.id))))return {...info,canDelete:false,reason:[info.reason,'网络书签或预设仍引用此资源'].filter(Boolean).join('；')};return info;
   }
   const changes=p.changes??[];
   if(p.action==='bookmark.patch'){
    for(const change of changes){if(typeof change.id!=='string')throw Error('书签编号无效');if(change.value){valid(change.value);if(change.value.id!==change.id||!library.categories.some(c=>c.id===(change.value.category??'default')))throw Error('书签编号或分类无效');}const current=library.bookmarks.find(b=>b.id===change.id)??null;if(JSON.stringify(current)!==JSON.stringify(change.expected??null))throw Error('书签已变化，请刷新后再试');}
    for(const change of changes){library.bookmarks=library.bookmarks.filter(b=>b.id!==change.id);if(change.value)library.bookmarks.push(change.value);}
    library.bookmarks.sort((a,b)=>b.createdAt-a.createdAt);
   }else if(p.action==='category.add'){
    if(typeof p.category?.id!=='string'||typeof p.category.name!=='string'||!p.category.name.trim()||p.category.name.length>80||library.categories.some(c=>c.id===p.category.id||c.name===p.category.name))throw Error('分类名称无效或已存在');library.categories.push(p.category);
   }else if(p.action==='node.save'){
    const book=library.bookmarks.find(b=>b.id===p.bookId);if(!book||book.asset||!singleOwnedNode(book.snapshot?.nodes))throw Error('请选择单节点书签');
    if(p.folder!=null&&!nodeTree.folders.some(f=>f.id===p.folder))throw Error('节点文件夹已不存在');
    const folder=p.folder==null||inOfficial(p.folder)?'stored-nodes':p.folder;
    const existing=library.nodeTemplates.find(e=>e.originBookmark===book.id&&(nodeTree.items[e.id]?.folder??'stored-nodes')===folder);
    const template=await nodeStore.save({storageKind:'node',existingId:existing?.id,document:{network:{version:8,nodes:structuredClone(book.snapshot.nodes),signals:{},delegations:[]},files:structuredClone(book.snapshot.files??{})},editor:{name:book.name,description:book.description??ownershipRoots(book.snapshot.nodes)[0].description??'',mode:book.mode,positions:book.snapshot.positions??{},entryEdges:structuredClone(book.snapshot.edges??[]),originBookmark:book.id,display_folder:folder}});
    library.nodeTemplates=(await nodeStore.list(options)).presets;nodeTree.items[template.id]??={folder};
    delete nodeTree.items[template.id].archivedAt;delete nodeTree.items[template.id].deletedAt;delete nodeTree.items[template.id].resource;
   }else if(p.action==='preset.save'){
    const book=library.bookmarks.find(b=>b.id===p.bookId);if(!book||book.asset||book.snapshot?.nodes.length<2)throw Error('请选择包含多个节点的网络书签');
    const tree=library.assets.preset??={folders:[],items:{}};if(p.folder!=null&&!tree.folders.some(f=>f.id===p.folder))throw Error('预设文件夹已不存在');
    const ancestors=new Set();for(let id=p.folder;id!=null&&!ancestors.has(id);id=tree.folders.find(f=>f.id===id)?.parent)ancestors.add(id);
    const storageKind=ancestors.has('stored-networks')?'network':'fragment';
    const existing=library.presets.find(e=>e.storageKind===storageKind&&e.originBookmark===book.id&&(tree.items[e.id]?.folder??null)===(p.folder??null));
    const preset=await store.save({storageKind,existingId:existing?.id,document:{network:{version:8,nodes:structuredClone(book.snapshot.nodes),signals:{},delegations:[]},files:structuredClone(book.snapshot.files??{})},editor:{name:book.name,description:book.description??'',mode:book.mode,positions:book.snapshot.positions??{},entryEdges:structuredClone(book.snapshot.edges??[]),originBookmark:book.id,display_folder:p.folder??null,runtime}});
    library.presets=(await store.list(options)).presets;tree.items[preset.id]??={folder:p.folder??null};
    delete tree.items[preset.id].archivedAt;delete tree.items[preset.id].resource;
   }else if(p.action==='network.save'){
    if(typeof p.name!=='string'||!p.name.trim()||p.name.length>160||!Array.isArray(p.document?.network?.nodes))throw Error('完整网络需要名称和节点列表');
    const preset=await store.save({storageKind:'network',document:structuredClone(p.document),editor:{name:p.name.trim(),mode:'internal',positions:p.layout??{},display_folder:'stored-networks',runtime}});
    library.presets=(await store.list(options)).presets;presetTree.items[preset.id]={folder:'stored-networks'};
   }else if(['asset.archive','asset.restore','asset.purge'].includes(p.action)){
    if(!['tool','module','node','preset'].includes(p.kind))throw Error('无效资源类型');library.assets[p.kind]??={folders:[],items:{}};const tree=library.assets[p.kind];
    const entries=p.action==='asset.purge'?[{id:p.id}]:p.entries;if(!Array.isArray(entries)||!entries.length||entries.length>1000)throw Error('请选择资源');
    for(const {id} of entries){
     let spec=definition(p.kind,id);
     if(p.action==='asset.archive'&&spec?.lazySnapshot)spec=await (p.kind==='node'?nodeStore:store).load(id);if(typeof id!=='string'||!spec)throw Error('资源已不在目录中');
     if(!Object.hasOwn(tree.items,id))Object.defineProperty(tree.items,id,{value:{folder:null},enumerable:true,writable:true,configurable:true});const item=tree.items[id];
     if(p.action==='asset.archive'){delete item.deletedAt;item.archivedAt=Date.now();item.resource={kind:p.kind,name:item.name??(p.kind==='module'?spec.label:spec.name),description:spec.description??'',...(['node','preset'].includes(p.kind)?{resourceId:id,mode:spec.mode,storageKind:spec.storageKind,snapshot:structuredClone(spec.snapshot)}:{asset:p.kind==='module'?{kind:p.kind,id,...structuredClone(spec.defaults)}:{kind:p.kind,id,channels:['tools']}})};}
     else if(p.action==='asset.restore'){if(item.deletedAt)throw Error('资源已彻底删除');delete item.archivedAt;delete item.resource;}
     else{
      if(!item.archivedAt||p.confirm!==id)throw Error('请先归档并确认资源编号');
      if(p.kind==='node'){if(!library.nodeTemplates.some(n=>n.id===id))throw Error('官方节点模板不可彻底删除');await nodeStore.remove(id);library.nodeTemplates=library.nodeTemplates.filter(e=>e.id!==id);item.deletedAt=Date.now();delete item.archivedAt;delete item.resource;continue;}
      if(p.kind==='preset'){await store.remove(id);library.presets=library.presets.filter(e=>e.id!==id);item.deletedAt=Date.now();delete item.archivedAt;delete item.resource;continue;}
      if([...library.bookmarks,...library.presets,...library.nodeTemplates].some(b=>b.snapshot?.nodes.some(n=>p.kind==='module'?Object.hasOwn(n.modules??{},id):n.offered_tools?.some(t=>t.ref===id))))throw Error('网络书签或预设仍引用此资源，请先处理');
      if(!inspect||!purge)throw Error('当前宿主不支持资源文件删除');const info=await inspect({kind:p.kind,id});if(!info.canDelete)throw Error(info.reason??'资源仍被使用');
      await purge({kind:p.kind,id,confirm:id});item.deletedAt=Date.now();delete item.archivedAt;delete item.resource;
      library.bookmarks=library.bookmarks.filter(b=>b.asset?.kind!==p.kind||b.asset.id!==id);library.history=library.history.filter(e=>e.asset?.kind!==p.kind||e.asset.id!==id);
     }
    }
   }else if(p.action?.startsWith('asset.')){
    if(p.kind==='node'){
     if(p.action==='asset.folder.create'&&inOfficial(p.parent))throw Error('请在自定义节点目录新建文件夹');
     if(p.action==='asset.move'){if(inOfficial(p.target))throw Error('官方节点目录不能放入自定义资源');for(const entry of p.entries??[p.entry])if(entry?.type==='item'&&(descriptors?.nodes??[]).some(n=>n.id===entry.id))throw Error('官方节点保留在官方节点目录，可归档或复制为自定义节点');}
    }
    organizeAssets(library,p,{ids:definitions(p.kind).map(s=>s.id)});
   }else if(p.action==='history.rename'){
    const entry=library.history.find(e=>e.kind===p.kind&&e.id===p.id);if(!entry||JSON.stringify(entry)!==JSON.stringify(p.expected))throw Error('历史条目已变化，请重新操作');
    if(typeof p.name!=='string'||!p.name.trim()||p.name.length>160)throw Error('无效名称');entry.label=p.name.trim();entry.renamed=true;
   }else if(p.action==='settings.save'){
    if(!p.settings||typeof p.settings!=='object'||Array.isArray(p.settings))throw Error('无效客户端设置');library.settings=p.settings;
   }else if(p.action!=='history.push')throw Error('未知的编辑资料操作');
   for(const entry of p.action==='history.push'?p.entries??[]:[]){
    if(!['node','edge','network','bookmark','tool','module'].includes(entry.kind)||typeof entry.id!=='string'||typeof entry.label!=='string')throw Error('无效历史条目');
    if(['tool','module'].includes(entry.kind)||entry.asset){validAsset(entry.asset);if(entry.kind!==entry.asset.kind)throw Error('历史资源类型不一致');}
    const normalized=normalizeHistory(entry,descriptors?.modules),old=library.history.find(e=>e.kind===normalized.kind&&e.id===normalized.id);library.history=library.history.filter(e=>e.kind!==normalized.kind||e.id!==normalized.id);library.history.unshift({...normalized,...(old?.renamed?{label:old.label,renamed:true}:{}),time:Date.now()});
   }
   library.history=library.history.slice(0,100);return write(library);
  });queue=result.catch(()=>{});return result;
 };
}
