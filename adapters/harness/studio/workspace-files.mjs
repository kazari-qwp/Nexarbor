// 工作区保存、便携网络文件与上下文分支。网络权限与运行仍交给已有核心。
import fs from 'node:fs/promises';import path from 'node:path';import {randomUUID} from 'node:crypto';import {fileURLToPath} from 'node:url';
import {NativeRunner} from './runtime/runner.mjs';import {isDeepStrictEqual} from 'node:util';
const graphState=document=>{const value=structuredClone(document);for(const node of value.network.nodes)delete node.context_cursor;return value;};
const clone=structuredClone;
const read=async(file,fallback=null)=>{try{return JSON.parse(await fs.readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;return fallback;}};
const atomic=async(file,value)=>{const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(value));await fs.rename(temp,file);};
export class WorkspaceFiles{
 constructor(directory,rpc,native,runtime={}){this.directory=directory;this.rpc=rpc;this.native=native;this.runtime=runtime;this.file=path.join(directory,'workspace-session.json');this.queue=Promise.resolve();this.logs=new NativeRunner(directory,()=>{throw Error('日志适配器不能调用网络');},{script:fileURLToPath(new URL('./runtime/log-host.cjs',import.meta.url)),noCredentials:true});}
 async state(){return read(this.file);}
 serial(fn){const job=this.queue.then(fn);this.queue=job.catch(()=>{});return job;}
 async close(){await this.queue;await this.logs.close();}
 bindings(state,document=state.live.document){const ids=new Set(document.network.nodes.filter(n=>n.type==='agent').map(n=>n.node_id));return Object.fromEntries(Object.entries(state.live.sessions).filter(([id])=>ids.has(id)).map(([id,value])=>{const binding=clone(value);delete binding.name;return [id,binding];}));}
 async capture(){
  for(let attempt=0;attempt<4;attempt++){
   const state=await this.rpc('studio_state'),info=await this.rpc('persistence_info');
   if(state.job.status==='running')throw Error('请等待当前时刻完成后保存网络和上下文');
   if(info.pending.length)throw Error('请先核对中断操作，再保存完整网络');
   if(state.live.commit!==info.commit_id||info.node_locks_preparing)continue;
   const bindings=this.bindings(state),ids=Object.fromEntries(Object.entries(bindings).filter(([,v])=>v.session_id).map(([id,v])=>[id,v.session_id]));
   let contexts=Object.keys(ids).length?await (this.native.child?this.native.request('agent-context-capture',{bindings:ids,requireIdle:true}):this.logs.request('capture',{bindings:ids})):{};
   contexts={...contexts,...info.locked_contexts};
   try{
    await this.rpc('persistence_checkpoint',{expected_commit:state.live.commit,bindings:ids,contexts,kind:'full'});
    return {state:await this.rpc('studio_state'),bindings,contexts,base_commit:state.live.commit};
   }catch(e){if(!/changed during|Network changed/i.test(e.message))throw e;}
  }
  throw Error('网络状态仍在变化，请在当前操作完成后重试保存');
 }
 async view(p){
  const previous=await this.state(),value={...previous,version:1,document:p.dirty?clone(p.document??previous?.document):undefined,layout:clone(p.layout??{}),view:clone(p.view??{}),base_commit:p.base_commit,dirty:!!p.dirty,updatedAt:new Date().toISOString()};
  await atomic(this.file,value);return {savedAt:value.updatedAt};
 }
 async draft(p,extra={}){
  const previous=await this.state(),state=await this.rpc('studio_state'),document=p.dirty?clone(p.document):clone(state.live.document);
  const value={version:1,document,layout:clone(p.layout??previous?.layout??{}),view:clone(p.view??previous?.view??{}),base_commit:p.dirty?p.base_commit:state.live.commit,dirty:!!p.dirty,updatedAt:new Date().toISOString(),...(previous?.importToken?{importToken:previous.importToken,agents:previous.agents,contexts:previous.contexts}:{}),...extra};
  if(p.dirty){const saved=await this.rpc('studio_draft',{document:value.document,layout:value.layout,base_commit:value.base_commit,expected_version:state.draft?.version??0});value.draftVersion=saved.version;}
  await atomic(this.file,value);return value;
 }
 async save(p,{portable=false}={}){
  const previous=await this.state(),imported=!!p.importToken&&p.importToken===previous?.importToken;
  let state,agents,contexts,capturedBase;
  if(imported){state=await this.rpc('studio_state');agents=clone(previous.agents);contexts=clone(previous.contexts);}
  else{const captured=await this.capture();({state,contexts}=captured);agents=captured.bindings;capturedBase=captured.base_commit;}
  const document=clone(p.dirty?p.document:state.live.document),ids=new Set(document.network.nodes.filter(n=>n.type==='agent').map(n=>n.node_id));
  agents=Object.fromEntries(Object.entries(agents).filter(([id])=>ids.has(id)));contexts=Object.fromEntries(Object.entries(contexts).filter(([id])=>ids.has(id)));
  for(const node of document.network.nodes)node.context_cursor=contexts[node.node_id]??null;
  const result=await this.draft({...p,document,dirty:!!p.dirty,base_commit:p.base_commit===capturedBase||!p.dirty?state.live.commit:p.base_commit},{document,agents,contexts,savedAt:new Date().toISOString(),...(imported?{}:{importToken:undefined})});
  if(!portable)return {...result,live_commit:state.live.commit,contextCount:Object.keys(contexts).length};
  const prefixes=Object.keys(contexts).length?await this.logs.request('export',{contexts}):{};
  return {format:'nexarbor-network/v1',document:result.document,layout:result.layout,view:result.view,agents,contexts:prefixes,runtime:this.runtime,createdAt:result.savedAt};
 }
 async import(p){
  const bundle=p.bundle,portable=bundle?.format==='nexarbor-network/v1';
  if(!portable&&(!bundle?.network||!bundle?.files))throw Error('请选择 Nexarbor 网络文件');
  const document=clone(portable?bundle.document:bundle);
  if(document?.network?.version!==8||!Array.isArray(document.network.nodes)||!document.files||typeof document.files!=='object'||new Set(document.network.nodes.map(n=>n.node_id)).size!==document.network.nodes.length||document.network.nodes.some(n=>typeof n.node_id!=='string'||typeof n.name!=='string'||typeof n.type!=='string'||!Array.isArray(n.connections?.interfaces)||!n.modules||!n.parameters))throw Error('网络文档结构无效');
  const check=await this.rpc('studio_graph_validate',{document});
  const agents=portable?clone(bundle.agents??{}):{},prefixes=portable?bundle.contexts??{}:{},nodes=new Map(document.network.nodes.map(n=>[n.node_id,n]));
  for(const [id,binding] of Object.entries(agents))if(nodes.get(id)?.type!=='agent'||typeof binding!=='object'||(binding.session_id&&!prefixes[id]))throw Error('网络文件缺少 Agent 日志前缀：'+id);
  for(const id of Object.keys(prefixes))if(nodes.get(id)?.type!=='agent'||agents[id]?.session_id!==prefixes[id].cursor?.session_id)throw Error('日志标记与 Agent 节点不匹配：'+id);
  const contexts=Object.keys(prefixes).length?await this.logs.request('import',{contexts:prefixes}):{};
  for(const node of document.network.nodes)node.context_cursor=contexts[node.node_id]??null;
  for(const [id,cursor] of Object.entries(contexts))agents[id].session_id=cursor.session_id;
  const state=await this.rpc('studio_state'),importToken=randomUUID();
  return {...await this.draft({document,layout:portable?bundle.layout??{}:{},view:portable?bundle.view??{}:{},dirty:true,base_commit:state.live.commit},{importToken,agents,contexts}),validation:check};
 }
 async apply(p){
  const state=await this.rpc('studio_state');if(p.base_commit!==state.live.commit)throw Error('网络已经变化，请刷新后再校验并更新');
  const check=await this.rpc('studio_graph_validate',{document:p.document});if(!check.valid)return check;
  const saved=await this.state(),imported=p.importToken&&p.importToken===saved?.importToken;
  let agents,contexts,base_commit=p.base_commit;
  if(imported){agents=clone(saved.agents);contexts=clone(saved.contexts);}
  else{
   // 原生日志检查点也会推进核心版本：先协调一次，再只对游标变化重定位版本。
   const captured=await this.capture();if(!isDeepStrictEqual(graphState(state.live.document),graphState(captured.state.live.document)))throw Error('网络已经变化，请刷新后再校验并更新');base_commit=captured.state.live.commit;
   const ids=new Set(p.document.network.nodes.filter(n=>n.type==='agent').map(n=>n.node_id));agents=Object.fromEntries(Object.entries(captured.bindings).filter(([id])=>ids.has(id)));
   const source=Object.fromEntries(Object.entries(captured.contexts).filter(([id])=>ids.has(id)));
   contexts=Object.keys(source).length?await this.logs.request('fork',{contexts:source}):{};
   for(const [id,cursor] of Object.entries(contexts))agents[id].session_id=cursor.session_id;
  }
  const allowed=new Set(p.document.network.nodes.filter(n=>n.type==='agent').map(n=>n.node_id));agents=Object.fromEntries(Object.entries(agents).filter(([id])=>allowed.has(id)));contexts=Object.fromEntries(Object.entries(contexts).filter(([id])=>allowed.has(id)));
  const document=clone(p.document);for(const node of document.network.nodes)node.context_cursor=contexts[node.node_id]??null;
  const result=await this.rpc('studio_apply',{...p,document,base_commit,agent_bindings:agents});
  if(result.valid){await atomic(this.file,{version:1,document:result.document,layout:p.layout??{},view:p.view??saved?.view??{},base_commit:result.commit,dirty:false,agents,contexts,updatedAt:new Date().toISOString()});result.contextBranches=Object.keys(contexts).length;}
  return result;
 }
 request(operation,p={}){const handlers={'workspace.save':()=>this.save(p),'workspace.export':()=>this.save(p,{portable:true}),'workspace.import':()=>this.import(p),'workspace.view':()=>this.view(p),'workspace.apply':()=>this.apply(p)};if(!Object.hasOwn(handlers,operation))throw Error('未知工作区操作');return this.serial(handlers[operation]);}
}
