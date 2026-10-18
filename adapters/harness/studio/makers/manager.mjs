import fs from 'node:fs/promises';import path from 'node:path';import {createHash,randomUUID} from 'node:crypto';
import {makerTools} from './tools.mjs';import {editorNode} from '../../framework/editor-nodes.js';import {storedNetworks} from '../../framework/stored-networks.js';
import {editorLibrary} from '../../framework/editor-library.js';
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex'),pause=ms=>new Promise(r=>setTimeout(r,ms));
export class MakerManager{
 constructor(directory,rpc,{runnerFactory}={}){this.directory=directory;this.rpc=rpc;this.runnerFactory=runnerFactory;this.jobs=new Map();this.sessions=new Map();this.root=path.join(directory,'studio');this.connected=false;this.closed=false;}
 async initialize(){try{for(const [id,s] of Object.entries(JSON.parse(await fs.readFile(path.join(this.root,'native-maker-sessions.json'),'utf8'))))this.sessions.set(id,s);}catch(e){if(e.code!=='ENOENT')throw e;}}
 status(){return {connected:this.connected,authority:'本机 Harness SDK',jobs:[...this.jobs.values()].map(j=>this.public(j)),backend:'native-sdk'};}
 public(job){const {instructions,...value}=job;return structuredClone(value);}
 async connect(p={}){if(!this.runnerFactory)throw Error('制作运行器尚未配置');if(this.runner)return {connected:true,authority:'本机 Harness SDK'};this.runner=await this.runnerFactory(p,(method,args)=>this.tool(args));await this.runner.start();this.connected=true;return {connected:true,authority:'本机 Harness SDK'};}
 async disk(){if(process.platform==='win32'){const info=await fs.statfs('C:\\');if(Number(info.bavail)*Number(info.bsize)<2*1024**3)throw Error('C 盘余量低于 2 GB，已暂停新的制作请求；测试数据仍位于 E 盘');}}
 async start(p){
  if(!this.connected)await this.connect();await this.disk();
  await this.rpc('studio_prepare_agent',{id:p.id});const workspace=await this.rpc('studio_read',{id:p.id}),kind=workspace.kind??'module';if([...this.jobs.values()].some(j=>j.workspace===p.id&&j.status==='running'))throw Error('该副本已有制作任务');
  if(typeof p.requirement!=='string'||!p.requirement.trim()||p.requirement.length>16000)throw Error('请填写不超过 16000 字符的制作需求');
  const timeout=p.timeout??600;if(!Number.isInteger(timeout)||timeout<10||timeout>1200)throw Error('制作时限为 10–1200 秒');
  const scoped=await this.rpc('studio_maker_scope',{id:p.id});
  if(scoped){p={...p,auto_publish:scoped.role==='component',allow_network_testing:true,allow_component_creation:p.allow_component_creation===true&&scoped.allow_component_creation};}
  const allow=kind==='network'&&p.allow_component_creation===true,testing=p.allow_network_testing===true,tools=makerTools(kind,allow,testing),references=Object.entries(workspace.references).sort(([a],[b])=>a.localeCompare(b));
  const prefix=hash({kind,allow,references,tools});let source;
  if(p.fork_session||p.resume_session){source=this.sessions.get(p.fork_session??p.resume_session);if(!source||source.prefix!==prefix)throw Error('教程或可用工具前缀已变化，请新开会话');if(p.resume_session&&source.workspace!==p.id)throw Error('继续历史只能用于原工作副本，换副本请分叉');}
  const id=randomUUID(),job={id,workspace:p.id,kind,status:'running',phase:'coding',started:Date.now(),deadline:Date.now()+timeout*1000,repairs:0,children:[],tool_events:[],allow_component_creation:allow,allow_network_testing:testing,hidden_modules:p.hidden_modules??[],scoped:!!scoped,prefix,source_session:p.fork_session??p.resume_session,auto_publish:p.auto_publish!==false};this.jobs.set(id,job);
  const instructions=workspace.references['AGENTS.md']+'\n\n当前职责：'+(kind==='network'?'网络预设组装；只产出 network.json 和 README。先按需读 lessons/06-presets.md。':kind==='tool'?'模块／工具制作；必须有 agent_tools，可调差异用配置。先按需读 lessons/01-local.md。':'模块／工具制作；先查目录复用，再按需读 lessons/01-local.md。')+(scoped?'\n这是局部管理员任务：先读 reference/局部网络说明.md。root仅是当前管理员锚点；保留已有节点及其运行状态。禁止补全或猜测副本外节点。':'')+(testing?'\n用户可能只表达当前网络里想要的效果。先按需读 lessons/07-environment.md，再用测试副本理解场景，自己抽象可复用方案、验证并报告。':'');
  try{
   const created=await this.runner.request('create',{task:id,directory:workspace.directory,name:p.name??p.id,kind,instructions,tools,max_steps:p.max_steps??70,...(p.fork_session?{fork_cursor:p.seed_only?source.seed_cursor:source.cursor}:p.resume_session?{resume_session:p.resume_session}:{})});Object.assign(job,created);this.sessions.set(job.session_id,{workspace:p.id,prefix,kind,seed_cursor:created.seed_cursor});await this.saveSessions();
   this.run(job,p.requirement,p.max_repairs??3).catch(e=>{job.status='failed';job.error=e.message;this.persist(job).catch(()=>{});});return this.public(job);
  }catch(e){job.status='failed';job.error=e.message;throw e;}
 }
 async saveSessions(){await fs.writeFile(path.join(this.root,'native-maker-sessions.json'),JSON.stringify(Object.fromEntries(this.sessions),null,2));}
 async persist(job){await fs.mkdir(path.join(this.root,'maker-evidence'),{recursive:true});await fs.writeFile(path.join(this.root,'maker-evidence',job.id+'.json'),JSON.stringify(this.public(job),null,2));}
 async validate(id){let check=await this.rpc('studio_validate',{id,timeout:40});while(check.status==='running'&&!this.closed){await pause(250);check=await this.rpc('studio_job',{job:check.id});}return check;}
 async run(job,prompt,maxRepairs){
  if(!Number.isInteger(maxRepairs)||maxRepairs<0||maxRepairs>19)throw Error('修复上限为 0–19');
  while(job.status==='running'&&!this.closed){
   const left=Math.floor((job.deadline-Date.now())/1000);if(left<1){job.status='timeout';break;}
   const result=await this.runner.request('run',{session_id:job.session_id,prompt,timeout:left});Object.assign(job,{messages:result.messages,requests:result.requests,steps:result.steps,cursor:result.cursor,usage_events:result.events});
   this.sessions.set(job.session_id,{...this.sessions.get(job.session_id),cursor:result.cursor});await this.saveSessions();
   if(job.status!=='running')break;
   if(result.status!=='completed'){job.status=result.status;job.error=JSON.stringify(result.reason??'原生制作未完成');break;}
   job.phase='validating';const check=await this.validate(job.workspace);if(job.kind!=='network'&&check.status==='passed'&&/测试数量：0\b/.test(check.log)){check.status='failed';check.log+='\n制作任务必须补充至少一个已收集的真实业务测试，请按需阅读 lessons/05-tests.md。';}job.validation=check.id;job.validation_log=check.log;
   if(check.status==='passed'){if(job.auto_publish)job.release=await this.publish({id:job.workspace});job.status='completed';job.phase='verified';break;}
   if(job.repairs++>=maxRepairs){job.status='failed';job.phase='validation_failed';break;}
   await this.disk();job.phase='coding';prompt='宿主验证未通过，请根据日志局部修复；不修改教程、依赖和宿主检查。\n'+check.log.slice(-16000);
  }
  job.finished=Date.now();await this.persist(job);
 }
 async read(p){let job=this.jobs.get(p.task);if(!job){if(!/^[a-zA-Z0-9_-]{1,80}$/.test(p.task))throw Error('未知制作任务');try{job=JSON.parse(await fs.readFile(path.join(this.root,'maker-evidence',p.task+'.json'),'utf8'));}catch{throw Error('制作任务已不在内存中，请查看工作副本或证据');}if(job.status==='running')job={...job,status:'interrupted',error:'宿主重启中断了制作，请保留副本并重新发起'};return this.public(job);}if(job.status==='running'&&job.session_id){try{Object.assign(job,await this.runner.request('read',{session_id:job.session_id}));}catch(e){job.read_error=e.message;}}return this.public(job);}
 async cancel(p){const job=this.jobs.get(p.task);if(!job)throw Error('未知制作任务');job.status='cancelled';if(job.session_id)await this.runner.request('cancel',{session_id:job.session_id});for(const task of job.children){if(this.jobs.get(task)?.status==='running')await this.cancel({task});}await this.persist(job);return this.public(job);}
 async tool(p){
  const job=this.jobs.get(p.task);if(!job||job.status!=='running')throw Error('制作任务已停止');const allowed=makerTools(job.kind,job.allow_component_creation,job.allow_network_testing).map(t=>t.name);if(!allowed.includes(p.tool))throw Error('该制作任务未获准使用此工具');
  job.tool_events.push({tool:p.tool,path:p.arguments?.path,time:Date.now(),content_hash:p.arguments?.content?hash(p.arguments.content):undefined});
  if(p.tool==='validate'){job.validation_attempts=(job.validation_attempts??0)+1;if(job.validation_attempts>20)throw Error('本任务已达到 20 次验证上限，请报告未解决问题并结束');const check=await this.validate(job.workspace);return {status:check.status,log:check.log};}
  if(p.tool==='node_template')return editorNode(p.arguments.kind,p.arguments.id,p.arguments.name);
  if(p.tool==='copy_current_network')return this.rpc('studio_copy_current',{id:job.workspace});
  if(p.tool==='test_environment'){job.environment_attempts=(job.environment_attempts??0)+1;if(job.environment_attempts>100)throw Error('本任务已达到测试环境操作上限');const value=await this.rpc('studio_environment',{...p.arguments,id:job.workspace});job.environment=value;return value;}
  if(p.tool==='request_component'){
   const key=hash(p.arguments),old=job.children.map(id=>this.jobs.get(id)).find(j=>j.request_key===key);if(old)return {task:old.id,status:old.status,release:old.release};
   if(job.children.length>=6)throw Error('本次预设最多委托 6 个组件；先复用已发布能力');
   const workspace=await this.rpc('studio_create',{kind:p.arguments.kind,name:p.arguments.name,sample:'blank'});if(job.scoped)await this.rpc('network_admin_child',{parent:job.workspace,id:workspace.id});const child=await this.start({id:workspace.id,name:p.arguments.name,requirement:p.arguments.requirement,allow_network_testing:job.allow_network_testing,auto_publish:true,timeout:Math.max(10,Math.min(600,Math.floor((job.deadline-Date.now())/1000)))});this.jobs.get(child.id).request_key=key;job.children.push(child.id);return {task:child.id,status:child.status};
  }
  if(p.tool==='component_status'){if(!job.children.includes(p.arguments.task))throw Error('只能查看当前预设委托的组件');const child=this.jobs.get(p.arguments.task),end=Date.now()+Math.min(30,Math.max(0,p.arguments.wait_seconds??15))*1000;while(child.status==='running'&&job.status==='running'&&Date.now()<end)await pause(500);return {task:child.id,status:child.status,release:child.release,validation_log:child.validation_log,error:child.error};}
  return this.rpc('studio_maker_tool',{id:job.workspace,tool:p.tool,arguments:p.arguments,hidden:job.hidden_modules});
 }
 async publish(p){
  const release=await this.rpc('studio_publish',p);
  if(release.kind==='component-presets'){
   const library=editorLibrary(this.directory),before=await library('editor.library'),bookmarks=release.presets.map((preset,index)=>({id:'maker-preset-'+hash({workspace:release.workspace,index}).slice(0,24),kind:'module',name:preset.name,description:preset.description,asset:{kind:'module',id:preset.module,config:preset.config},category:'default',createdAt:Date.now(),originMaker:release.workspace}));
   await library('editor.library.update',{action:'bookmark.patch',changes:bookmarks.map(value=>({id:value.id,expected:before.bookmarks.find(b=>b.id===value.id)??null,value}))});
   return {...release,bookmarks:bookmarks.map(b=>b.id)};
  }
  if(release.kind!=='network')return release;
  let tree={folders:[]};try{tree=JSON.parse(await fs.readFile(path.join(this.directory,'editor-library.json'),'utf8')).assets?.preset??tree;}catch(e){if(e.code!=='ENOENT')throw e;}
  const folder=release.display_folder??null;if(folder!=null&&!tree.folders.some(f=>f.id===folder))throw Error('预设目标目录已不存在');
  const ancestors=new Set();for(let id=folder;id!=null&&!ancestors.has(id);id=tree.folders.find(f=>f.id===id)?.parent)ancestors.add(id);
  const preset=await storedNetworks(this.directory).save({storageKind:ancestors.has('stored-networks')?'network':'fragment',document:release.document,editor:{name:release.name,mode:'internal',display_folder:folder,originMaker:release.id}});return {kind:'network',...preset};
 }
 async close(){this.closed=true;for(const j of this.jobs.values())if(j.status==='running')await this.cancel({task:j.id}).catch(()=>{});await this.runner?.close();}
}
