// Native Skill discovery and read-only resources, shared by studio and graph agents.
exports.loadedInHistory=(events,name)=>{
 const calls=new Set();
 for(const event of events){
  if(event.type==='user/message'&&event.data.source?.kind==='skill-invocation'&&event.data.source.name===name)return true;
  if(event.type==='tool/call'&&event.data.name==='skill'){
   let args=event.data.arguments;try{if(typeof args==='string')args=JSON.parse(args);}catch{continue;}
   if(args?.name===name&&typeof event.data.callId==='string')calls.add(event.data.callId);
  }
  if(event.type==='tool/result'&&!event.data.message?.isError&&calls.has(event.data.message?.toolCallId??event.data.message?.callId))return true;
 }
 return false;
};
exports.mount=async(runtime,entry,bundles,onActivate=()=>{})=>{
 if(!bundles.length)return;
 const names=bundles.map(s=>s.name);if(new Set(names).size!==names.length)throw Error('Skill 名称重复');
 const byName=new Map(bundles.map(s=>[s.name,s])),active=new Set(),nativeLoader=runtime.native('dsh-tool-skill');
 const scope=entry.agent.ctx.plugin({name:'nexarbor-skills',inject:nativeLoader.inject,apply(ctx){
  for(const skill of bundles)entry.tools.push(ctx.skills.register({name:skill.name,description:skill.description,content:skill.content,source:skill.source??'bundled',resourceBase:{kind:'opaque',description:'使用 read_skill_reference；skill 为名称，file 为该 Skill 内相对路径。'}}));
  nativeLoader.apply(ctx);
  let reader=false;
  const activate=name=>{
   if(!byName.has(name)||active.has(name))return;active.add(name);onActivate(name);
   if(reader)return;reader=true;
   entry.tools.push(ctx.tools.register({name:'read_skill_reference',description:'按需读取已加载 Skill 的参考；省略 file 列目录。',parameters:{type:'object',properties:{skill:{type:'string',enum:names},file:{type:'string'},start_line:{type:'integer',minimum:1},line_count:{type:'integer',minimum:1,maximum:400}},additionalProperties:false},output:{schema:{},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},execute:async args=>{
    if(args.skill&&!active.has(args.skill))throw Error('请先用 skill 加载 '+args.skill);
    const candidates=bundles.filter(s=>active.has(s.name)&&(!args.skill||s.name===args.skill));
    if(args.file===undefined)return {skills:candidates.map(s=>({name:s.name,files:Object.keys(s.files??{})}))};
    const matches=candidates.filter(s=>Object.hasOwn(s.files??{},args.file));if(matches.length!==1)throw Error(matches.length?'请用 skill 参数指定参考所属 Skill':'参考不属于已加载 Skill');
    const skill=matches[0],lines=skill.files[args.file].split('\n'),start=args.start_line??1,count=args.line_count??200;
    if(!Number.isInteger(start)||start<1||!Number.isInteger(count)||count<1||count>400)throw Error('参考行号无效，每次最多400行');
    return {skill:skill.name,file:args.file,start_line:start,total_lines:lines.length,text:lines.slice(start-1,start-1+count).join('\n'),more:start-1+count<lines.length};
   }}));
  };
  entry.tools.push(ctx.on('tools/result',(exec,result)=>{if(exec.name==='skill'&&!result.isError)activate(exec.arguments?.name);}));
  entry.tools.push(ctx.on('agent/pre-step',async(p,next)=>{const decision=await next();if(decision.kind==='reject')return decision;
   for(const m of p.messages)if(m.source?.kind==='user')for(const b of m.content??[])if(b.type==='text')for(const match of b.text.matchAll(/(^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)/g))activate(match[2]);
   for(const m of decision.messages??[])if(m.source?.kind==='skill-invocation')activate(m.source.name);return decision;
  }));
  const events=entry.agent.session.snapshotEvents();for(const name of names)if(exports.loadedInHistory(events,name))activate(name);
 }});entry.tools.push(()=>scope.dispose());
};
