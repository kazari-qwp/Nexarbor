// Local development host. Electron Renderer has no OS bridge or Node privileges.
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {spawn} from 'node:child_process';import readline from 'node:readline';
import {startEditorServer} from '../framework/editor-server.js';
import {NativeRunner} from './runtime/runner.mjs';
import {OfficialToolsRunner} from './runtime/official-runner.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
export async function startStudio({directory=path.join(root,'build/workbench-v3'),python=path.join(root,'.venv/Scripts/python.exe'),initialNetwork}={}){
 await fs.mkdir(directory,{recursive:true});const temporary=path.join(directory,'temp');await fs.mkdir(temporary,{recursive:true});
 const profile=JSON.parse(await fs.readFile(path.join(root,'extensions/development/extension.json'),'utf8'));
 const child=spawn(python,[path.join(root,'adapters/harness/studio/server.py'),directory],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:path.join(root,'python'),DATANET_PRODUCT_ROOT:root,DATANET_COMPONENT_ROOT:path.join(root,'extensions/development'),DATANET_COMPONENT_SELECTION:JSON.stringify(profile.select),DATANET_COMPONENT_PROFILE:'{}',...(initialNetwork?{DATANET_INITIAL_NETWORK:path.resolve(initialNetwork)}:{}),TEMP:temporary,TMP:temporary,TMPDIR:temporary}});
 let serial=0,closed=false;const pending=new Map();let diagnostics='';child.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-16000);});
 const official=new OfficialToolsRunner(directory);let officialTools=[],toolError=null;
 const native=new NativeRunner(directory,(method,params)=>rpc(method,params));
 const lines=readline.createInterface({input:child.stdout});lines.on('line',line=>{try{const response=JSON.parse(line);if(response.notification){native.notify();return;}if(response.host_id){(response.method==='official-tool-invoke'?official.request('invoke',response.params):native.request(response.method,response.params)).then(result=>child.stdin.write(JSON.stringify({host_id:response.host_id,result})+'\n'),error=>child.stdin.write(JSON.stringify({host_id:response.host_id,error:error.message})+'\n'));return;}const p=pending.get(response.id);if(!p)return;pending.delete(response.id);clearTimeout(p.timer);response.error?p.reject(Error(response.error)):p.resolve(response.result);}catch{}});
 const fail=error=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();};
 child.on('error',fail);child.on('exit',code=>fail(Error('开发后端已退出 '+code+'\n'+diagnostics)));
 const rpc=(method,params={})=>new Promise((resolve,reject)=>{if(closed)return reject(Error('后端已关闭'));const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('开发操作超时：'+method));},method==='studio_pulse'?660000:45000);pending.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({id,method,params})+'\n');});
 const request=async(operation,params)=>{
  if(operation.startsWith('studio.'))return rpc('studio_'+operation.slice(7).replaceAll('.','_'),params);
  if(operation==='module.frontend')return rpc('studio_frontend',params);
  if(['state','draft','apply','view'].includes(operation))return rpc('studio_'+operation,params);
  if(operation==='catalog'){
   const catalog=await rpc('studio_catalog');const presets=[];
   return {modules:Object.fromEntries(Object.values(catalog.library).map(m=>[m.id,{label:m.manifest.frontend?.title??m.id,description:m.manifest.description??m.manifest.config_schema.description??('已发布 · '+m.version),preview:m.manifest.preview,version:m.version,node_types:m.manifest.node_types,schema:m.manifest.config_schema,frontend:m.manifest.frontend,defaults:{config:m.defaults??{},state:m.mount_defaults?.state??{},access:m.mount_defaults?.access??{strength:0,channels:[]}},owner:'组件库'}])),presets,studio:true,tools:officialTools,toolError,contract:catalog.contract};
  }
  if(operation==='preset'){
   if(!/^[a-zA-Z0-9_-]+$/.test(params.id))throw Error('Invalid preset');
   const directory=path.join(root,'configs',params.id),profile=JSON.parse(await fs.readFile(path.join(directory,'profile.json'),'utf8')),file=path.resolve(directory,profile.network);
   if(!file.startsWith(directory+path.sep))throw Error('Preset escapes configuration directory');
   return JSON.parse(await fs.readFile(file,'utf8'));
  }
  if(operation==='tools.visit')return rpc('executor_visit',params);
  if(operation==='run')return rpc('studio_pulse',params);
  if(operation==='checkpoint')return rpc('save',{full:true});
  if(operation==='validate')return rpc('studio_graph_validate',params);
  if(operation==='template'){
   const {kind,options,document}=params;if(!['node','text_file','agent','pulse'].includes(kind))throw Error('请在组件工作室建立小镇实验场，再装配已发布组件');
   const doc=structuredClone(document);if(doc.network.nodes.some(n=>n.node_id===options.id))throw Error('节点编号已存在');
   const node={type:kind,node_id:options.id,name:options.name||options.id,description:'',management_parent_id:'root',divergence:-1,data_kind:null,parameters:kind==='agent'||kind==='text_file'?{file_path:'data/'+Date.now()+'.md'}:kind==='pulse'?{channels:['world.tick'],strength:4}:{},connections:{interfaces:[]},agent:null,modules:{},offered_tools:[],toolboxes:[],expose:[],execution:null,inputs:null};
   doc.network.nodes.push(node);return doc;
  }
  if(operation==='connect'){
   const doc=structuredClone(params.document),c=params.connection,meta={channels:c.channels,threshold:c.threshold,multiplier:c.multiplier,attributes:c.attributes??{}};
   const add=(from,to)=>doc.network.nodes.find(n=>n.node_id===from).connections.interfaces.push({target_node_id:to,metadata:meta});add(c.source,c.target);if(c.reciprocal)add(c.target,c.source);return doc;
  }
  throw Error('此开发工作台未启用该业务入口：'+operation);
 };
 await rpc('ping');
 try{officialTools=await official.start();await rpc('official_register',{tools:officialTools});officialTools=officialTools.map(t=>({...t,ref:'harness:'+t.name,provider:'harness'}));}catch(error){toolError=error.message;await official.close();}
 const server=await startEditorServer({web:path.join(root,'extensions/editor/capabilities/network_editor/web'),directory,request,chat:(operation,p)=>rpc(operation==='chat.read'?'executor_read':'executor_run',p),recover:()=>{throw Error('请先保存完整开发恢复点');}});
 return {...server,directory,rpc,async close(){if(closed)return;await server.close();await native.close();await official.close();closed=true;child.stdin.end();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});fail(Error('开发后端已关闭'));}};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=await startStudio({directory:process.argv[2]});console.log(JSON.stringify({connection_file:path.join(value.directory,'editor-connection.json')}));
 const close=()=>value.close().finally(()=>process.exit());process.once('SIGTERM',close);process.once('SIGINT',close);
}
