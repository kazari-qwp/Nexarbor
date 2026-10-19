import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {storedNetworks} from '../framework/stored-networks.js';

export const applications=[
 {id:'fixed_groups_v3',name:'固定讨论与协作组',description:'讨论小组与去中心化协作小组，包含私人记忆和公共讨论、任务及公告板。'},
 {id:'knowledge_v3',name:'知识归档与恢复',description:'归档、修订恢复及独立 JSON、CSV、SQLite、RAG、Wiki 数据节点。'},
 {id:'npc_town_v3',name:'NPC小镇',description:'21 节点完整小镇：时刻、居民、地点、移动、资源、交易与家庭。'}
];
// 每个工作区首次安装一份独立成品副本；重启不覆盖用户的编辑、归档或删除。
export async function installApplicationPresets(directory,root){
 const store=storedNetworks(directory),base=path.join(directory,'network_presets');await fs.mkdir(base,{recursive:true});
 if(!(await fs.realpath(base)).startsWith((await fs.realpath(directory))+path.sep))throw Error('成品网络目录越出工作区');
 const file=path.join(base,'applications-installed.json');let installed;
 try{installed=JSON.parse(await fs.readFile(file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;installed={version:1,applications:{}};}
 const save=async()=>{const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(installed,null,2)+'\n');await fs.rename(temp,file);};
 for(const app of applications){
  if(installed.applications[app.id])continue;
  const existing=(await store.list()).presets.find(p=>p.originBookmark==='application:'+app.id);
  if(existing){installed.applications[app.id]=existing.id;await save();continue;}
  const folder=path.join(root,'configs',app.id),profile=JSON.parse(await fs.readFile(path.join(folder,'profile.json'),'utf8')),document=JSON.parse(await fs.readFile(path.join(folder,profile.network),'utf8'));
  const runtime={components:profile.components??[],templates:profile.templates?JSON.parse(await fs.readFile(path.join(folder,profile.templates),'utf8')):[]};
  const preset=await store.save({storageKind:'network',document,editor:{name:app.name,description:app.description,mode:'internal',positions:{},display_folder:'stored-networks',originBookmark:'application:'+app.id,application:app.id,runtime}});
  installed.applications[app.id]=preset.id;await save();
 }
 return (await store.list()).presets.filter(p=>Object.values(installed.applications).includes(p.id));
}
