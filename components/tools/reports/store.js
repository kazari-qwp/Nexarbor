import { mkdir, readdir, readFile, writeFile, rename, appendFile, realpath } from 'node:fs/promises';
import path from 'node:path';

import {uuidv7,redactText} from '../../../adapters/harness/framework/record-utils.js';
export {uuidv7,redactText};
const terminal=new Set(['completed','failed','blocked','interrupted']);
const now=()=>new Date().toISOString();
const serialize=(value,space)=>JSON.stringify(value,(_key,item)=>typeof item==='string'?redactText(item):item,space);
export class ReportStore {
  constructor(directory){this.directory=path.resolve(directory);this.requests=new Map();this.contexts=new WeakMap();this.tail=Promise.resolve();}
  enqueue(fn){const next=this.tail.then(fn);this.tail=next.catch(()=>{});return next;}
  file(q,relative){return path.join(this.directory,q.root_request_id,...relative.split('/'));}
  async atomic(file,value){await mkdir(path.dirname(file),{recursive:true});const temp=file+'.'+uuidv7()+'.tmp';await writeFile(temp,serialize(value,2),'utf8');await rename(temp,file);}
  async init(){await mkdir(this.directory,{recursive:true});for(const entry of await readdir(this.directory,{withFileTypes:true})){
    if(!entry.isDirectory())continue;let q;
    try{q=JSON.parse(await readFile(path.join(this.directory,entry.name,'manifest.json'),'utf8'));}catch(error){if(error.code==='ENOENT')continue;throw error;}
    this.requests.set(q.root_request_id,q);let changed=false;
    for(const d of Object.values(q.delegations)){for(const run of d.runs)if(run.status==='running'){run.status='interrupted';run.finished_at=now();run.error='宿主重启，执行结果未确认';changed=true;await this.atomic(this.file(q,run.files.metadata),run);}if(d.status==='running'){d.status='interrupted';changed=true;await this.atomic(this.file(q,d.path+'/delegation.json'),d);}}
    if(changed)await this.persist(q);
  }}
  listing(d){const {task,...entry}=d;return {...entry,task_preview:task.slice(0,160),delegation_path:d.path+'/delegation.json'};}
  index(q,actor){const nodes=Object.create(null);for(const d of Object.values(q.delegations)){if(d.kind==='discussion'||(actor!==undefined&&!this.allowed(q,d,actor)))continue;(nodes[d.target_node_id]??=[]).push(this.listing(d));}return {version:1,root_request_id:q.root_request_id,nodes};}
  topology(q,actor){return {version:1,root_request_id:q.root_request_id,delegations:Object.values(q.delegations).filter(d=>actor===undefined||this.allowed(q,d,actor)).map(d=>{const {runs,...entry}=this.listing(d);return {...entry,run_ids:runs.map(r=>r.run_id)};})};}
  async persist(q){await this.atomic(this.file(q,'manifest.json'),q);await this.atomic(this.file(q,'topology.json'),this.topology(q));await this.atomic(this.file(q,'node-index.json'),this.index(q));}
  context(ac){return this.contexts.get(ac);}
  restoreContext(ac,actor,sessionId){let latest;for(const q of this.requests.values())for(const d of Object.values(q.delegations))if(d.target_node_id===actor)for(const run of d.runs)if(run.session_id===sessionId&&(!latest||run.started_at>=latest.started_at))latest={root_request_id:q.root_request_id,delegation_id:d.delegation_id,run_id:run.run_id,started_at:run.started_at};if(latest)this.contexts.set(ac,latest);}
  hasDelegated(actor){return [...this.requests.values()].some(q=>Object.values(q.delegations).some(d=>d.kind!=='request'&&d.caller_node_id===actor));}
  hasArchiveGrant(actor){return [...this.requests.values()].some(q=>(q.archive_grants??[]).some(g=>g.actor===actor));}
  async startRun(ac,meta,runId,task=''){return this.enqueue(async()=>{
    let c=this.context(ac),q=c&&this.requests.get(c.root_request_id),d=q?.delegations[c.delegation_id];
    if(c?.run_id&&terminal.has(d?.runs.find(r=>r.run_id===c.run_id)?.status))d=null;
    if(!d){const rootId=uuidv7(),id=uuidv7();q={version:1,root_request_id:rootId,created_at:now(),origin_node_id:meta.node_id,delegations:{},archive_grants:[]};d={delegation_id:id,parent_delegation_id:null,caller_run_id:null,caller_node_id:meta.node_id,target_node_id:meta.node_id,sequence:1,kind:'request',task:redactText(task),created_at:now(),status:'running',path:'delegations/001_'+id,runs:[]};q.delegations[id]=d;this.requests.set(rootId,q);c={root_request_id:rootId,delegation_id:id};}
    const base=d.path+'/runs/'+runId,run={run_id:runId,node_id:meta.node_id,session_id:meta.session_id,status:'running',started_at:now(),files:{metadata:base+'/metadata.json',tools:base+'/tools.jsonl',transcript:base+'/transcript.jsonl'},tool_sequence:0};
    d.runs.push(run);d.status='running';c={...c,run_id:runId};this.contexts.set(ac,c);
    await this.atomic(this.file(q,d.path+'/delegation.json'),d);await this.atomic(this.file(q,run.files.metadata),run);await writeFile(this.file(q,run.files.tools),'','utf8');await writeFile(this.file(q,run.files.transcript),'','utf8');await this.persist(q);return this.reference(c);
  });}
  async delegate(ac,{target,task,kind='agent',round,parent,receiver,retry_of}){return this.enqueue(async()=>{
    const caller=this.context(ac);if(!caller)throw new Error('Caller run has not started');const q=this.requests.get(caller.root_request_id),parentId=parent?.delegation_id??caller.delegation_id,p=q.delegations[parentId];if(!p)throw new Error('Unknown parent delegation');
    const sequence=Object.values(q.delegations).filter(d=>d.parent_delegation_id===parentId).length+1,id=uuidv7();
    const d={delegation_id:id,parent_delegation_id:parentId,caller_run_id:caller.run_id,caller_node_id:q.delegations[caller.delegation_id].target_node_id,target_node_id:target,sequence,kind,task:redactText(task),...(round?{round}:{}),...(retry_of?{retry_of}:{}),created_at:now(),status:'running',path:p.path+'/children/'+String(sequence).padStart(3,'0')+'_'+id,runs:[]};q.delegations[id]=d;
    const c={root_request_id:caller.root_request_id,delegation_id:id};if(receiver)this.contexts.set(receiver,c);await this.atomic(this.file(q,d.path+'/delegation.json'),d);await this.persist(q);return c;
  });}
  async endDelegation(c,status,error){return this.enqueue(async()=>{const q=this.requests.get(c.root_request_id),d=q?.delegations[c.delegation_id];if(!d)return;d.status=status;d.finished_at=now();if(error)d.error=redactText(error);await this.atomic(this.file(q,d.path+'/delegation.json'),d);await this.persist(q);});}
  reference(c){if(!c)return null;const q=this.requests.get(c.root_request_id),d=q?.delegations[c.delegation_id],run=d?.runs.find(r=>r.run_id===c.run_id);return {root_request_id:c.root_request_id,delegation_id:c.delegation_id,...(run?{run_id:run.run_id,files:{...run.files}}:{})};}
  run(ac){const c=this.context(ac),q=c&&this.requests.get(c.root_request_id),d=q?.delegations[c.delegation_id],run=d?.runs.find(r=>r.run_id===c.run_id);return {c,q,d,run};}
  async tool(ac,exec,result){if(!this.context(ac)?.run_id)return;return this.enqueue(async()=>{const {q,run}=this.run(ac);if(!run)return;const event={sequence:++run.tool_sequence,time:now(),call_id:exec.callId??exec.id??null,tool:exec.name,arguments:exec.arguments,result:{isError:result.isError??false,value:result.value,content:result.content}};await appendFile(this.file(q,run.files.tools),serialize(event)+'\n','utf8');});}
  async submission(ac,value){return this.enqueue(async()=>{const {q,d,run}=this.run(ac);if(!run)return;run.files.submission=d.path+'/runs/'+run.run_id+'/submission.json';await this.atomic(this.file(q,run.files.submission),value);await this.persist(q);});}
  async artifact(ac,value){return this.enqueue(async()=>{const {q,d,run}=this.run(ac);if(!run)return;run.files.output=d.path+'/runs/'+run.run_id+'/artifacts/output.md';await mkdir(path.dirname(this.file(q,run.files.output)),{recursive:true});await writeFile(this.file(q,run.files.output),redactText(value),'utf8');await this.persist(q);});}
  async finish(ac,status,report,error,messages=[]){if(!this.context(ac)?.run_id)return;await this.enqueue(async()=>{const {q,d,run}=this.run(ac);if(!run||terminal.has(run.status))return;run.status=status;run.finished_at=now();const base=d.path+'/runs/'+run.run_id;
    if(status==='completed'&&report?.trim()){run.files.report=base+'/report.md';await writeFile(this.file(q,run.files.report),redactText(report),'utf8');}
    if(error){run.error=redactText(error);run.files.error=base+'/error.json';await this.atomic(this.file(q,run.files.error),{status,error:run.error});}
    await writeFile(this.file(q,run.files.transcript),messages.map(m=>serialize(m)).join('\n')+(messages.length?'\n':''),'utf8');await this.atomic(this.file(q,run.files.metadata),run);d.status=status;d.finished_at=run.finished_at;await this.atomic(this.file(q,d.path+'/delegation.json'),d);await this.persist(q);
  });}
  async archiveGrant(actor,c){await this.enqueue(async()=>{const q=this.requests.get(c.root_request_id);if(!q.archive_grants.some(g=>g.actor===actor&&g.delegation_id===c.delegation_id))q.archive_grants.push({actor,delegation_id:c.delegation_id});await this.persist(q);});}
  isDescendant(q,id,ancestor){for(let d=q.delegations[id];d;d=q.delegations[d.parent_delegation_id])if(d.delegation_id===ancestor)return true;return false;}
  allowed(q,d,actor){return d.target_node_id===actor||Object.values(q.delegations).some(p=>p.caller_node_id===actor&&this.isDescendant(q,d.delegation_id,p.delegation_id))||(q.archive_grants??[]).some(g=>g.actor===actor&&this.isDescendant(q,d.delegation_id,g.delegation_id));}
  async query(actor,{root_request_id,delegation_id,node_id,offset=0,limit=20}={}){await this.tail;const items=[];for(const q of this.requests.values()){if(root_request_id&&q.root_request_id!==root_request_id)continue;const selected=delegation_id&&q.delegations[delegation_id];if(delegation_id&&(!selected||!this.allowed(q,selected,actor)))continue;
    for(const d of Object.values(q.delegations)){if(!this.allowed(q,d,actor)||(delegation_id&&!this.isDescendant(q,d.delegation_id,delegation_id))||(node_id&&d.target_node_id!==node_id))continue;items.push({root_request_id:q.root_request_id,...this.listing(d)});}}
    items.sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.sequence-b.sequence);return {items:items.slice(offset,offset+limit),offset,total:items.length,has_more:offset+limit<items.length,next_offset:offset+limit<items.length?offset+limit:null};}
  async read(actor,{root_request_id,path:relative,offset=0,limit=12000}){await this.tail;const q=this.requests.get(root_request_id);if(!q)throw new Error('Report request not found');if(typeof relative!=='string'||relative.includes('\\')||relative.split('/').some(p=>p==='..'||p==='.'||!p)||path.isAbsolute(relative))throw new Error('Invalid report path');
    let content;if(relative==='node-index.json'||relative==='topology.json'){if(!Object.values(q.delegations).some(d=>this.allowed(q,d,actor)))throw new Error('Report request is outside grant');content=serialize(relative==='node-index.json'?this.index(q,actor):this.topology(q,actor),2);}
    else{let owner;for(const d of Object.values(q.delegations)){if(relative===d.path+'/delegation.json')owner=d;for(const run of d.runs)if(Object.values(run.files).includes(relative))owner=d;}if(!owner||!this.allowed(q,owner,actor))throw new Error('Report file is outside delegated or archive grant');
      const base=await realpath(path.join(this.directory,q.root_request_id)),file=await realpath(this.file(q,relative)),check=path.relative(base,file);if(check==='..'||check.startsWith('..'+path.sep)||path.isAbsolute(check))throw new Error('Report file escapes request directory');const raw=await readFile(file,'utf8');content=relative.endsWith('.json')?serialize(JSON.parse(raw),2):relative.endsWith('.jsonl')?raw.split('\n').filter(Boolean).map(line=>serialize(JSON.parse(line))).join('\n')+(raw.endsWith('\n')?'\n':''):redactText(raw);}
    return {root_request_id,path:relative,offset,content:content.slice(offset,offset+limit),total_characters:content.length,has_more:offset+limit<content.length,next_offset:offset+limit<content.length?offset+limit:null};
  }
}
