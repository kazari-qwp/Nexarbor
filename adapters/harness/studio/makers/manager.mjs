import {catalogPresets,instantiatePreset} from './preset-tools.mjs';
import {RequirementUpdates,requirementReference} from './requirement-updates.mjs';
import {unfinishedComponents} from './unfinished-components.mjs';
import {editNetwork} from './edit-network.mjs';
import {editJson} from './edit-json.mjs';
import {projectFiles} from './project-files.mjs';
import {transportRecovery} from './transport-recovery.mjs';
import {makerGit} from './git-tools.mjs';
import {validationFeedback,validationLog} from './validation-feedback.mjs';
import {NetworkObserver,indexNetwork,observerTools,readObservedResource,readObservedText} from './network-observer.mjs';
import networkSkill from './network-skill.cjs';
import {NetworkRenderer} from './network-renderer.mjs';
import {ProjectObservations} from './project-observer.mjs';
import fs from 'node:fs/promises';import path from 'node:path';import {createHash,randomUUID} from 'node:crypto';
import {makerTools} from './tools.mjs';import {editorNode} from '../../framework/editor-nodes.js';import {storedNetworks} from '../../framework/stored-networks.js';
import {editorLibrary} from '../../framework/editor-library.js';
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex'),pause=ms=>new Promise(r=>setTimeout(r,ms));
export class MakerManager{
 constructor(directory,rpc,{runnerFactory}={}){this.directory=directory;this.rpc=rpc;this.runnerFactory=runnerFactory;this.jobs=new Map();this.sessions=new Map();this.root=path.join(directory,'studio');this.connected=false;this.closed=false;this.observations=new Map();this.observationIndices=new Map();this.renderer=new NetworkRenderer(directory);this.projectObservations=new ProjectObservations(this.renderer);this.edits=new Map();this.updates=new RequirementUpdates(this);}
 async initialize(){try{for(const [id,s] of Object.entries(JSON.parse(await fs.readFile(path.join(this.root,'native-maker-sessions.json'),'utf8'))))this.sessions.set(id,s);}catch(e){if(e.code!=='ENOENT')throw e;}let files=[];try{files=await fs.readdir(path.join(this.root,'maker-evidence'));}catch(e){if(e.code!=='ENOENT')throw e;}for(const file of files.filter(n=>/^[a-zA-Z0-9_-]+\.json$/.test(n))){const job=JSON.parse(await fs.readFile(path.join(this.root,'maker-evidence',file),'utf8'));if(job.status==='running'){job.status='interrupted';job.error='宿主重启中断了制作，可保留工作分支后继续';}this.jobs.set(job.id,job);}}
 status(){return {connected:this.connected,authority:'本机 Harness SDK',jobs:[...this.jobs.values()].sort((a,b)=>(a.started??0)-(b.started??0)).map(j=>this.public(j)),backend:'native-sdk'};}
 public(job){const {instructions,...value}=job;return structuredClone(value);}
 async connect(p={}){if(!this.runnerFactory)throw Error('制作运行器尚未配置');if(this.runner)return {connected:true,authority:'本机 Harness SDK'};this.runner=await this.runnerFactory(p,(method,args)=>this.tool(args));await this.runner.start();this.connected=true;return {connected:true,authority:'本机 Harness SDK'};}
 async disk(){if(process.platform==='win32'){const info=await fs.statfs('C:\\');if(Number(info.bavail)*Number(info.bsize)<2*1024**3)throw Error('C 盘余量低于 2 GB，已暂停新的制作请求；测试数据仍位于 E 盘');}}
 async profile(workspace,kind,allow,testing=true,runtimeManagement=false){
  const tools=makerTools(kind,allow,testing).filter(t=>!runtimeManagement||!['validate','test_environment','copy_current_network'].includes(t.name)),references=Object.entries(workspace.references??{}).filter(([name])=>name!==requirementReference).sort(([a],[b])=>a.localeCompare(b));
  return {tools,prefix:hash({kind,allow,references,tools,skills:await networkSkill.fingerprint()})};
 }
 async start(p){
  if(!this.connected)await this.connect();await this.disk();
  await this.rpc('studio_prepare_agent',{id:p.id});const workspace=await this.rpc('studio_read',{id:p.id}),kind=workspace.kind??'module';if([...this.jobs.values()].some(j=>j.workspace===p.id&&j.status==='running'))throw Error('该副本已有制作任务');
  if(typeof p.requirement!=='string'||!p.requirement.trim()||p.requirement.length>16000)throw Error('请填写不超过 16000 字符的制作需求');
  const timeout=p.timeout??600;if(!Number.isInteger(timeout)||timeout<10||timeout>86400)throw Error('制作时限为 10–86400 秒');
  const scoped=await this.rpc('studio_maker_scope',{id:p.id});
  if(scoped){p={...p,auto_publish:scoped.role==='component',allow_network_testing:true,allow_component_creation:p.allow_component_creation===true&&scoped.allow_component_creation};}
  const runtimeManagement=scoped?.role==='network'&&kind==='network',allow=kind==='network'&&(scoped?p.allow_component_creation===true:true),testing=!runtimeManagement,{tools,prefix}=await this.profile(workspace,kind,allow,testing,runtimeManagement);
  const inherited=unfinishedComponents(this.jobs,{workspace:p.id,kind,scoped:!!scoped,hidden_modules:p.hidden_modules});let source;
  if(p.fork_session||p.resume_session){source=this.sessions.get(p.fork_session??p.resume_session);if(!source||source.prefix!==prefix)throw Error('教程或可用工具前缀已变化，请新开会话');if(p.resume_session&&source.workspace!==p.id)throw Error('继续历史只能用于原工作副本，换副本请分叉');}
  const id=randomUUID(),job={id,workspace:p.id,kind,status:'running',phase:'coding',started:Date.now(),deadline:Date.now()+timeout*1000,repairs:0,children:[],inherited_children:inherited,tool_events:[],allow_component_creation:allow,allow_network_testing:testing,hidden_modules:p.hidden_modules??[],scoped:!!scoped,runtime_management:runtimeManagement,prefix,source_session:p.fork_session??p.resume_session,auto_publish:p.auto_publish!==false};this.jobs.set(id,job);
  const instructions=(runtimeManagement?'你是运行中的局部网络管理员。加载 nexarbor-basics、inspect-network 和 make-network 后，按运行中管理分支操作：读取局部网络和可用预设，用 instantiate_preset 放置实例并连接入口。完成后用 inspect_nodes 或 view_network 查看一次，确认节点与接线确实创建，然后简洁交付。不编写 tests，不调用 validate，不模拟讨论、协作或其他业务运行。项目制作与完整验收属于网络制作任务，当前任务只是动态管理网络。':networkSkill.instructions(kind))+(workspace.references?.['reference/追加要求.json']?'\n本副本保存了委托方追加要求，按需读取 reference/追加要求.json，原有要求仍有效。':'')+(inherited.length?'\n本工作副本保留了未发布委托；先用 component_status 按需查看并继续，编号：'+inherited.join('、'):'')+(workspace.identity?.immutable?'\n宿主已固定本次修订的模块 ID 为 '+workspace.identity.module_id+'；保留这个 ID，不改回接口参考中的原发布 ID。':'')+(scoped?'\n这是局部管理员任务：先读 reference/局部网络说明.md。保留已有节点及运行状态，不补全或猜测副本外节点。':'');
  try{
   const created=await this.runner.request('create',{task:id,directory:workspace.directory,name:p.name??p.id,kind,instructions,tools,model:p.model,model_signature:source?.model_signature,max_steps:p.max_steps??100000,...(!p.fork_session&&!p.resume_session&&workspace.origin?.consult_cursor?{fork_cursor:workspace.origin.consult_cursor}:{}),...(p.fork_session?{fork_cursor:p.seed_only?source.seed_cursor:source.cursor}:p.resume_session?{resume_session:p.resume_session}:{})});Object.assign(job,created);this.sessions.set(job.session_id,{workspace:p.id,prefix,kind,seed_cursor:created.seed_cursor,model_signature:created.model_signature});await this.saveSessions();
   this.run(job,p.requirement,p.max_repairs??3,p.attachments??[]).catch(e=>{this.observations.delete(job.id);if(job.status==='running'){job.status='failed';job.error=e.message;}job.finished??=Date.now();this.persist(job).catch(()=>{});});return this.public(job);
  }catch(e){job.status='failed';job.error=e.message;throw e;}
 }
 async saveSessions(){await fs.writeFile(path.join(this.root,'native-maker-sessions.json'),JSON.stringify(Object.fromEntries(this.sessions),null,2));}
 async persist(job){if(this.project&&job.workspace){try{job.git=await this.project.branch(await this.rpc('studio_read',{id:job.workspace}));}catch(error){job.history_error=error.message;}}if(this.project){let prefix;if(job.cursor)try{prefix=await this.runner.request('export-context',{cursor:job.cursor});}catch(e){job.history_error=e.message;}await this.project.conversation('maker',this.public(job),prefix);}await fs.mkdir(path.join(this.root,'maker-evidence'),{recursive:true});await fs.writeFile(path.join(this.root,'maker-evidence',job.id+'.json'),JSON.stringify(this.public(job),null,2));}
 async validate(id,timeout=60){if(!Number.isInteger(timeout)||timeout<1||timeout>86400)throw Error('验证时限为1至86400秒');let check=await this.rpc('studio_validate',{id,timeout});while(check.status==='running'&&!this.closed){await pause(250);check=await this.rpc('studio_job',{job:check.id});}return check;}
 async run(job,prompt,maxRepairs,attachments=[]){
  if(!Number.isInteger(maxRepairs)||maxRepairs<0||maxRepairs>19)throw Error('修复上限为 0–19');
  let passKind='build';
  while(job.status==='running'&&!this.closed){
   const left=Math.floor((job.deadline-Date.now())/1000);if(left<1){job.status='timeout';break;}
   const supplement=await this.updates.drain(job);if(supplement){prompt+='\n'+supplement;passKind='requirement-update';job.phase='coding';}
   const began=Date.now(),previousPass=job.passes?.at(-1);
   const result=await this.runner.request('run',{session_id:job.session_id,prompt,attachments,timeout:left});(job.passes??=[]).push({kind:passKind,status:result.status,elapsed_ms:Date.now()-began,requests:result.requests-(previousPass?.requests_total??0),steps:result.steps-(previousPass?.steps_total??0),requests_total:result.requests,steps_total:result.steps});Object.assign(job,{messages:result.messages,requests:result.requests,steps:result.steps,cursor:result.cursor,usage_events:result.events,previews:result.previews??[]});
   this.sessions.set(job.session_id,{...this.sessions.get(job.session_id),cursor:result.cursor});await this.saveSessions();
   if(job.status!=='running')break;
   if(result.status!=='completed'){
    Object.assign(job.passes.at(-1),{reason:result.reason,tool_input_errors:result.tool_input_errors??[]});
    const recovery=transportRecovery(job,result);
    if(recovery){job.transport_recoveries=(job.transport_recoveries??0)+1;job.phase='recovering';passKind='transport-recovery';prompt=recovery;attachments=[];continue;}
    job.status=result.status;job.error=JSON.stringify(result.reason??'原生制作未完成');break;
   }
   const pending=await this.updates.drain(job);if(pending){prompt=pending;attachments=[];passKind='requirement-update';job.phase='coding';continue;}
   if(job.runtime_management){
    const work=await this.rpc('studio_read',{id:job.workspace});
    const check=await this.rpc('studio_graph_validate',{document:JSON.parse(work.files['network.json'])});
    if(!check.valid){job.status='failed';job.phase='invalid_structure';job.error=JSON.stringify(check.errors);break;}
    job.structure_check={valid:true};job.requirements_closed=true;job.status='completed';job.phase='assembled';break;
   }
   attachments=[];job.phase='validating';const check=await this.validate(job.workspace,Math.min(job.validation_timeout??60,Math.max(1,Math.floor((job.deadline-Date.now())/1000))));if(check.status==='passed'&&/测试数量：0\b/.test(check.log)){check.status='failed';check.log+='\n制作任务必须补充至少一个已收集的真实业务测试；模块看 lessons/05-tests.md，网络看 make-network 的 references/行为测试.md。';}job.validation=check.id;job.validation_log=check.log;
   job.validation_status=check.status;Object.assign(job.passes.at(-1),{validation:{job:check.id,status:check.status,source_digest:check.digest,test_count:validationFeedback(check).test_count}});
   const queued=await this.updates.drain(job);if(queued){prompt=queued+(check.status==='passed'?'':'\n当前验证仍需修复：'+validationFeedback(check).log);passKind='requirement-update';job.phase='coding';continue;}
   if(check.status==='passed'){
    if(!job.self_review_done){job.self_review_done=true;job.phase='reviewing';passKind='self-review';prompt='交付前做一次有边界的使用方自检：逐项对照原需求，列出实际跑过的入口、结果和未测缺口；按需读 lessons/15-behavior-tests.md。选一项不同于已有测试、最影响使用的完整场景补测：使用真实入口和模型实际工具，核对相关组件及每类生成对象的结果，不能靠字典或补配置。可调参数改变后实际运行；大输入按路径／引用由代码消费，以公开真实规模验证。修复后重跑，不降需求或做无关润色；通过后简洁交付。'+(check.warnings?.length?'\n当前配置检查（只给相关字段）：\n'+check.warnings.slice(0,8).map(w=>w.path+'：'+w.message).join('\n'):'');continue;}
    if(this.updates.busy(job)){prompt='先处理尚在投递的追加要求。';passKind='requirement-update';continue;}job.requirements_closed=true;
    if(job.auto_publish)job.release=await this.publish({id:job.workspace});job.status='completed';job.phase='verified';break;
   }
   if(job.repairs++>=maxRepairs){job.status='failed';job.phase='validation_failed';break;}
   await this.disk();job.phase='coding';passKind='repair';prompt='宿主验证未通过，请根据日志局部修复；也核对自测前提和独立推算的预期，修正错误预期需有需求依据，不删场景或改变业务来迎合断言。不修改教程、依赖和宿主检查。\n'+validationFeedback(check).log;
  }
  this.observations.delete(job.id);job.finished=Date.now();await this.persist(job);this.updates.clear(job);
 }
 async read(p){let job=this.jobs.get(p.task);if(!job){if(!/^[a-zA-Z0-9_-]{1,80}$/.test(p.task))throw Error('未知制作任务');try{job=JSON.parse(await fs.readFile(path.join(this.root,'maker-evidence',p.task+'.json'),'utf8'));}catch{throw Error('制作任务已不在内存中，请查看工作副本或证据');}if(job.status==='running')job={...job,status:'interrupted',error:'宿主重启中断了制作，请保留副本并重新发起'};return this.public(job);}if(job.status==='running'&&job.session_id){try{Object.assign(job,await this.runner.request('read',{session_id:job.session_id}));}catch(e){job.read_error=e.message;}}return this.public(job);}
 async cancel(p){const job=this.jobs.get(p.task);if(!job)throw Error('未知制作任务');job.status='cancelled';this.observations.delete(job.id);if(job.session_id)await this.runner.request('cancel',{session_id:job.session_id});for(const task of job.children){if(this.jobs.get(task)?.status==='running')await this.cancel({task});}await this.persist(job);return this.public(job);}
 async tool(p){
  if(this.closed)throw Error('制作宿主已关闭');
  if(this.advisor?.has(p.task))return this.advisor.tool(p);
  const job=this.jobs.get(p.task);if(!job||job.status!=='running')throw Error('制作任务已停止');const allowed=makerTools(job.kind,job.allow_component_creation,job.allow_network_testing).map(t=>t.name);if(!allowed.includes(p.tool)||job.runtime_management&&['validate','test_environment','copy_current_network'].includes(p.tool))throw Error('当前任务未提供此工具');
  return this.executeTool(job,p);
 }
 async executeTool(job,p){
  const definition=makerTools(job.kind,job.allow_component_creation,job.allow_network_testing).find(t=>t.name===p.tool);if(!definition)throw Error('此制作职责不支持该工具');const args=p.arguments??{},schema=definition.parameters;if(!args||typeof args!=='object'||Array.isArray(args))throw Error(p.tool+' 参数必须是对象');const missing=(schema.required??[]).filter(key=>!Object.hasOwn(args,key)),extra=Object.keys(args).filter(key=>!Object.hasOwn(schema.properties,key));if(missing.length||extra.length)throw Error(p.tool+' 参数不匹配：'+(missing.length?'缺少 '+missing.join(', ')+'；':'')+(extra.length?'未知 '+extra.join(', ')+'；':'')+'可用字段 '+Object.keys(schema.properties).join(', '));
  job.tool_events.push({tool:p.tool,path:p.arguments?.path,time:Date.now(),content_hash:p.arguments?.content?hash(p.arguments.content):undefined});
  if(p.tool==='project_files'){
   if(job.scoped)throw Error('局部管理员只读可达节点的受管理文本；用 read_network_text，不读取整个项目目录');
   const directory=args.project??this.project?.directory;if(!directory)throw Error('当前宿主没有项目文件夹');
   return projectFiles(directory,args,job.hidden_modules??[]);
  }
  if(p.tool==='install_module'){
   if(!this.project)throw Error('当前宿主没有项目资源安装能力');
   const catalog=await this.rpc('studio_catalog'),seen=new Set(),hidden=new Set(job.hidden_modules??[]);
   const visit=id=>{if(hidden.has(id))throw Error('隐藏组件不可安装：'+id);if(seen.has(id))return;const release=catalog.library[id];if(!release)throw Error('未知公开模块：'+id);seen.add(id);for(const dependency of release.manifest.requires??[])visit(dependency);};
   visit(args.id);await this.project.install('module',args.id);await this.rpc('studio_project_modules');return {installed:args.id,modules:[...seen],count:seen.size};
  }
  if(['read_resource','read_network_text'].includes(p.tool)||observerTools.some(t=>t.name===p.tool))return this.observe(job,p.tool,p.arguments??{});
  if(['write_file','edit_file','edit_json','network_patch','edit_network','copy_current_network'].includes(p.tool)||p.tool==='test_environment'&&p.arguments?.action!=='inspect'){const held=this.observations.get(job.id);if(held){held.epoch++;held.observer=null;}}
  if(p.tool==='project_git'){if(p.arguments?.action==='restore')this.observations.delete(job.id);return makerGit(this,job,p.arguments);}
  if(p.tool==='validate'){if(p.arguments?.job){const check=await this.rpc('studio_job',{job:p.arguments.job});if(check.workspace!==job.workspace)throw Error('只能读取当前工作副本的验证日志');return validationLog(check,p.arguments);}job.validation_attempts=(job.validation_attempts??0)+1;if(job.validation_attempts>1000)throw Error('本任务已达到 1000 次验证上限，请报告未解决问题并结束');if(args.timeout_seconds!==undefined){if(!Number.isInteger(args.timeout_seconds)||args.timeout_seconds<1||args.timeout_seconds>86400)throw Error('验证时限为1至86400秒');job.validation_timeout=args.timeout_seconds;}const check=await this.validate(job.workspace,Math.min(job.validation_timeout??60,Math.max(1,Math.floor(((job.deadline??Infinity)-Date.now())/1000))));return validationFeedback(check);}
  if(p.tool==='edit_network'){const result=(this.edits.get(job.id)??Promise.resolve()).then(async()=>{const work=await this.rpc('studio_read',{id:job.workspace}),catalog=await this.rpc('studio_catalog'),file=args.path??'network.json';if(!file.endsWith('.json'))throw Error('网络产物使用自有 JSON 文件');const text=work.files[file]??'',document=text?JSON.parse(text):{network:{version:8,nodes:[],signals:{},delegations:[]},files:{}};const edited=editNetwork(document,args.commands,catalog.library);await this.rpc('studio_save',{id:job.workspace,file,content:JSON.stringify(edited.document,null,2),expected:createHash('sha256').update(text).digest('hex')});return {...edited.receipt,file};});this.edits.set(job.id,result.catch(()=>{}));return result;}
  if(p.tool==='edit_json'){const result=(this.edits.get(job.id)??Promise.resolve()).then(async()=>{const work=await this.rpc('studio_read',{id:job.workspace}),text=work.files[args.path];if(!args.path.endsWith('.json')||typeof text!=='string')throw Error('只能编辑工作副本中已有的自有 JSON 文件');const value=editJson(JSON.parse(text),args.operations),content=JSON.stringify(value,null,2)+'\n';await this.rpc('studio_save',{id:job.workspace,file:args.path,content,expected:createHash('sha256').update(text).digest('hex')});return {saved:args.path,operation_count:args.operations.length,digest:createHash('sha256').update(content).digest('hex')};});this.edits.set(job.id,result.catch(()=>{}));return result;}
  if(p.tool==='catalog_presets')return catalogPresets(this,args);
  if(p.tool==='instantiate_preset'){this.observations.delete(job.id);const result=(this.edits.get(job.id)??Promise.resolve()).then(()=>instantiatePreset(this,job,args));this.edits.set(job.id,result.catch(()=>{}));return result;}
  if(p.tool==='node_template'){
   if(args.kind==='subnode')return editNetwork({network:{nodes:[]},files:{}},[{op:'node.create',...args} ],{}).document.network.nodes[0];
   return editorNode(args.kind,args.id,args.name);
  }
  if(p.tool==='copy_current_network')return this.rpc('studio_copy_current',{id:job.workspace});
  if(p.tool==='test_environment'){job.environment_attempts=(job.environment_attempts??0)+1;if(job.environment_attempts>100)throw Error('本任务已达到测试环境操作上限');const value=await this.rpc('studio_environment',{...p.arguments,id:job.workspace});job.environment=value;return value;}
  if(p.tool==='request_component')return this.requestComponent(job,p.arguments);
  if(p.tool==='component_status'){if(![...job.children,...(job.inherited_children??[])].includes(p.arguments.task))throw Error('只能查看当前工作副本自己委托的组件');const child=this.jobs.get(p.arguments.task),end=Date.now()+Math.min(30,Math.max(0,p.arguments.wait_seconds??15))*1000;while(child.status==='running'&&job.status==='running'&&Date.now()<end)await pause(500);return {task:child.id,status:child.status,phase:child.phase,release:p.arguments.details?child.release:child.release?{id:child.release.id,kind:child.release.kind,version:child.release.version,...(child.release.presets?{preset_count:child.release.presets.length,presets:child.release.presets.slice(0,8).map(v=>({name:v.name,module:v.module}))}:{})}:undefined,validation:child.validation_log?validationFeedback({id:child.validation,status:child.validation_status??(child.status==='completed'?'passed':'failed'),log:child.validation_log}):undefined,error:child.error,hint:child.status==='completed'?(child.release?.presets?'用 details=true 取得配置方案的完整装配参数。':'用 catalog_modules 的精确 ID 读取已发布接口和默认配置。'):child.status!=='running'?'工作副本已保留；用 request_component(task=此编号,requirement=继续要求) 继续，不必从空白重做。':undefined};}
  return this.rpc('studio_maker_tool',{id:job.workspace,tool:p.tool,arguments:p.arguments,hidden:job.hidden_modules});
 }
 async requestComponent(job,args){
  if(args.task&&args.module)throw Error('task 和 module 分别用于继续委托与修订公开组件，请只选一种');
  if(args.task){if(![...job.children,...(job.inherited_children??[])].includes(args.task))throw Error('只能继续当前任务或本工作副本自己委托的未发布组件');const child=this.jobs.get(args.task);if(child?.status==='running')return this.updates.enqueue(child,{requirement:args.requirement,source:job.id});}
  const key=hash(args),old=job.children.map(id=>this.jobs.get(id)).find(j=>j.request_key===key);
  if(old)return {task:old.id,status:old.status,release:old.release?{id:old.release.id,kind:old.release.kind,version:old.release.version}:undefined};
  const timeout=Math.min(86400,Math.floor((job.deadline-Date.now())/1000));if(timeout<10)throw Error('父任务剩余时间不足，已保留委托进度，请在继续父任务后重试');
  let workspace,previous,kind=args.kind,name=args.name,resume;
  if(args.task){
   if(![...job.children,...(job.inherited_children??[])].includes(args.task))throw Error('只能继续当前任务或本工作副本自己委托的未发布组件');
   previous=this.jobs.get(args.task);
   kind=previous.kind;const work=await this.rpc('studio_read',{id:previous.workspace});name??=work.label??work.name??previous.workspace;
   if(previous.release)workspace=await this.rpc('studio_revision',{kind,source:{files:work.files,release:previous.release},reference:args.requirement,origin:{previous_workspace:previous.workspace,parent:job.workspace}});
   else{workspace=work;const profile=await this.profile(work,kind,false,job.allow_network_testing),stored=this.sessions.get(previous.session_id);if(stored?.workspace===work.id&&stored.prefix===profile.prefix)resume=previous.session_id;}
  }else{
   const roots=job.children.map(id=>this.jobs.get(id)).filter(child=>!child.continues_task);if(roots.length>=12)throw Error('本次预设最多委托12个独立组件；已有委托用 task 继续或修订');
   if(args.module){
    if(job.hidden_modules?.includes(args.module))throw Error('本次未提供该组件源码，不能用修订恢复隐藏答案');
    const catalog=await this.rpc('studio_catalog');if(!catalog.library[args.module]||catalog.library[args.module].available===false)throw Error('请先把要修订的公开组件安装到当前项目');
    const source=await this.rpc('studio_release_read',{module:args.module});kind??=source.release.origin_kind==='tool'?'tool':'module';name??=source.release.manifest.name??args.module;
    if(!['module','tool'].includes(kind))throw Error('组件修订的 kind 为 module 或 tool');
    workspace=await this.rpc('studio_revision',{kind,source,reference:args.requirement,origin:{module:args.module,parent:job.workspace}});
   }else{
    if(!['module','tool'].includes(kind)||typeof name!=='string'||!name.trim())throw Error('新委托需要 kind=module/tool 与 name；继续已有委托使用 task，公开组件修订使用 module');
    workspace=await this.rpc('studio_create',{kind,name,sample:'blank'});
   }
  }
  if(job.scoped)await this.rpc('network_admin_child',{parent:job.workspace,id:workspace.id});
  const child=await this.start({id:workspace.id,name,requirement:args.requirement,resume_session:resume,allow_network_testing:job.allow_network_testing,hidden_modules:job.hidden_modules,auto_publish:true,timeout});
  Object.assign(this.jobs.get(child.id),{request_key:key,...(previous?{continues_task:previous.id}:{})});job.children.push(child.id);
  return {task:child.id,status:child.status,...(previous?{continues_task:previous.id}:{}),...(workspace.identity?.immutable?{module_id:workspace.identity.module_id}: {})};
 }
 observe(job,name,args){
  if(this.projectObservations.uses(job.id,args))return this.projectObservations.observe(job.id,name,args);
  if(args.source)this.projectObservations.clear(job.id);
  let state=this.observations.get(job.id);if(!state){state={source:job.kind==='network'?'candidate':'current',epoch:0,tail:Promise.resolve(),observer:null,views:new Map()};this.observations.set(job.id,state);}
  const result=state.tail.then(async()=>{
   if(job.status!=='running')throw Error('制作任务已停止');
   const source=args.source??state.source;
   if(['current','environment'].includes(source)&&!job.allow_network_testing)throw Error('当前任务未获准读取用户网络；请使用 candidate');
   if(!state.observer||state.source!==source||args.refresh){
    if(args.refresh)state.epoch++;
    const epoch=state.epoch,document=await this.rpc('studio_observe',{id:job.workspace,source});
    const resources={},catalog=await this.rpc('studio_catalog');
    for(const id of new Set(document.network.nodes.flatMap(n=>Object.keys(n.modules??{}))))if(catalog.library[id]&&!job.hidden_modules.includes(id))resources[id]=await this.rpc('studio_release_read',{module:id});
    if(epoch!==state.epoch)throw Error('读取期间副本已变化，请重新观察');
    const key=job.workspace+'|'+source,index=indexNetwork(document,this.observationIndices.get(key));this.observationIndices.set(key,index);
    const catalogRevisions=Object.fromEntries(Object.entries(catalog.library).filter(([name])=>!job.hidden_modules.includes(name)).map(([name,r])=>[name,r.digest]));const snapshot={document,resources,catalogRevisions,source,observerIndex:index,selection:{nodes:[],edges:[]}},id=hash({document,resources,catalogRevisions,index,source,epoch});state.views.clear();state.observer=new NetworkObserver(snapshot,id,state.views);state.source=source;
   }
   const observer=state.observer;observer.check(args);if(name==='read_resource'){if(!observer.snapshot.resources[args.module]&&Object.hasOwn(observer.snapshot.catalogRevisions,args.module)){const resource=await this.rpc('studio_release_read',{module:args.module});if(resource.release.digest!==observer.snapshot.catalogRevisions[args.module])throw Error('模块发布版本已变化，请 refresh 后重新读取');observer.snapshot.resources[args.module]=resource;}return readObservedResource(observer.snapshot,observer.id,args);}if(name==='read_network_text')return readObservedText(observer.snapshot,observer.id,args);
   return observer.execute(name,args,scene=>this.renderer.render(scene));
  });state.tail=result.then(()=>{},()=>{});return result;
 }

