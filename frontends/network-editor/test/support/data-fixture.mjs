// Original five operator data types, seeded through their actual Dataers; no model calls.
import path from 'node:path';import {copyProjectLibrary} from './project-library.mjs';
import {startStudio} from '../../../../adapt/harness/studio/host.mjs';
import {setModule} from '../../../shared/graph/node-records.js';
export async function dataFixture(root,directory){
 await copyProjectLibrary(path.join(root,'项目演示/应用2-资料库-初始'),directory);
 const host=await startStudio({directory});
 try{
  const state=await host.request('state',{}),catalog=await host.request('catalog',{});let document=state.live.document;
  for(const kind of ['value','csv','sqlite','rag','wiki']){
   const template=catalog.nodes.find(n=>n.id===kind);if(!template)throw Error('Missing original data template '+kind);
   const snapshot=structuredClone(template.snapshot),node=snapshot.nodes[0];node.node_id='knowledge/'+kind;document.network.nodes.push(node);Object.assign(document.files,snapshot.files);
   const key=kind==='value'?'value':kind==='rag'?'energy':kind==='wiki'?'welcome':'example';
   const value=kind==='value'?{seed:123}:kind==='rag'?'太阳能电池把阳光转换为电能。':kind==='wiki'?'本节点保存独立 Wiki 页面和版本。':{id:'example',text:'这条记录可独立复制和修改。'};
   const preview=await host.request('data.preview',{node,files:document.files,operation:'write',arguments:{key,value}});Object.assign(document.files,preview.files);
  }
  document=await host.request('template',{kind:'markdown',options:{id:'text-source',name:'原始文本'},document});const text=document.network.nodes.at(-1);setModule(text,'data.local',structuredClone(catalog.modules['data.local'].defaults));document.files[text.data.path]='文本原件正文';
  await host.request('apply',{document,base_commit:state.live.commit});
  for(const [kind,key] of [['rag','energy'],['wiki','welcome']])await host.request('module.call',{node:'knowledge/'+kind,module:'data.local',operation:'read',arguments:{key}});
  return host;
 }catch(error){await host.close();throw error;}
}
