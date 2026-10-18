// Local development host. Electron Renderer has no OS bridge or Node privileges.
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {spawn} from 'node:child_process';import readline from 'node:readline';
import {startEditorServer} from '../framework/editor-server.js';
import {NativeRunner} from './runtime/runner.mjs';
import {OfficialToolsRunner} from './runtime/official-runner.mjs';
import {editorNode,editorNodes} from '../framework/editor-nodes.js';
import {MakerManager} from './makers/manager.mjs';
import {nativeMakerFactory} from './makers/connection.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
export async function startStudio({directory=path.join(root,'build/workbench-v3'),python=path.join(root,'.venv/Scripts/python.exe'),initialNetwork,makerRunnerFactory,components=[]}={}){
 await fs.mkdir(directory,{recursive:true});const temporary=path.join(directory,'temp');await fs.mkdir(temporary,{recursive:true});
 const profile=JSON.parse(await fs.readFile(path.join(root,'extensions/development/extension.json'),'utf8'));profile.select=[...new Set([...profile.select,...components])];
 const child=spawn(python,[path.join(root,'adapters/harness/studio/server.py'),directory],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:path.join(root,'python'),DATANET_PRODUCT_ROOT:root,DATANET_COMPONENT_ROOT:path.join(root,'extensions/development'),DATANET_COMPONENT_SELECTION:JSON.stringify(profile.select),DATANET_COMPONENT_PROFILE:'{}',...(initialNetwork?{DATANET_INITIAL_NETWORK:path.resolve(initialNetwork)}:{}),TEMP:temporary,TMP:temporary,TMPDIR:temporary}});
 let serial=0,closed=false;const pending=new Map();let diagnostics='';child.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-16000);});
 const official=new OfficialToolsRunner(directory);let officialTools=[],runtimeTools=[],toolError=null;
 const native=new NativeRunner(directory,(method,params)=>rpc(method,params));
 const lines=readline.createInterface({input:child.stdout});lines.on('line',line=>{try{const response=JSON.parse(line);if(response.notification){native.notify();return;}if(response.host_id){(response.method==='official-tool-invoke'?official.request('invoke',response.params):native.request(response.method,response.params)).then(result=>child.stdin.write(JSON.stringify({host_id:response.host_id,result})+'\n'),error=>child.stdin.write(JSON.stringify({host_id:response.host_id,error:error.message})+'\n'));return;}const p=pending.get(response.id);if(!p)return;pending.delete(response.id);clearTimeout(p.timer);response.error?p.reject(Error(response.error)):p.resolve(response.result);}catch{}});
 const fail=error=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();};
 child.on('error',fail);child.on('exit',code=>fail(Error('开发后端已退出 '+code+'\n'+diagnostics)));
 const rpc=(method,params={})=>new Promise((resolve,reject)=>{if(closed)return reject(Error('后端已关闭'));const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('开发操作超时：'+method));},method==='studio_pulse'?660000:45000);pending.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({id,method,params})+'\n');});
 const request=async(operation,params)=>{
  if(operation.startsWith('studio.agent.')){const method=operation.slice('studio.agent.'.length);if(!['status','connect','start','read','cancel'].includes(method))throw Error('未知制作操作');return makers[method](params);}
  if(operation==='studio.publish')return makers.publish(params);
  if(operation==='resource.inspect'||operation==='resource.purge'){
   if(params.kind==='tool'&&params.id.startsWith('module:')){if(operation==='resource.purge')throw Error('模块携带工具应随实现模块管理');return {canDelete:false,reason:'工具由模块提供，请到对应模块查看实现。独立书签和历史缓存保留。',ownership:'module'};}
   if(params.kind==='module')return rpc(operation==='resource.inspect'?'studio_release_delete_info':'studio_delete_release',{module:params.id,confirm:params.confirm});
   if(params.kind==='tool'&&officialTools.some(t=>t.ref===params.id)){if(operation==='resource.purge')throw Error('Harness 官方工具不可彻底删除');return {canDelete:false,reason:'Harness 官方工具属于共享安装，只可归档和恢复。',ownership:'official'};}
   throw Error('该工具尚未登记项目自有的文件来源');
  }
  if(operation.startsWith('studio.'))return rpc('studio_'+operation.slice(7).replaceAll('.','_'),params);
  if(operation==='module.frontend')return rpc('studio_frontend',params);
  if(['state','draft','apply','view'].includes(operation))return rpc('studio_'+operation,params);
  if(operation==='catalog'){
   const catalog=await rpc('studio_catalog');const presets=[];const moduleTools=Object.values(catalog.library).flatMap(m=>(m.manifest.agent_tools??[]).map(t=>{const operation=m.manifest.operations.find(o=>o.name===t.operation);return {ref:'module:'+m.id+'/'+t.id,name:t.name,description:t.description,parameters:operation.parameters,channels:operation.channels,provider:'module',module:m.id,requires:[m.id],tools:[],display_folder:m.origin_kind==='tool'?m.display_folder:undefined};}));
   return {modules:Object.fromEntries(Object.values(catalog.library).map(m=>[m.id,{label:m.name??m.manifest.name??m.manifest.frontend?.title??m.id,description:m.manifest.description??m.manifest.config_schema.description??('已发布 · '+m.version),preview:m.manifest.preview,requires:m.manifest.requires??[],tools:(m.manifest.agent_tools??[]).map(t=>'module:'+m.id+'/'+t.id),version:m.version,node_types:m.manifest.node_types,schema:m.manifest.config_schema,state_schema:m.manifest.state_schema,frontend:m.manifest.frontend,defaults:{config:m.defaults??{},state:m.mount_defaults?.state??{},access:m.mount_defaults?.access??{strength:0,channels:[]}},owner:'组件库',display_folder:m.origin_kind==='tool'?undefined:m.display_folder}])),nodes:editorNodes(),presets,studio:true,tools:[...officialTools,...runtimeTools,...moduleTools],toolError,contract:catalog.contract};
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
   const node=editorNode(kind,options.id,options.name||options.id);
   doc.network.nodes.push(node);return doc;
  }
  if(operation==='connect'){
   const doc=structuredClone(params.document),c=params.connection,meta={channels:c.channels,threshold:c.threshold,multiplier:c.multiplier,attributes:c.attributes??{}};
   const add=(from,to)=>doc.network.nodes.find(n=>n.node_id===from).connections.interfaces.push({target_node_id:to,metadata:meta});add(c.source,c.target);if(c.reciprocal)add(c.target,c.source);return doc;
  }
  throw Error('此开发工作台未启用该业务入口：'+operation);
 };
 await rpc('ping');
 if(components.includes('capabilities/runtime_ports'))runtimeTools=(await rpc('runtime_catalog')).map(t=>({...t,owner:'可选宿主端口'}));
 const makers=new MakerManager(directory,rpc,{runnerFactory:makerRunnerFactory??((p,callback)=>nativeMakerFactory({...p,directory},callback))});await makers.initialize();
 try{officialTools=await official.start();await rpc('official_register',{tools:officialTools});officialTools=officialTools.map(t=>({...t,ref:'harness:'+t.name,provider:'harness'}));}catch(error){toolError=error.message;await official.close();}
 const server=await startEditorServer({web:path.join(root,'extensions/editor/capabilities/network_editor/web'),directory,request,chat:(operation,p)=>rpc(operation==='chat.read'?'executor_read':'executor_run',p),recover:()=>{throw Error('请先保存完整开发恢复点');}});
 return {...server,directory,request,rpc:(method,p={})=>method.startsWith('studio_agent_')?request('studio.agent.'+method.slice(13),p):method==='studio_publish'?makers.publish(p):rpc(method,p),async close(){if(closed)return;await server.close();await makers.close();await native.close();await official.close();closed=true;child.stdin.end();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});fail(Error('开发后端已关闭'));}};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=await startStudio({directory:process.argv[2]});console.log(JSON.stringify({connection_file:path.join(value.directory,'editor-connection.json')}));
 const close=()=>value.close().finally(()=>process.exit());process.once('SIGTERM',close);process.once('SIGINT',close);
}
