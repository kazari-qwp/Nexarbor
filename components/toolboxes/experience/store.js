import {mkdir,readFile,writeFile,rename,rm} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const writeQueues=new Map();
const kinds=new Set(['common','tool','toolbox','role','node']);
function text(value,name,max=1000){if(typeof value!=='string'||!value.trim()||value.length>max)throw new Error(`Invalid ${name}`);return value.trim()}
function validate(input){
 const applies=input.applies;if(!Array.isArray(applies)||!applies.length||applies.length>12)throw new Error('applies requires 1-12 selectors');
 const selectors=applies.map(x=>{if(!kinds.has(x.kind))throw new Error('Unknown experience selector');return {kind:x.kind,id:text(x.id,'selector',160)}});
 return {applies:selectors,trigger:text(input.trigger,'trigger',240),advice:text(input.advice,'advice'),evidence:text(input.evidence,'evidence'),version:text(input.version,'version',100),core:input.core===true};
}
export class ExperienceStore {
 constructor(directory){this.directory=path.resolve(directory);this.file=path.join(this.directory,'library.json')}
 async init(seed=[]){await mkdir(this.directory,{recursive:true});try{const current=await this.read();if(seed.some(e=>!current.entries.some(x=>x.id===e.id)))await this.mutate(db=>{for(const entry of seed)if(!db.entries.some(x=>x.id===entry.id))db.entries.push({...validate(entry),id:text(entry.id,'id',160),status:'verified',author:'framework',reviewer:'framework',created_at:new Date().toISOString()})})}catch(e){if(e.code!=='ENOENT')throw e;try{await this.mutate(db=>{for(const entry of seed)db.entries.push({...validate(entry),id:text(entry.id,'id',160),status:'verified',author:'framework',reviewer:'framework',created_at:new Date().toISOString()})})}catch(e){if(e.code!=='EEXIST')throw e;await this.read()}}}
 async read(){const db=JSON.parse(await readFile(this.file,'utf8'));if(db.format!==1||!Array.isArray(db.entries))throw new Error('Invalid experience library');return db}
 async mutate(fn){
  const prior=writeQueues.get(this.file)??Promise.resolve();const next=prior.then(()=>this.writeMutation(fn));const tail=next.catch(()=>{});writeQueues.set(this.file,tail);try{return await next}finally{if(writeQueues.get(this.file)===tail)writeQueues.delete(this.file)}
 }
 async writeMutation(fn){
  const lock=path.join(this.directory,'.write-lock');await mkdir(lock);let temp;
  try{let db;try{db=await this.read()}catch(e){if(e.code!=='ENOENT')throw e;db={format:1,entries:[],reviews:[]}}
   const result=await fn(db);temp=path.join(this.directory,randomUUID()+'.tmp');await writeFile(temp,JSON.stringify(db,null,2),'utf8');await rename(temp,this.file);return result;
  }finally{if(temp)await rm(temp,{force:true});await rm(lock,{recursive:true,force:true})}
 }
 async query({selectors=[],ids=[],exclude_ids=[],query='',status='all',limit=6,offset=0,core_only=false}={}){
  if(!Number.isInteger(limit)||limit<1||limit>10)throw new Error('limit must be 1-10');
  if(!Number.isInteger(offset)||offset<0)throw new Error('Invalid offset');
  if(!['all','verified','pending','retired','rejected','merged'].includes(status))throw new Error('Invalid experience status');
  const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const entries=(await this.read()).entries.filter(e=>(!core_only||e.core===true)&&(status==='all'?['verified','pending'].includes(e.status):e.status===status)&&(!ids.length||ids.includes(e.id))&&!exclude_ids.includes(e.id)&&(!selectors.length||e.applies.some(a=>selectors.some(s=>s.kind===a.kind&&s.id===a.id)))&&(!words.length||words.every(w=>JSON.stringify([e.trigger,e.advice,e.applies]).toLowerCase().includes(w))));
  return entries.slice(offset,offset+limit);
 }
 async submit(input,actor){const entry={...validate(input),core:false,id:randomUUID(),status:'pending',author:actor,created_at:new Date().toISOString()};await this.mutate(db=>db.entries.push(entry));return {id:entry.id,status:'pending'}}
 async review({id,action,changes,merge_into,core},actor){
  if(!['publish','reject','retire','merge','set_core'].includes(action))throw new Error('Unknown review action');
  return this.mutate(db=>{const entry=db.entries.find(e=>e.id===id);if(!entry)throw new Error('Experience not found');
   if(action==='publish'||action==='reject'||action==='merge'){if(entry.status!=='pending')throw new Error('Only pending experience can be reviewed')}
   if(action==='set_core'){if(entry.status!=='verified'||typeof core!=='boolean')throw new Error('set_core requires verified experience and boolean core');entry.core=core}
   if(action==='retire'&&entry.status!=='verified')throw new Error('Only verified experience can be retired');
   if(changes){if(action!=='publish')throw new Error('changes only apply to publishing');Object.assign(entry,validate({...entry,...changes}))}
   if(action==='merge'){const target=db.entries.find(e=>e.id===merge_into&&e.status==='verified');if(!target)throw new Error('Merge target must be verified');entry.merged_into=target.id}
   if(action!=='set_core')entry.status={publish:'verified',reject:'rejected',retire:'retired',merge:'merged'}[action];entry.promotion_candidate=entry.status==='verified'&&!entry.core&&(entry.success_count??0)>=5;entry.reviewer=actor;entry.reviewed_at=new Date().toISOString();
   db.reviews??=[];db.reviews.push({id,action,actor,time:entry.reviewed_at,entry:structuredClone(entry)});return {id,status:entry.status};
  });
 }
}
export class ExperienceView {
 constructor(store,{actor,role,ids=[],tools=[],toolboxes=[]}={}){this.store=store;this.actor=actor;this.role=role;this.ids=ids;this.tools=tools;this.toolboxes=toolboxes;this.loaded=new Map();this.used=new Set();this.resident=new Set()}
 async startup(){const selectors=[{kind:'common',id:'*'},{kind:'node',id:this.actor},...(this.role?[{kind:'role',id:this.role}]:[]),...this.tools.map(id=>({kind:'tool',id})),...this.toolboxes.filter(id=>id!=='network_management').map(id=>({kind:'toolbox',id}))];const entries=await this.store.query({selectors,status:'verified',core_only:true,limit:10});const explicit=this.ids.length?await this.store.query({ids:this.ids,status:'verified',limit:10}):[];for(const e of [...entries.filter(e=>e.core),...explicit])this.add(e);this.resident=new Set(this.loaded.keys())}
 add(e){if(e.status!=='verified')return false;if(this.loaded.has(e.id)||this.loaded.size>=12)return false;this.loaded.set(e.id,e);return true}
 async use(tool,boxes){const key=JSON.stringify([tool,boxes]);if(this.used.has(key))return [];const entries=await this.store.query({selectors:[{kind:'tool',id:tool},...boxes.map(id=>({kind:'toolbox',id}))],status:'verified',limit:6});const fresh=entries.filter(e=>this.add(e));this.used.add(key);return fresh}
 clearTransient(){for(const id of this.loaded.keys())if(!this.resident.has(id))this.loaded.delete(id);this.used.clear()}
 render({active=false}={}){return (active?'排障时查经验只作参考；待审核不代表可靠，权限不变。\n':'常加载经验：\n')+[...this.loaded.values()].map(e=>`[${e.id}; ${e.version}] ${e.trigger}：${e.advice}`).join('\n')}
}