 async publish(p){
  const release=await this.rpc('studio_publish',p);
  if(this.project&&release.id&&release.manifest){await this.project.install('module',release.id);await this.rpc('studio_project_modules');const work=await this.rpc('studio_read',{id:p.id});release.git=await this.project.branch(work);}
  if(release.kind==='component-presets'){
   const library=editorLibrary(this.directory),before=await library('editor.library'),bookmarks=release.presets.map((preset,index)=>({id:'maker-preset-'+hash({workspace:release.workspace,index}).slice(0,24),kind:'module',name:preset.name,description:preset.description,asset:{kind:'module',id:preset.module,config:preset.config},category:'default',createdAt:Date.now(),originMaker:release.workspace}));
   await library('editor.library.update',{action:'bookmark.patch',changes:bookmarks.map(value=>({id:value.id,expected:before.bookmarks.find(b=>b.id===value.id)??null,value}))});
   return {...release,bookmarks:bookmarks.map(b=>b.id)};
  }
  if(release.kind!=='network')return release;
  let tree={folders:[]};try{tree=JSON.parse(await fs.readFile(path.join(this.project?.directory??this.directory,'editor-library.json'),'utf8')).assets?.preset??tree;}catch(e){if(e.code!=='ENOENT')throw e;}
  const folder=release.display_folder??null;if(folder!=null&&!tree.folders.some(f=>f.id===folder))throw Error('预设目标目录已不存在');
  const ancestors=new Set();for(let id=folder;id!=null&&!ancestors.has(id);id=tree.folders.find(f=>f.id===id)?.parent)ancestors.add(id);
  const hasTemplates=!!release.runtime?.templates?.length;
  const store=storedNetworks(this.directory),preset=await store.save({storageKind:hasTemplates||ancestors.has('stored-networks')?'network':'fragment',document:release.document,editor:{name:release.name,mode:'internal',display_folder:folder,originMaker:release.id,...(hasTemplates?{runtime:release.runtime}:{})}});
  const outputs=[];for(const item of release.outputs??[]){const saved=await store.save({storageKind:'fragment',document:item.document,editor:{name:item.name,description:item.description,mode:'internal',display_folder:folder,originMaker:release.id,originFile:item.file}});outputs.push({id:saved.id,name:saved.name,file:item.file,node_count:saved.snapshot.nodes.length,repeat_unit_count:saved.snapshot.repeat_unit_count??null});}
  return {kind:'network',...preset,...(outputs.length?{outputs}:{})};
 }
 async close(){this.renderer.close();this.observations.clear();this.projectObservations.states.clear();this.closed=true;await this.advisor?.close();for(const j of this.jobs.values())if(j.status==='running')await this.cancel({task:j.id}).catch(()=>{});await this.runner?.close();}
}
