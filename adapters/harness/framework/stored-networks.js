import {repeatMetadata,validRepeatMetadata} from '../../../shared/graph/preset-parameters.js';
import {singleOwnedNode,ownershipRoots} from '../../../shared/graph/ownership.js';
import {projectDirectory} from './project-directory.js';
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

// 目录只取摘要；打开、拖动、检查引用时才读取对应完整文档。
export const storedNetworks=directory=>storedDocuments(projectDirectory(directory),{rootName:'network_presets',parts:{fragment:'fragments',network:'networks'},label:'网络预设'});
export const storedNodes=directory=>storedDocuments(projectDirectory(directory),{rootName:'node_presets',parts:{node:'nodes'},label:'节点预设',singleNode:true});
function storedDocuments(directory,{rootName,parts,label,singleNode=false}){
 const base=path.resolve(directory),root=path.join(base,rootName),summaries=new Map();
 const valid=(document,kind)=>document.network?.version===8&&validRepeatMetadata(document.network)&&Array.isArray(document.network.nodes)&&(singleNode?singleOwnedNode(document.network.nodes):kind==='network'||document.network.nodes.length>0);
 const checked=async(folder,file)=>{
  const actualBase=await fs.realpath(base),actualFolder=await fs.realpath(folder);
  if(!actualFolder.startsWith(actualBase+path.sep))throw Error(label+'目录越出当前工作区');
  if(path.dirname(file)!==folder)throw Error(label+'路径无效');
  try{const stat=await fs.lstat(file);if(!stat.isFile()||stat.isSymbolicLink())throw Error(label+'必须是当前工作区内的普通文件');}catch(error){if(error.code!=='ENOENT')throw error;}
 };
 const atomic=async(file,value)=>{const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(value,null,2)+'\n');await fs.rename(temp,file);};
 const stamp=stat=>({size:stat.size,mtimeMs:stat.mtimeMs});
 const matches=(a,b)=>a?.size===b.size&&a?.mtimeMs===b.mtimeMs;
 const read=async(storageKind,name,{summary=false}={})=>{
  const folder=path.join(root,parts[storageKind]),file=path.join(folder,name),metadataFile=file.slice(0,-5)+'.editor.json';
  await checked(folder,file);const stat=stamp(await fs.stat(file));
  let editor={};try{await checked(folder,metadataFile);editor=JSON.parse(await fs.readFile(metadataFile,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
  let document,info=matches(editor.documentStamp,stat)?editor.summary:undefined;
  info??=matches(summaries.get(file)?.stamp,stat)?summaries.get(file).info:undefined;
  if(!summary||!info){
   document=JSON.parse(await fs.readFile(file,'utf8'));
   if(!valid(document,storageKind))throw Error(singleNode?'节点预设需要包含一个节点的 v8 文档':'需要当前 v8 网络文档');
   info={...repeatMetadata(document.network),nodeCount:document.network.nodes.length,hasRoot:document.network.nodes.some(n=>n.node_id==='root')};summaries.set(file,{stamp:stat,info});
  }
  return {id:storageKind+':'+name,name:editor.name??path.basename(name,'.json'),description:editor.description??'',mode:editor.mode??'internal',...info,...(summary?{lazySnapshot:true}:{snapshot:{...repeatMetadata(document.network),nodes:document.network.nodes,files:document.files??{},positions:editor.positions??{},...(editor.entryEdges?.length?{edges:structuredClone(editor.entryEdges)}:{})}}),originBookmark:editor.originBookmark,display_folder:editor.display_folder,storageKind,file,metadataFile,runtime:summary?undefined:editor.runtime,application:editor.application};
 };
 const load=async(id,options={})=>{
  const separator=id.indexOf(':'),kind=id.slice(0,separator),name=id.slice(separator+1);
  if(!Object.hasOwn(parts,kind)||!name.endsWith('.json')||name.endsWith('.editor.json')||path.basename(name)!==name||/[\\/]/.test(name))throw Error(label+'编号无效');
  return read(kind,name,options);
 };
 const list=async(options={})=>{
  const presets=[],errors=[];
  for(const [storageKind,part] of Object.entries(parts)){
   const folder=path.join(root,part);let entries;try{entries=await fs.readdir(folder,{withFileTypes:true});}catch(error){if(error.code==='ENOENT')continue;throw error;}
   for(const entry of entries){
    if(!entry.isFile()||!entry.name.endsWith('.json')||entry.name.endsWith('.editor.json'))continue;
    try{presets.push(await read(storageKind,entry.name,options));}catch(error){errors.push(entry.name+'：'+error.message);}
   }
  }
  return {presets,errors};
 };
 const save=async({storageKind,existingId,document,editor})=>{
  if(!Object.hasOwn(parts,storageKind)||!valid(document,storageKind))throw Error('无效的'+label+'文档');
  const existing=existingId?await load(existingId,{summary:true}):null;if(existing&&existing.storageKind!==storageKind)throw Error('预设存储类型不一致');
  const folder=path.join(root,parts[storageKind]);await fs.mkdir(folder,{recursive:true});
  const file=existing?.file??path.join(folder,randomUUID()+'.json'),metadataFile=file.slice(0,-5)+'.editor.json';await checked(folder,file);await checked(folder,metadataFile);
  // JSON 保留完整网络格式；摘要与布局是可重建的编辑资料，不是数据副本。
  await atomic(file,document);
  await atomic(metadataFile,{version:1,...editor,documentStamp:stamp(await fs.stat(file)),summary:{...repeatMetadata(document.network),nodeCount:document.network.nodes.length,hasRoot:document.network.nodes.some(n=>n.node_id==='root')}});
  return load(storageKind+':'+path.basename(file));
 };
 const inspect=async id=>{const preset=await load(id,{summary:true});return {canDelete:true,scope:'删除当前工作区的'+(singleNode?'节点预设':preset.storageKind==='network'?'完整网络':'零件预设')+'文件及编辑资料；独立书签和历史缓存保留',path:preset.file,files:[preset.file,preset.metadataFile]};};
 const remove=async id=>{const info=await inspect(id);for(const file of info.files){await checked(path.dirname(file),file);try{await fs.unlink(file);}catch(error){if(error.code!=='ENOENT')throw error;}}summaries.delete(info.path);};
 return {list,load,save,inspect,remove};
}
