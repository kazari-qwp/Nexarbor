// Local development host. Electron Renderer has no OS bridge or Node privileges.
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {spawn} from 'node:child_process';import readline from 'node:readline';
import {startEditorServer} from '../framework/editor-server.js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
export async function startStudio({directory=path.join(root,'build/workbench'),python=path.join(root,'.venv/Scripts/python.exe')}={}){
 await fs.mkdir(directory,{recursive:true});const temporary=path.join(directory,'temp');await fs.mkdir(temporary,{recursive:true});
 const child=spawn(python,[path.join(root,'adapters/harness/studio/server.py'),directory],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:path.join(root,'python'),DATANET_PRODUCT_ROOT:root,DATANET_COMPONENT_ROOT:path.join(root,'extensions/development'),DATANET_COMPONENT_SELECTION:'["capabilities/component_studio"]',DATANET_COMPONENT_PROFILE:'{}',TEMP:temporary,TMP:temporary,TMPDIR:temporary}});
 let serial=0,closed=false;const pending=new Map();let diagnostics='';child.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-16000);});
 const lines=readline.createInterface({input:child.stdout});lines.on('line',line=>{try{const response=JSON.parse(line),p=pending.get(response.id);if(!p)return;pending.delete(response.id);clearTimeout(p.timer);response.error?p.reject(Error(response.error)):p.resolve(response.result);}catch{}});
 const fail=error=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();};
 child.on('error',fail);child.on('exit',code=>fail(Error('开发后端已退出 '+code+'\n'+diagnostics)));
 const rpc=(method,params={})=>new Promise((resolve,reject)=>{if(closed)return reject(Error('后端已关闭'));const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('开发操作超时：'+method));},45000);pending.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({id,method,params})+'\n');});
 const request=async(operation,params)=>{
  if(operation.startsWith('studio.'))return rpc('studio_'+operation.slice(7).replaceAll('.','_'),params);
  if(['state','draft','apply','view'].includes(operation))return rpc('studio_'+operation,params);
  if(operation==='catalog'){
   const catalog=await rpc('studio_catalog');return {modules:Object.fromEntries(Object.values(catalog.library).map(m=>[m.id,{label:m.id,description:'已发布 · '+m.version,schema:m.manifest.config_schema,defaults:{config:m.defaults??{},state:{}},owner:'组件库'}])),presets:[],studio:true};
  }
  if(operation==='run')return rpc('studio_pulse',params);
  if(operation==='checkpoint')return rpc('save',{full:true});
  if(operation==='validate')return rpc('studio_graph_validate',params);
  if(operation==='template'){
   const {kind,options,document}=params;if(!['node','text_file','agent','pulse'].includes(kind))throw Error('请在组件工作室建立小镇实验场，再装配已发布组件');
   const doc=structuredClone(document);if(doc.network.nodes.some(n=>n.node_id===options.id))throw Error('节点编号已存在');
   const node={type:kind,node_id:options.id,name:options.name||options.id,description:'',management_parent_id:'root',divergence:-1,data_kind:null,parameters:kind==='agent'||kind==='text_file'?{file_path:'data/'+Date.now()+'.md'}:kind==='pulse'?{channels:['world.tick'],strength:4}:{},connections:{interfaces:[]},agent:null,modules:{},toolboxes:[],expose:[],execution:null,inputs:null};
   doc.network.nodes.push(node);return doc;
  }
  if(operation==='connect'){
   const doc=structuredClone(params.document),c=params.connection,meta={channels:c.channels,threshold:c.threshold,multiplier:c.multiplier,attributes:{}};
   const add=(from,to)=>doc.network.nodes.find(n=>n.node_id===from).connections.interfaces.push({target_node_id:to,metadata:meta});add(c.source,c.target);if(c.reciprocal)add(c.target,c.source);return doc;
  }
  throw Error('此开发工作台未启用该业务入口：'+operation);
 };
 await rpc('ping');
 const server=await startEditorServer({web:path.join(root,'extensions/editor/capabilities/network_editor/web'),directory,request,chat:()=>{throw Error('此小镇实验场尚未绑定居民模型；组件制作会话在组件工作室中打开。');},recover:()=>{throw Error('请先保存完整开发恢复点');}});
 return {...server,directory,rpc,async close(){if(closed)return;await server.close();closed=true;child.stdin.end();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});fail(Error('开发后端已关闭'));}};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=await startStudio({directory:process.argv[2]});console.log(JSON.stringify({connection_file:path.join(value.directory,'editor-connection.json')}));
 const close=()=>value.close().finally(()=>process.exit());process.once('SIGTERM',close);process.once('SIGINT',close);
}
