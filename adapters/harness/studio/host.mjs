import {studioRpcTimeout} from './rpc-timeouts.mjs';
import {SkillResources} from './skills.mjs';
import {assembleResources} from '../../../shared/graph/resource-assembly.js';
import {ExternalTextFiles} from './external-text.mjs';
import {ModelConnections} from './model-connections.mjs';
import {pythonExecutable} from './runtime-paths.mjs';
import {Project,readProjectBundle,readProjectRuntime} from './project.mjs';import {registerProjectDirectory} from '../framework/project-directory.js';
// Local development host. Electron Renderer has no OS bridge or Node privileges.
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {spawn} from 'node:child_process';import readline from 'node:readline';
import {startEditorServer} from '../framework/editor-server.js';
import {Advisors} from './makers/advisors.mjs';
import {WorkspaceFiles} from './workspace-files.mjs';
import {NativeRunner} from './runtime/runner.mjs';
import {OfficialToolsRunner} from './runtime/official-runner.mjs';
import {editorNode,editorNodes} from '../framework/editor-nodes.js';
import {MakerManager} from './makers/manager.mjs';
import {nativeMakerFactory} from './makers/connection.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
export async function startStudio({directory=path.join(root,'build/workbench-v3'),python,initialNetwork,makerRunnerFactory,application,components=[],templates=[],onOpenNetwork,onImportNetwork,onOpenProject,onCreateProject,onRevealFile,projectDirectory=directory,applicationPresets,startupWarnings=[],onProgress=()=>{},modelDirectory,modelPolicy,onModelSelection,onOpenText,onChooseText}={}){
 python??=await pythonExecutable(root);
 registerProjectDirectory(directory,projectDirectory);
 if(!application){const savedRuntime=await readProjectRuntime(projectDirectory);if(savedRuntime){components=[...new Set([...components,...(savedRuntime.components??[])])];if(!templates.length)templates=savedRuntime.templates??[];application=savedRuntime.application;}}
 let restoreBundle=null;try{await fs.access(path.join(directory,'checkpoints.sqlite3'));}catch{if(!initialNetwork)restoreBundle=await readProjectBundle(projectDirectory);}
 if(restoreBundle){components=[...new Set([...components,...(restoreBundle.runtime.components??[])])];templates=restoreBundle.runtime.templates??templates;application=restoreBundle.runtime.application??application;await fs.mkdir(directory,{recursive:true});initialNetwork=path.join(directory,'project-bootstrap.json');await fs.writeFile(initialNetwork,JSON.stringify({network:{version:8,nodes:restoreBundle.document.network.nodes.map(n=>editorNode('node',n.node_id,n.name)),signals:{},delegations:[]},files:{}}));}
 await fs.mkdir(directory,{recursive:true});const temporary=path.join(directory,'temp');await fs.mkdir(temporary,{recursive:true});
 const profile=JSON.parse(await fs.readFile(path.join(root,'extensions/development/extension.json'),'utf8'));profile.select=[...new Set([...profile.select,...components])];
 onProgress('正在恢复网络…');const startTime=performance.now(),timings={};const mark=name=>{timings[name]=Math.round(performance.now()-startTime);};
 const child=spawn(python,[path.join(root,'adapters/harness/studio/server.py'),directory],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',DATANET_DEFER_VECTORS:'1',PYTHONPATH:path.join(root,'python'),DATANET_PRODUCT_ROOT:root,DATANET_COMPONENT_ROOT:path.join(root,'extensions/development'),DATANET_COMPONENT_SELECTION:JSON.stringify(profile.select),DATANET_COMPONENT_PROFILE:'{}',DATANET_PROJECT_DIRECTORY:projectDirectory,DATANET_PROJECT_RESOURCES_ONLY:path.resolve(projectDirectory)!==path.resolve(directory)?'1':'0',...(initialNetwork?{DATANET_INITIAL_NETWORK:path.resolve(initialNetwork)}:{}),TEMP:temporary,TMP:temporary,TMPDIR:temporary}});
 let serial=0,closed=false;const pending=new Map();let diagnostics='';child.stderr.on('data',chunk=>{diagnostics=(diagnostics+chunk).slice(-16000);});
 const official=new OfficialToolsRunner(directory,{cwd:projectDirectory});let officialTools=[],runtimeTools=[],toolError=null;
 const project=new Project(projectDirectory,directory,(method,p)=>rpc(method,p));
 const skills=new SkillResources(project,(method,p)=>rpc(method,p));project.skillResources=skills;
 const modelConnections=new ModelConnections({project,directory,configDirectory:modelDirectory,modelPolicy,onModelSelection});
 const externalText=new ExternalTextFiles({directory,project,onOpen:onOpenText,onChoose:onChooseText,onReveal:onRevealFile,preferences:()=>modelConnections.preferences()});
 const native=new NativeRunner(directory,async(method,params)=>{const view=await rpc(method,params);if(method==='executor_prepare'){view.skill_bundles=[];view.skill_errors=[];for(const id of view.skills??[])try{view.skill_bundles.push(...await skills.bundles([id]));}catch(error){view.skill_errors.push({id,error:error.message});}}return view;},{modelResolver:choice=>modelConnections.runtime(choice,'project')});
 const workspaceFiles=new WorkspaceFiles(directory,(method,p)=>rpc(method,p),native,{components,templates});
 const lines=readline.createInterface({input:child.stdout});lines.on('line',line=>{try{const response=JSON.parse(line);if(response.notification){native.notify();return;}if(response.host_id){(response.method.startsWith('network-admin-')?adminRequest(response.method.slice(14),response.params):response.method==='official-tool-invoke'?official.request('invoke',response.params):native.request(response.method,response.params)).then(result=>child.stdin.write(JSON.stringify({host_id:response.host_id,result})+'\n'),error=>child.stdin.write(JSON.stringify({host_id:response.host_id,error:error.message})+'\n'));return;}const p=pending.get(response.id);if(!p)return;pending.delete(response.id);clearTimeout(p.timer);Object.hasOwn(response,'error')?p.reject(Error(response.error||'宿主调用失败，未提供错误说明')):p.resolve(response.result);}catch{}});
 const fail=error=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(error);}pending.clear();};
 child.stdin.on('error',fail);child.on('error',fail);child.on('exit',code=>fail(Error('开发后端已退出 '+code+'\n'+diagnostics)));
 const rpc=(method,params={})=>new Promise((resolve,reject)=>{if(closed||child.exitCode!==null)return reject(Error('后端已关闭'));const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error('开发操作超时：'+method));},studioRpcTimeout(method,params));pending.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({id,method,params})+'\n');});
 let officialLoading=null,officialState='idle',officialNeeded=false;
 const loadOfficial=()=>officialLoading??=(async()=>{officialState='loading';try{const tools=await official.start(),contracts=await official.request('contracts');await rpc('official_register',{tools,contracts});officialTools=tools.map(t=>({...t,ref:'harness:'+t.name,provider:'harness'}));officialState='ready';toolError=null;return officialTools;}catch(error){officialState='error';toolError=error.message;officialLoading=null;await official.close();throw error;}})();
 let openingNetwork=false;
 const request=async(operation,params)=>{
  if(operation?.startsWith('text.external.'))return externalText.request(operation,params);
  if(operation?.startsWith('models.')||operation?.startsWith('preferences.'))return modelConnections.request(operation,params);
  if(operation==='skills.import'){const value=await project.serial(async()=>{const imported=await skills.import(params.files);await project.installNow('skill',imported.id);return imported;});await rpc('studio_project_modules');return value;}
  if(operation==='skills.read'){const value=await skills.read(params.id);return {manifest:value.manifest,content:value.content,files:Object.keys(value.files),local:value.local};}
  if(operation==='project.restore')return project.restore(params.commit);
  if(operation==='project.info')return project.info();
  if(operation==='project.install'){const value=await project.install(params.kind,params.id);await rpc('studio_project_modules');return value;}
  if(operation==='project.new'){if(!onCreateProject)throw Error('请从桌面客户端新建项目文件夹');setTimeout(()=>onCreateProject(),50);return {opening:true};}
  if(operation==='project.open'){if(!onOpenProject)throw Error('请从桌面客户端选择项目文件夹');setTimeout(()=>onOpenProject(),50);return {opening:true};}
  if(operation==='file.reveal'){if(!onRevealFile)throw Error('当前连接未启用文件定位');let requested=params.path.replace(/:(\d+)(?::\d+)?$/,'');const file=await fs.realpath(path.resolve(projectDirectory,requested));const allowed=[await fs.realpath(projectDirectory),await fs.realpath(root)];if(!allowed.some(base=>file===base||file.startsWith(base+path.sep)))throw Error('文件不在当前项目或制作后端内');return onRevealFile(file);}
  if(operation==='state')return {startupWarnings,...await rpc('studio_state'),...(params.resume!==false?{workspace:await workspaceFiles.state()}:{})};
  if(['workspace.commit','workspace.export','workspace.save','apply'].includes(operation)){const before=params.document??(await rpc('studio_state')).live.document,document=await externalText.sync(before);params={...params,document,...(operation==='apply'?{}:{dirty:!!params.dirty||JSON.stringify(before.files)!==JSON.stringify(document.files)})};}
  if(operation==='workspace.import.local')return workspaceFiles.request('workspace.import',params);
  if(operation==='workspace.import'&&onImportNetwork){setTimeout(()=>Promise.resolve(onImportNetwork(params.bundle)).catch(()=>{}),100);return {opening:true};}
  if(operation==='workspace.commit')await project.ensureResources(params.dirty?params.document:(await rpc('studio_state')).live.document,{allowMissing:true});
  if(operation.startsWith('workspace.'))return workspaceFiles.request(operation,params);
  if(operation.startsWith('advice.'))return makers.advisor.request(operation.slice(7),params);
  if(operation==='startup.status')return {timings,officialState,toolError,vector:await rpc('studio_vector_status')};
  if(operation==='apply'){await project.ensureResources(params.document,{allowMissing:true});const catalog=await request('catalog',{});for(const node of params.document.network.nodes)for(const id of node.skills??[])try{params.document=assembleResources(params.document,node.node_id,[{kind:'skill',id}],catalog);}catch{}const needed=params.document.network.nodes.some(n=>(n.offered_tools??[]).some(o=>o.ref.startsWith('harness:')));if(needed)await loadOfficial();const result=await workspaceFiles.request('workspace.apply',params);officialNeeded=needed;return result;}
  if(officialNeeded&&['module.call','tools.visit','run','view'].includes(operation))await loadOfficial();
  if(operation==='preset.open'){
   if(!onOpenNetwork)throw Error('请通过 Nexarbor 桌面客户端打开完整网络');
   if(openingNetwork)throw Error('正在打开完整网络');
   const {storedNetworks}=await import('../framework/stored-networks.js'),preset=await storedNetworks(directory).load(params.id);
   if(preset.storageKind!=='network')throw Error('请选择完整网络；零件预设可拖入当前网络使用');
   openingNetwork=true;setTimeout(()=>Promise.resolve(onOpenNetwork(preset)).catch(()=>{}).finally(()=>{openingNetwork=false;}),150);
   return {opening:true,name:preset.name};
  }
  if(operation.startsWith('studio.agent.')){const method=operation.slice('studio.agent.'.length);if(!['status','connect','start','read','cancel'].includes(method))throw Error('未知制作操作');return makers[method](params);}
  if(operation==='studio.revision'){const work=await rpc('studio_revision',params);work.git=await project.branch(work);return work;}
  if(['studio.save','studio.create','studio.delete_file','studio.copy_current'].includes(operation)){const work=await rpc('studio_'+operation.slice(7),params);work.git=await project.branch(work.files?work:await rpc('studio_read',{id:params.id}));return work;}
  if(operation==='studio.publish')return makers.publish(params);
  if(operation==='resource.inspect'||operation==='resource.purge'){
   if(params.kind==='tool'&&runtimeTools.some(t=>t.ref===params.id)){if(operation==='resource.purge')throw Error('官方宿主端口不可删除');return {canDelete:false,reason:'官方宿主能力只可归档和恢复。',ownership:'official'};}
   if(params.kind==='tool'&&params.id.startsWith('module:')){if(operation==='resource.purge')throw Error('模块携带工具应随实现模块管理');return {canDelete:false,reason:'工具由模块提供，请到对应模块查看实现。独立书签和历史缓存保留。',ownership:'module'};}
   if(params.kind==='skill'){if(operation==='resource.purge')throw Error('Skill 请在项目的 skills 目录中管理；客户端支持归档和恢复');return {canDelete:false,reason:'Skill 文件在项目 skills 目录内，由 Git 保留版本；可归档和恢复。',ownership:'project'};}
   if(params.kind==='module')return rpc(operation==='resource.inspect'?'studio_release_delete_info':'studio_delete_release',{module:params.id,confirm:params.confirm});
   if(params.kind==='tool'&&officialTools.some(t=>t.ref===params.id)){if(operation==='resource.purge')throw Error('Harness 官方工具不可彻底删除');return {canDelete:false,reason:'Harness 官方工具属于共享安装，只可归档和恢复。',ownership:'official'};}
   throw Error('该工具尚未登记项目自有的文件来源');
  }
  if(operation.startsWith('studio.'))return rpc('studio_'+operation.slice(7).replaceAll('.','_'),params);
  if(operation==='module.frontend')return rpc('studio_frontend',params);
  if(operation==='module.preview')return rpc('studio_frontend_preview',params);
  if(['state','draft','apply','view'].includes(operation))return rpc('studio_'+operation,params);
  if(operation==='catalog'){
   if(params.official)await loadOfficial();
   const catalog=await rpc('studio_catalog'),local=await project.localResources(catalog),skillCatalog=await skills.catalog();local.skills=Object.fromEntries(Object.entries(skillCatalog).filter(([,s])=>s.local));const presets=[];const moduleTools=Object.values(catalog.library).flatMap(m=>(m.manifest.agent_tools??[]).map(t=>{const operation=m.manifest.operations.find(o=>o.name===t.operation);return {ref:'module:'+m.id+'/'+t.id,name:t.name,description:t.description,parameters:operation.parameters,channels:operation.channels,provider:'module',module:m.id,requires:[m.id],tools:[],display_folder:m.origin_kind==='tool'?m.display_folder:undefined};}));
   return {project:{path:projectDirectory,resourceSource:path.resolve(projectDirectory)!==path.resolve(directory)?'project':'library'},localResources:local,skills:skillCatalog,modules:Object.fromEntries(Object.values(catalog.library).map(m=>[m.id,{available:m.available,unavailableReason:m.unavailableReason,local:!!local.modules[m.id],label:m.name??m.manifest.name??m.manifest.frontend?.title??m.id,description:m.manifest.description??m.manifest.config_schema.description??('已发布 · '+m.version),preview:m.manifest.preview,requires:m.manifest.requires??[],tools:(m.manifest.agent_tools??[]).map(t=>'module:'+m.id+'/'+t.id),version:m.version,node_types:m.manifest.node_types,schema:m.manifest.config_schema,state_schema:m.manifest.state_schema,frontend:m.manifest.frontend,defaults:{config:m.defaults??{},state:m.mount_defaults?.state??{},access:m.mount_defaults?.access??{strength:0,channels:[]}},owner:'组件库',display_folder:m.origin_kind==='tool'?undefined:m.display_folder}])),nodes:[...editorNodes(),...await rpc('data_templates')],presets,toolsReady:officialState==='ready',canOpenNetworks:!!onOpenNetwork,studio:true,tools:[...officialTools,...runtimeTools,...moduleTools],toolError,contract:catalog.contract};
  }
  if(operation==='preset'){
   if(!/^[a-zA-Z0-9_-]+$/.test(params.id))throw Error('Invalid preset');
   const directory=path.join(root,'configs',params.id),profile=JSON.parse(await fs.readFile(path.join(directory,'profile.json'),'utf8')),file=path.resolve(directory,profile.network);
   if(!file.startsWith(directory+path.sep))throw Error('Preset escapes configuration directory');
   return JSON.parse(await fs.readFile(file,'utf8'));
  }
  if(operation==='data.preview')return rpc('data_preview',params);
  if(operation==='preset.expand')return rpc('preset_expand',params);
  if(operation==='data.clear')return rpc('data_clear',params);
  if(operation==='module.call')return rpc('module_access',params);
  if(operation==='tools.visit')return rpc('executor_visit',params);
  if(operation==='run')return rpc('studio_pulse',params);
  if(operation==='checkpoint')return rpc('save',{full:true});
  if(operation==='validate')return rpc('studio_graph_validate',params);
  if(operation==='template'){
   const {kind,options,document}=params;if(!['node','text_file','agent','pulse','network_admin'].includes(kind))throw Error('请在组件工作室建立小镇实验场，再装配已发布组件');
   const doc=structuredClone(document);if(doc.network.nodes.some(n=>n.node_id===options.id))throw Error('节点编号已存在');
   const node=editorNode(kind,options.id,options.name||options.id);
   doc.network.nodes.push(node);return doc;
  }
  if(operation==='connect'){
   const doc=structuredClone(params.document),c=params.connection,meta={channels:c.channels,threshold:c.threshold,multiplier:c.multiplier,attributes:{...c.attributes,...(c.channel_mode?{channel_mode:c.channel_mode}:{})}};
   const add=(from,to)=>doc.network.nodes.find(n=>n.node_id===from).connections.interfaces.push({target_node_id:to,metadata:meta});add(c.source,c.target);if(c.reciprocal)add(c.target,c.source);return doc;
  }
  throw Error('此开发工作台未启用该业务入口：'+operation);
 };
 let closeJob;
 const close=()=>closeJob??=(async()=>{await server?.close();await makers?.close();await native.close();await workspaceFiles.close();await official.close();if(child.exitCode===null)await rpc('studio_vector_close').catch(()=>{});closed=true;child.stdin.end();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},10000);child.once('exit',()=>{clearTimeout(timer);resolve();});});fail(Error('开发后端已关闭'));})();
 let server,makers,adminRequest;
 try{
 await rpc('ping');await project.initialize();await rpc('studio_project_modules');mark('pythonReady');onProgress('正在准备画布…');officialNeeded=await rpc('studio_official_needed');mark('presetsReady');
 if(components.includes('capabilities/runtime_ports'))runtimeTools=(await rpc('runtime_catalog')).map(t=>({...t,owner:'可选宿主端口'}));
 if(components.includes('capabilities/template_instantiation')){if(templates.length)await rpc('templates_register',{templates});runtimeTools.push(...(await rpc('templates_catalog')).map(t=>({...t,owner:'固定模板端口'})));}
 workspaceFiles.runtime={components,templates,application};workspaceFiles.project=project;
 if(restoreBundle){
  if(restoreBundle.document.network.nodes.some(node=>(node.offered_tools??[]).some(tool=>tool.ref.startsWith('harness:'))))await loadOfficial();
  const staged=await workspaceFiles.request('workspace.import',{bundle:restoreBundle});
  if(!restoreBundle.dirty){if(!staged.validation.valid)throw Error('项目网络无法载入：'+JSON.stringify(staged.validation.errors??staged.validation));await workspaceFiles.request('workspace.apply',{...staged,base_commit:staged.base_commit});}
 }
 makers=new MakerManager(directory,rpc,{runnerFactory:makerRunnerFactory??((p,callback)=>nativeMakerFactory({...p,directory,modelResolver:(choice,meta)=>modelConnections.runtime(choice,meta.kind==='network'?'network':'component')},callback))});await makers.initialize();makers.project=project;makers.advisor=new Advisors(directory,rpc,makers,()=>request('catalog',{}));
 adminRequest=(method,p)=>{if(method==='start')return makers.start(p);if(method==='status')return makers.read(p);if(method==='cancel')return makers.cancel(p);throw Error('未知局部管理员宿主操作');};
 // 原生 Agent 与制作运行器已有按需启动；官方工具同样不阻塞画布。
 server=await startEditorServer({web:path.join(root,'extensions/editor/capabilities/network_editor/web'),directory,runtime:{components,templates},request,chat:async(operation,p)=>{if(operation!=='chat.read'&&officialNeeded)await loadOfficial();return rpc(operation==='chat.read'?'executor_read':'executor_run',p);},recover:()=>{throw Error('请先保存完整开发恢复点');}});
 mark('ready');await fs.writeFile(path.join(directory,'startup-timings.json'),JSON.stringify(timings,null,2));
 return {...server,directory,timings,request,rpc:(method,p={})=>method.startsWith('studio_agent_')?request('studio.agent.'+method.slice(13),p):method==='studio_publish'?makers.publish(p):rpc(method,p),close};
 }catch(error){await close().catch(()=>{});throw error;}
}
export async function startStudioProfile(file,overrides={}){
 const base=path.dirname(path.resolve(file)),profile=JSON.parse(await fs.readFile(file,'utf8'));
 if(profile.project){const projectDirectory=path.resolve(base,profile.project);return startStudio({directory:path.join(projectDirectory,'.nexarbor/runs/main'),projectDirectory,...overrides});}
 const directory=path.resolve(base,profile.runtime_directory??'runtime'),relative=path.relative(path.join(root,'build'),directory);
 if(!overrides.directory&&(!relative||relative.startsWith('..')||path.isAbsolute(relative)))throw Error('应用运行目录须位于项目 build 内；其他目录请显式指定 --workspace');
 return startStudio({directory,application:path.dirname(base)===path.join(root,'configs')?path.basename(base):undefined,initialNetwork:profile.network?path.resolve(base,profile.network):undefined,components:profile.components??[],templates:profile.templates?JSON.parse(await fs.readFile(path.resolve(base,profile.templates),'utf8')):[],...overrides});
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=process.argv[2]==='--profile'?await startStudioProfile(process.argv[3]):await startStudio({directory:process.argv[2]});console.log(JSON.stringify({connection_file:path.join(value.directory,'editor-connection.json')}));
 const close=()=>value.close().finally(()=>process.exit());process.once('SIGTERM',close);process.once('SIGINT',close);
}
