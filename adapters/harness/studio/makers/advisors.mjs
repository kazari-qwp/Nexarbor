import networkSkill from './network-skill.cjs';
import {makerTools} from './tools.mjs';
import {NetworkObserver,indexNetwork,observerTools,observerResourceTool,observerTextTool,readObservedText} from './network-observer.mjs';
import {NetworkRenderer} from './network-renderer.mjs';
import {inspectNetwork,responseFormat} from './network-inspection.mjs';
// 两个制作 Agent 的持续对话：提问读取快照，编辑按需建立 Git 工作分支。
import fs from 'node:fs/promises';import path from 'node:path';import {randomUUID,createHash} from 'node:crypto';
import {GitHistory,splitSnapshot,joinSnapshot} from './git-history.mjs';
import {storedNetworks} from '../../framework/stored-networks.js';
const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex'),clone=structuredClone;
export const adviceTools=[...observerTools,observerTextTool,{...observerResourceTool,parameters:{...observerResourceTool.parameters,required:[]}}];
export const adviceInstructions=role=>networkSkill.instructions(role==='network'?'network':'module')+'\n本轮当前网络由宿主固定快照；修改候选网络后可继续观察候选图。编辑工具首次使用会自动建立工作分支，不会覆盖已发布组件或直接改运行图。用户提出修改需求就完成、验证并报告；只是提问时先回答。';
export class Advisors{
 constructor(directory,rpc,makers,catalog){this.directory=directory;this.root=path.join(directory,'studio/advice');this.rpc=rpc;this.makers=makers;this.catalog=catalog;this.history=new GitHistory(directory);this.jobs=new Map();this.activeRecords=new Map();this.workloads=new Map();this.observerViews=new Map();this.queue=Promise.resolve();this.persistence=Promise.resolve();this.renderer=new NetworkRenderer(directory);}
 views(id){if(!this.observerViews.has(id)){this.observerViews.set(id,new Map());if(this.observerViews.size>24)this.observerViews.delete(this.observerViews.keys().next().value);}return this.observerViews.get(id);}
 has(id){return this.jobs.has(id);}
 serialPersistence(fn){const task=this.persistence.then(fn);this.persistence=task.catch(()=>{});return task;}
 atomic(file,value,{ui=false,uiFields}={}){const input=clone(value);return this.serialPersistence(async()=>{
  let stored=input,current;try{current=JSON.parse(await fs.readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
  if(stored.id&&current){
   if(uiFields)stored={...((input.revisionAt??input.updatedAt??0)>(current.revisionAt??current.updatedAt??0)?input:current),...Object.fromEntries(uiFields.filter(key=>Object.hasOwn(input,key)).map(key=>[key,input[key]]))};
   else{
    if(current.job?.id!==stored.job?.id&&(current.job?.started??0)>(stored.job?.started??0))return current;
    if(!ui){stored.focus=current.focus??stored.focus;stored.draft=current.draft??stored.draft;}
   }
   if(stored.focus?.key===stored.workKey&&stored.workspace)stored.focus={...stored.focus,workspace:stored.workspace};
  }
  stored.revisionAt=Date.now();delete stored.portablePrefix;await fs.mkdir(path.dirname(file),{recursive:true});const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(stored));await fs.rename(temp,file);
  if(this.makers.project&&path.dirname(file)===this.root&&stored.id)await this.makers.project.conversation('advice',stored);return stored;
 });}

 file(id){if(!/^[a-z0-9-]{1,80}$/.test(id))throw Error('咨询编号无效');return path.join(this.root,id+'.json');}
 async read(p,portable=false){let record;try{record=JSON.parse(await fs.readFile(this.file(p.id),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;record=(await this.makers.project?.conversations('advice',{prefix:portable,id:p.id}))?.find(r=>r.id===p.id);if(!record)throw Error('咨询记录不存在');record.portableSource=true;}if(p.preferProject){const saved=(await this.makers.project?.conversations('advice',{prefix:portable,id:p.id}))?.find(r=>r.id===p.id);if(saved&&(saved.revisionAt??saved.updatedAt)>(record.revisionAt??record.updatedAt)){record=saved;record.portableSource=true;}}if(portable&&record.portableSource&&!record.portablePrefix){const saved=(await this.makers.project?.conversations('advice',{prefix:true,id:p.id}))?.find(r=>r.id===p.id);if(saved?.portablePrefix)record.portablePrefix=saved.portablePrefix;}if(record.job){const active=this.jobs.get(record.job.id);if(active){if(active.status==='running'&&active.phase!=='saving'){try{const latest=await this.makers.runner.request('read',{session_id:active.session_id});if(active.status==='running'&&active.phase!=='saving')Object.assign(active,latest);}catch(e){active.read_error=e.message;}}record.job=clone(active);}else if(record.job.status==='running')record.job={...record.job,status:'interrupted'};}return record;}
 async list(){
  await fs.mkdir(this.root,{recursive:true});const records=new Map(),add=value=>{const previous=records.get(value.id);if(!previous||(value.revisionAt??value.updatedAt)>(previous.revisionAt??previous.updatedAt))records.set(value.id,{id:value.id,role:value.role,target:value.target,updatedAt:value.updatedAt,revisionAt:value.revisionAt,turns:value.turns.length,focus:value.focus});};
  for(const name of await fs.readdir(this.root)){if(name==='ui.json'||!/^[a-z0-9-]+\.json$/.test(name))continue;add(JSON.parse(await fs.readFile(path.join(this.root,name),'utf8')));}
  for(const value of await this.makers.project?.conversations('advice',{detail:false})??[])add(value);
  return [...records.values()].sort((a,b)=>b.updatedAt-a.updatedAt);
 }

 async snapshot(p,target,branch,parent){
  const work=p.workspace?await this.rpc('studio_read',{id:p.workspace}):null;
  const document=clone(work?.kind==='network'?JSON.parse(work.files['network.json']):p.document??(await this.rpc('studio_state')).live.document);if(document?.network?.version!==8||!Array.isArray(document.network.nodes)||!document.files)throw Error('咨询需要当前网络快照');
  for(const node of document.network.nodes)node.context_cursor=null;
  const catalog=await this.rpc('studio_catalog'),modules=new Set(document.network.nodes.flatMap(n=>Object.keys(n.modules??{})));if(target.module)modules.add(target.module);
  const resources={},snapshotTarget=clone(target);await Promise.all([...modules].map(async id=>{if(catalog.library[id])resources[id]=await this.rpc('studio_release_read',{module:id});}));
  if(work&&work.kind!=='network'){const manifest=JSON.parse(work.files['module.json']);snapshotTarget.module=manifest.id;snapshotTarget.id=manifest.id;resources[manifest.id]={files:work.files,release:{id:manifest.id,version:manifest.version,digest:work.digest,manifest}};}
  let preset;if(target.kind==='preset'){const stored=await storedNetworks(this.directory).load(target.id);preset={id:stored.id,name:stored.name,file:stored.file,display_folder:stored.display_folder,document:JSON.parse(await fs.readFile(stored.file,'utf8'))};for(const n of preset.document.network.nodes)n.context_cursor=null;for(const id of new Set(preset.document.network.nodes.flatMap(n=>Object.keys(n.modules??{}))))if(!resources[id]&&catalog.library[id])resources[id]=await this.rpc('studio_release_read',{module:id});}
  const selection={nodes:(p.selection?.nodes??[]).filter(id=>document.network.nodes.some(n=>n.node_id===id)),edges:clone(p.selection?.edges??[])};
  let previous=null;if(parent){try{previous=await this.getSnapshot(parent);}catch(e){if(!/not a valid object|bad object|not a tree|unknown revision|does not exist|invalid object/i.test(e.message))throw e;parent=null;}}
  const value={document,selection,target:snapshotTarget,resources,preset,...(work?{workspace:work.id}:{}),tools:(await this.catalog()).tools,observerIndex:indexNetwork(document,previous?.observerIndex),...(preset?{presetIndex:indexNetwork(preset.document,previous?.presetIndex)}:{}),createdAt:Date.now()};const digest=hash(value),id=await this.history.write(splitSnapshot(value),{branch,parent,message:'咨询网络与资源快照'});return {id,digest,branch,nodes:document.network.nodes.length,selection,createdAt:value.createdAt};
 }
 stateFile(){return this.makers.project?path.join(this.makers.project.directory,'.nexarbor/ui/agent-conversations.json'):path.join(this.root,'preferences/active.json');}
 async current(){try{return JSON.parse(await fs.readFile(this.stateFile(),'utf8'));}catch(e){if(e.code==='ENOENT')return {};throw e;}}
 async remember(record){const current=await this.current();current[record.role]=record.id;await this.atomic(this.stateFile(),current);}
 target(value,role){
  const target=clone(value??(role==='network'?{kind:'network',name:'当前网络'}:{kind:'component',name:'模块／工具制作'}));
  if(target.kind==='module')target.module=target.id;
  if(target.kind==='tool'&&target.id?.startsWith('module:'))target.module=target.id.slice(7).split('/')[0];
  if(!['network','component','module','tool','preset'].includes(target.kind))throw Error('咨询对象无效');
  if(role==='component'&&!['component','module','tool'].includes(target.kind))throw Error('模块 Agent 需要模块或工具对象');
  return target;
 }
 key(target,role){if(role==='network'&&target.kind!=='preset')return 'network:'+path.relative(this.makers.project?.directory??this.directory,this.directory).replaceAll('\\','/');return target.module?'module:'+target.module:target.kind==='network'?'network:'+path.relative(this.makers.project?.directory??this.directory,this.directory).replaceAll('\\','/'):target.kind+':'+(target.id??'new');}
 async focus(p,record){
  if(!p.target&&!p.workspace&&record.focus)return clone(record.focus);
  let target=this.target(p.target??record.focus?.target??record.target,p.role??record.role),workspace=p.workspace,explicitKey;
  if(workspace){const work=await this.rpc('studio_read',{id:workspace});explicitKey=Object.entries(record.workspaces??{}).find(([,entry])=>entry.workspace===workspace)?.[0]??(!work.origin?.source&&!work.origin?.target?'workspace:'+workspace:undefined);if(work.kind==='network'){if(record.role!=='network')throw Error('请选择网络 Agent');if(target.kind==='component')target={kind:'network',name:'当前候选网络'};}else{const manifest=JSON.parse(work.files['module.json']);target={...target,kind:target.kind==='tool'?'tool':'module',id:work.origin?.source?.id??manifest.id,module:work.origin?.source?.id??manifest.id,name:p.target?.name??manifest.name??work.label??manifest.id};}}
  const key=explicitKey??this.key(target,record.role),saved=record.workspaces?.[key]??(record.workspace&&(record.workKey??this.key(record.target,record.role))===key?{workspace:record.workspace}:null);
  return {target,key,...(workspace??saved?.workspace?{workspace:workspace??saved.workspace}:{}),...(p.source_task?{source_task:p.source_task}:{})};
 }
 saveWork(record){if(record.workspace){record.workKey??=this.key(record.target,record.role);record.workspaces={...record.workspaces,[record.workKey]:{workspace:record.workspace,work:record.work}};}}
 async useFocus(record){
  this.saveWork(record);const focus=record.focus??await this.focus({},record),saved=record.workspaces?.[focus.key];
  record.target=clone(focus.target);record.workKey=focus.key;record.workspace=focus.workspace??saved?.workspace;record.work=saved?.work;
  if(record.workspace)await this.ensureWorkspace(record);
  this.saveWork(record);
 }
 async open(p){
  if(!['component','network'].includes(p.role))throw Error('咨询角色无效');
  const current=await this.current(),last=p.id??(!p.newConversation?(current[p.role]??(await this.list()).find(r=>r.role===p.role)?.id):null);
  let record;
  if(last){record=await this.read({id:last,preferProject:true});if(record.role!==p.role)throw Error('该对话属于另一个 Agent');}
  else{const target=this.target(p.target,p.role),id=randomUUID(),snapshot=await this.snapshot(p,target,'advice-'+id,null);record={id,role:p.role,target,snapshot,turns:[],updatedAt:Date.now()};}
  record.focus=await this.focus(p,record);
  if(!record.session_id&&record.focus.source_task){const source=this.makers.jobs.get(record.focus.source_task);if(source?.workspace===record.focus.workspace&&source.cursor){record.source_cursor=source.cursor;record.model_signature=source.model_signature;}}
  await this.atomic(this.file(record.id),record,{uiFields:last?['focus','source_cursor','model_signature','portableSource']:undefined,ui:true});await this.remember(record);return this.read({id:record.id});
 }
 async draft(p){
  const record=await this.read(p),value=p.draft??{};
  if(typeof value.text!=='string'||value.text.length>16000||!Array.isArray(value.attachments)||value.attachments.length>8)throw Error('输入草稿无效');
  record.draft=clone(value);await this.atomic(this.file(record.id),record,{uiFields:['draft']});return {id:record.id};
 }
 async getSnapshot(id){return joinSnapshot(await this.history.read(id));}
 async send(p){
  const record=await this.read({...p,preferProject:true},true);if(record.job?.status==='running')throw Error('当前咨询尚未结束');if(typeof p.text!=='string'||p.text.length>16000||!p.text.trim()&&!(p.attachments?.length))throw Error('请输入问题或添加附件');
  await this.useFocus(record);await this.makers.connect();await this.makers.disk();const snapshot=await this.snapshot({...p,workspace:record.workspace},record.target,'advice-'+record.id,record.snapshot.id),id=randomUUID(),job={id,mode:'conversation',kind:record.role==='network'?'network':'module',status:'running',phase:'working',workspace:record.workspace??null,started:Date.now(),deadline:Date.now()+86400000,children:[],hidden_modules:[],allow_component_creation:record.role==='network',allow_network_testing:true,tool_events:[],snapshot,role:record.role};this.jobs.set(id,job);this.activeRecords.set(id,record);
  const cwd=path.join(this.root,'sessions',record.id);await fs.mkdir(cwd,{recursive:true});const created=await this.makers.runner.request('create',{task:id,directory:cwd,name:record.target.name??record.target.id??'当前网络',kind:record.role==='network'?'network':'module',instructions:adviceInstructions(record.role),tools:makerTools(job.kind,true,true),max_steps:100000,...(record.source_cursor?{fork_cursor:record.source_cursor,model_signature:record.model_signature}:{}),...(record.portablePrefix?{portable_prefix:record.portablePrefix}:record.session_id?{resume_session:record.session_id,model_signature:record.model_signature}:{})});Object.assign(job,created);delete record.portablePrefix;delete record.portableSource;delete record.source_cursor;record.session_id=created.session_id;record.model_signature=created.model_signature;record.snapshot=snapshot;record.turns.push({snapshot,target:clone(record.target),workspace:record.workspace,question:p.text,job:id,createdAt:Date.now()});record.job=clone(job);record.updatedAt=Date.now();record.draft={text:'',attachments:[]};await this.atomic(this.file(record.id),record,{ui:true});
  const prompt=`本轮快照 ${snapshot.id}；全网 ${snapshot.nodes} 个节点；重点：${JSON.stringify({target:record.target,selection:snapshot.selection})}\n用户问题：\n${p.text}`;
  this.makers.runner.request('run',{session_id:job.session_id,prompt,attachments:p.attachments??[],timeout:86400}).then(result=>this.finish(record,job,result),error=>this.finish(record,job,{status:'failed',reason:{error:{message:error.message}}})).catch(error=>{job.status='failed';job.history_error=error.message;});return record;
 }
 async finish(record,job,result){
  const status=result.status;Object.assign(job,result,{status:'running',phase:'saving',finished:Date.now()});
  if(record.workspace)try{const work=await this.rpc('studio_read',{id:record.workspace});if(this.makers.project){job.git=await this.makers.project.branch(work);record.work={id:work.id,kind:work.kind,origin:work.origin,module:work.kind==='network'?null:JSON.parse(work.files['module.json']).id,git:job.git};}}catch(error){job.history_error=error.message;}
  if(status!=='completed')job.error=result.reason?.error?.message??'本轮未完成：'+status;
  this.saveWork(record);record.job={...clone(job),status,phase:'answered'};record.updatedAt=Date.now();await this.atomic(this.file(record.id),record);
  if(job.cursor&&this.makers.project)try{const prefix=await this.makers.runner.request('export-context',{cursor:job.cursor});await this.serialPersistence(async()=>{const latest=JSON.parse(await fs.readFile(this.file(record.id),'utf8'));if(latest.job?.id===job.id)await this.makers.project.conversation('advice',latest,prefix);});}catch(error){job.history_error=error.message;}
  job.status=status;job.phase='answered';
 }

 async cancel(p){const record=await this.read(p),job=this.jobs.get(record.job?.id);if(job?.status==='running'){await this.makers.runner.request('cancel',{session_id:job.session_id});job.status='cancelled';record.job=clone(job);await this.atomic(this.file(record.id),record);}return record;}
 async tool(p){
  const job=this.jobs.get(p.task);if(job?.status!=='running'||!(p.tool==='inspect_network'||adviceTools.some(t=>t.name===p.tool)||makerTools(job.kind,true,true).some(t=>t.name===p.tool)))throw Error('会话已停止或工具不存在');
  const observing=adviceTools.some(t=>t.name===p.tool)||p.tool==='inspect_network';
  if(!observing){const record=this.activeRecords.get(job.id);await this.ensureWorkspace(record,job);const value=await this.makers.executeTool(job,p);if(job.workspace!==record.workspace){record.workspace=job.workspace;const work=await this.rpc('studio_read',{id:job.workspace});record.work={id:work.id,kind:work.kind,origin:work.origin,module:work.kind==='network'?null:JSON.parse(work.files['module.json']).id,git:job.git};}this.saveWork(record);record.job=clone(job);await this.atomic(this.file(record.id),record);return value;}
  job.tool_events.push({tool:p.tool,arguments:p.arguments,time:Date.now()});
  if(this.makers.projectObservations.uses(job.id,p.arguments??{}))return this.makers.observe(job,p.tool,p.arguments??{});
  if(p.arguments?.source)this.makers.projectObservations.clear(job.id);
  const s=await this.getSnapshot(job.snapshot.id),a=p.arguments??{},slice=text=>({total_lines:String(text).split('\n').length,text:String(text).split('\n').slice(Math.max(0,(a.start_line??1)-1),Math.max(0,(a.start_line??1)-1)+Math.min(300,Math.max(1,a.line_count??120))).join('\n')});
  if(job.workspace&&(a.source==='candidate'||a.source==='environment'||job.kind==='network'&&a.source!=='current')&&p.tool!=='inspect_network')return this.makers.observe(job,p.tool,a);
  if(observerTools.some(t=>t.name===p.tool))return new NetworkObserver(s.target?.kind==='preset'&&s.preset?{...s,document:s.preset.document,observerIndex:s.presetIndex,selection:{nodes:[],edges:[]}}:s,job.snapshot.id,this.views(job.id??p.task)).execute(p.tool,a,scene=>this.renderer.render(scene));
  if(p.tool==='read_network_text')return readObservedText(s.target?.kind==='preset'&&s.preset?{...s,document:s.preset.document}:s,job.snapshot.id,a);
  if(p.tool==='inspect_network'){
   responseFormat(a.response_format);
   if(a.file){if(!Object.hasOwn(s.document.files,a.file))throw Error('文件不在本轮快照内');const content=s.document.files[a.file];if(typeof content!=='string')return {file:a.file,binary:true};return {file:a.file,...slice(content)};}
   return inspectNetwork(s,job.snapshot.id,a);
  }
  const id=a.module??s.target.module,resource=s.resources[id];if(!resource){const t=s.tools.find(t=>t.ref===s.target.id);if(t)return {tool:t,source:'外部工具，仅提供登记的接口；不推断其内部实现'};throw Error('模块不在本轮源码快照内');}
  if(a.file){if(!Object.hasOwn(resource.files,a.file))throw Error('文件不在本轮模块源码内');return {module:id,version:resource.release.version,digest:resource.release.digest,file:a.file,...slice(resource.files[a.file])};}
  return {module:id,name:resource.release.manifest.name,description:resource.release.manifest.description,files:Object.keys(resource.files),version:resource.release.version,hint:'接口摘要或 Schema 用 inspect_modules；文档、源码按文件名和行读取。'};
 }
 async ensureWorkspace(record,job){
  if(!record)throw Error('当前会话记录不存在');
  if(record.workspace){try{const work=await this.rpc('studio_read',{id:record.workspace});if(job)job.workspace=record.workspace;return work;}catch(error){if(!/not found|does not exist|Unknown work copy|ENOENT|不存在|工作副本/.test(error.message)||!record.work)throw error;const files=await this.makers.project.workFiles(record.work),manifest=record.work.kind==='network'?null:JSON.parse(files['module.json']);const work=await this.rpc('studio_revision',{kind:record.work.kind,preserve_identity:true,source:manifest?{files,release:{id:manifest.id,version:manifest.version,manifest}}:undefined,document:manifest?undefined:JSON.parse(files['network.json']),runtime:!manifest&&files['runtime.json']?JSON.parse(files['runtime.json']):undefined,origin:{...record.work.origin,git_lineage:[record.work.id,...(record.work.origin?.git_lineage??[])],advice:record.id},reference:'从 Git 恢复此前工作分支。'});record.workspace=work.id;const git=await this.makers.project.branch(work);record.work={id:work.id,kind:work.kind,origin:work.origin,module:manifest?JSON.parse(work.files['module.json']).id:null,git};if(job)job.workspace=work.id;await this.atomic(this.file(record.id),record);return work;}}
  if(this.workloads.has(record.id))return this.workloads.get(record.id);
  const loading=(async()=>{const snapshot=await this.getSnapshot(record.snapshot.id),source=snapshot.resources[record.target.module],kind=record.role==='network'?'network':record.target.kind==='tool'?'tool':'module';
   if(kind!=='network'&&record.target.module&&!source)throw Error('当前模块源码不可用：'+record.target.module);
   const work=kind!=='network'&&!source?await this.rpc('studio_create',{kind,sample:'blank'}):await this.rpc('studio_revision',{kind,source:kind==='network'?undefined:source,document:kind==='network'?(snapshot.preset?.document??snapshot.document):undefined,runtime:kind==='network'?(snapshot.preset?.runtime??await this.rpc('studio_runtime_settings')):undefined,origin:{advice:record.id,consult_cursor:record.job?.cursor,snapshot:record.snapshot.id,target:record.target,source:source?.release?{id:source.release.id,version:source.release.version,digest:source.release.digest}:null},reference:JSON.stringify({questionHistory:record.turns.map(t=>t.question),selection:snapshot.selection,target:record.target,document:snapshot.document},null,2),display_folder:snapshot.preset?.display_folder});
   if(this.makers.project)work.git=await this.makers.project.branch(work);record.work={id:work.id,kind:work.kind,origin:work.origin,module:kind==='network'?null:JSON.parse(work.files['module.json']).id,git:work.git};record.workspace=work.id;if(record.focus?.key===record.workKey)record.focus.workspace=work.id;this.saveWork(record);if(job)job.workspace=work.id;record.revisions??=[];record.revisions.push({workspace:work.id,createdAt:Date.now()});await this.atomic(this.file(record.id),record);return work;})();this.workloads.set(record.id,loading);try{return await loading;}finally{this.workloads.delete(record.id);}
 }
 async modify(p){const record=await this.read(p);if(record.job?.status==='running')throw Error('请等待当前操作结束');await this.useFocus(record);if(!record.workspace)record.snapshot=await this.snapshot(p,record.target,'advice-'+record.id,record.snapshot.id);const work=await this.ensureWorkspace(record);this.saveWork(record);await this.atomic(this.file(record.id),record);return {...work,advice:record.id};}

 async ui(p){const file=path.join(this.root,'ui.json');let value={};try{value=JSON.parse(await fs.readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}if(p?.key){if(!['studio','advisor'].includes(p.key))throw Error('布局名称无效');value[p.key]=p.value;await this.atomic(file,value);}return value;}
 async close(){this.renderer.close();for(const job of this.jobs.values())if(job.status==='running'){job.status='interrupted';await this.makers.runner?.request('cancel',{session_id:job.session_id}).catch(()=>{});}}
 async request(method,p={}){if(!['open','read','list','send','cancel','modify','ui','draft'].includes(method))throw Error('未知咨询操作');if(['open','send','modify','ui','draft'].includes(method)){const task=this.queue.then(()=>this[method](p));this.queue=task.catch(()=>{});return task;}return this[method](p);}
}
