// Packaged knowledge, not user/project files. Only these references may be read.
const fs=require('node:fs/promises'),path=require('node:path'),{createHash}=require('node:crypto');
const name='inspect-network',directory=path.join(__dirname,'../skills',name);
const references=['references/理解整体与局部.md','references/解释模块与配置.md','references/追踪连接与可达性.md'];
exports.toolNames=new Set(['view_network','inspect_nodes','inspect_edges','inspect_modules','read_resource','read_network_text']);
let pending;
exports.loadedInHistory=events=>{
 const calls=new Set();
 for(const event of events){
  if(event.type==='user/message'&&event.data.source?.kind==='skill-invocation'&&event.data.source.name===name)return true;
  if(event.type==='tool/call'&&event.data.name==='skill'){
   let args=event.data.arguments;try{if(typeof args==='string')args=JSON.parse(args);}catch{continue;}
   if(args?.name===name)calls.add(event.data.callId);
  }
  if(event.type==='tool/result'&&!event.data.message?.isError&&calls.has(event.data.message?.toolCallId??event.data.message?.callId))return true;
 }
 return false;
};
exports.bundle=()=>pending??=(async()=>{
 const entry=await fs.readFile(path.join(directory,'SKILL.md'),'utf8'),files=Object.fromEntries(await Promise.all(references.map(async file=>[file,await fs.readFile(path.join(directory,file),'utf8')])));
 const header=/^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n/.exec(entry);if(!header||header[1]!==name)throw Error('网络 Skill 入口无效');
 return {name,description:header[2],content:entry.slice(header[0].length).trim(),files,revision:createHash('sha256').update(JSON.stringify([entry,files])).digest('hex')};
})();
exports.install=async(runtime,entry,definitions,register)=>{
 if(!definitions.some(t=>t.name==='view_network'))return;
 const skill=await exports.bundle();
 const nativeLoader=runtime.native('dsh-tool-skill');
 const scope=entry.agent.ctx.plugin({name:'nexarbor-network-skill',inject:nativeLoader.inject,apply(ctx){
 entry.tools.push(ctx.skills.register({name,description:skill.description,content:skill.content,source:'bundled',resourceBase:{kind:'opaque',description:'使用 read_skill_reference，file 为本 Skill 内相对路径。'}}));
 // Mount the native loader in this agent's scope, preserving its catalog identity.
 nativeLoader.apply(ctx);
 const activate=()=>{
  if(entry.networkSkillLoaded)return;entry.networkSkillLoaded=true;
  for(const definition of definitions)register(definition);
  entry.tools.push(ctx.tools.register({name:'read_skill_reference',description:'按需读取查看网络 Skill 的参考；省略 file 列出参考。',parameters:{type:'object',properties:{file:{type:'string',enum:references}},additionalProperties:false},output:{schema:{},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},execute:async({file})=>{if(file===undefined)return {skill:name,files:references};if(!Object.hasOwn(skill.files,file))throw Error('参考不属于此 Skill');return {skill:name,file,text:skill.files[file]};}}));
 };
 entry.tools.push(ctx.on('tools/result',(exec,result)=>{if(exec.name==='skill'&&exec.arguments?.name===name&&!result.isError)activate();}));
 entry.tools.push(ctx.on('agent/pre-step',async(p,next)=>{const decision=await next();const explicit=p.messages.some(m=>m.source?.kind==='user'&&m.content?.some(b=>b.type==='text'&&/(^|\s)\/inspect-network(?=\s|$)/.test(b.text)));if(decision.kind!=='reject'&&(explicit||decision.messages?.some(m=>m.source?.kind==='skill-invocation'&&m.source.name===name)))activate();return decision;}));
 // Restore discovery after resume/fork, using successful durable calls, never arbitrary user text.
 if(exports.loadedInHistory(entry.agent.session.snapshotEvents()))activate();
 }});entry.tools.push(()=>scope.dispose());
};
