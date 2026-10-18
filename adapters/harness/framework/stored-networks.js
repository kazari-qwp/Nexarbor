import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

// 两类文件采用相同网络文档格式，仅真实存储目录和编辑资料不同。
export function storedNetworks(directory){
 const base=path.resolve(directory),root=path.join(base,'network_presets'),parts={fragment:'fragments',network:'networks'};
 const checked=async(folder,file)=>{
  const actualBase=await fs.realpath(base),actualFolder=await fs.realpath(folder);
  if(!actualFolder.startsWith(actualBase+path.sep))throw Error('网络预设目录越出当前工作区');
  if(path.dirname(file)!==folder)throw Error('网络预设路径无效');
  try{const stat=await fs.lstat(file);if(!stat.isFile()||stat.isSymbolicLink())throw Error('网络预设必须是当前工作区内的普通文件');}catch(error){if(error.code!=='ENOENT')throw error;}
 };
 const atomic=async(file,value)=>{const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(value,null,2)+'\n');await fs.rename(temp,file);};
 const list=async()=>{
  const presets=[],errors=[];
  for(const [storageKind,part] of Object.entries(parts)){
   const folder=path.join(root,part);let entries;try{entries=await fs.readdir(folder,{withFileTypes:true});}catch(error){if(error.code==='ENOENT')continue;throw error;}
   for(const entry of entries){
    if(!entry.isFile()||!entry.name.endsWith('.json')||entry.name.endsWith('.editor.json'))continue;
    const file=path.join(folder,entry.name),metadataFile=file.slice(0,-5)+'.editor.json';
    try{
     await checked(folder,file);const document=JSON.parse(await fs.readFile(file,'utf8'));
     if(document.network?.version!==8||!Array.isArray(document.network.nodes)||!document.network.nodes.length)throw Error('需要当前 v8 网络文档');
     let editor={};try{await checked(folder,metadataFile);editor=JSON.parse(await fs.readFile(metadataFile,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
     presets.push({id:storageKind+':'+entry.name,name:editor.name??path.basename(entry.name,'.json'),description:editor.description??'',mode:editor.mode??'internal',snapshot:{nodes:document.network.nodes,files:document.files??{},positions:editor.positions??{}},originBookmark:editor.originBookmark,display_folder:editor.display_folder,storageKind,file,metadataFile});
    }catch(error){errors.push(entry.name+'：'+error.message);}
   }
  }
  return {presets,errors};
 };
 const save=async({storageKind,existingId,document,editor})=>{
  if(!Object.hasOwn(parts,storageKind)||document.network?.version!==8||!Array.isArray(document.network.nodes)||!document.network.nodes.length)throw Error('无效的网络预设文档');
  const existing=(await list()).presets.find(p=>p.id===existingId&&p.storageKind===storageKind),folder=path.join(root,parts[storageKind]);await fs.mkdir(folder,{recursive:true});
  const file=existing?.file??path.join(folder,randomUUID()+'.json'),metadataFile=file.slice(0,-5)+'.editor.json';await checked(folder,file);await checked(folder,metadataFile);
  // network JSON 本身就是成品网络；布局、名称与复制方式放入旁边的编辑资料。
  await atomic(metadataFile,{version:1,...editor});await atomic(file,document);
  return (await list()).presets.find(p=>p.file===file);
 };
 const inspect=async id=>{const preset=(await list()).presets.find(p=>p.id===id);if(!preset)throw Error('网络预设文件已不存在');return {canDelete:true,scope:'删除当前工作区的'+(preset.storageKind==='network'?'完整网络':'零件预设')+'文件及编辑资料；独立书签和历史缓存保留',path:preset.file,files:[preset.file,preset.metadataFile]};};
 const remove=async id=>{const info=await inspect(id);for(const file of info.files){await checked(path.dirname(file),file);try{await fs.unlink(file);}catch(error){if(error.code!=='ENOENT')throw error;}}};
 return {list,save,inspect,remove};
}
