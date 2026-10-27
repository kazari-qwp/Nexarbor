export function createAgentConversations(api){
 const empty=()=>({record:null,history:[],draft:{text:'',attachments:[]},busy:false,error:''});
 const states={network:empty(),component:empty()},listeners=new Set(),timers=new Map(),polls=new Map(),versions={network:0,component:0};
 const publish=(role,patch)=>{states[role]={...states[role],...patch};for(const listener of listeners)listener();};
 const history=async()=>{const rows=await api('advice.list');for(const role of Object.keys(states))publish(role,{history:rows.filter(row=>row.role===role)});};
 const drafts=new Map(),writes=new Map();
 const flush=id=>{
  clearTimeout(timers.get(id));timers.delete(id);const draft=drafts.get(id);if(!draft)return writes.get(id)??Promise.resolve();drafts.delete(id);
  const job=(writes.get(id)??Promise.resolve()).catch(()=>{}).then(()=>api('advice.draft',{id,draft})).catch(error=>{if(!drafts.has(id))drafts.set(id,draft);throw error;});writes.set(id,job);
  job.then(()=>{if(writes.get(id)===job)writes.delete(id);},()=>{if(writes.get(id)===job)writes.delete(id);});return job;
 };
 const accept=(role,record,{loadDraft=false}={})=>{
  const same=states[role].record?.id===record.id;
  publish(role,{record,...(loadDraft&&!same?{draft:record.draft??{text:'',attachments:[]}}:{})});
  if(record.job?.status==='running'&&!polls.has(record.id)){
   const poll=async()=>{try{const next=await api('advice.read',{id:record.id});if(states[role].record?.id===next.id)accept(role,next);if(next.job?.status!=='running'){clearInterval(polls.get(record.id));polls.delete(record.id);await history();}}catch(error){publish(role,{error:error.message});}};
   polls.set(record.id,setInterval(poll,1000));
  }
  return record;
 };
 const store={
  subscribe(listener){listeners.add(listener);return()=>listeners.delete(listener);},
  snapshot:role=>states[role],
  async open({role,...params}){
   const version=++versions[role];publish(role,{busy:true,error:''});
   try{await store.flush();const record=await api('advice.open',{role,...params});if(version===versions[role])accept(role,record,{loadDraft:true});await history();return record;}
   catch(error){if(version===versions[role])publish(role,{error:error.message});throw error;}
   finally{if(version===versions[role])publish(role,{busy:false});}
  },
  setError(role,error){publish(role,{error:error?.message??error??''});},
  setDraft(role,patch){const state=states[role],draft={...state.draft,...patch};publish(role,{draft});if(!state.record)return;const id=state.record.id;drafts.set(id,draft);clearTimeout(timers.get(id));timers.set(id,setTimeout(()=>flush(id).catch(error=>store.setError(role,error)),250));},
  async send(role,text,attachments,context){
   const record=states[role].record;if(!record)throw Error('对话尚未载入');publish(role,{busy:true,error:''});
   try{await flush(record.id);const next=await api('advice.send',{id:record.id,text,attachments,...context});accept(role,next);publish(role,{draft:{text:'',attachments:[]}});await history();return next;}
   catch(error){store.setError(role,error);throw error;}finally{publish(role,{busy:false});}
  },
  async modify(role,context){const record=states[role].record;if(!record)throw Error('对话尚未载入');const work=await api('advice.modify',{id:record.id,...context});accept(role,await api('advice.read',{id:record.id}));return work;},
  async cancel(role){const record=states[role].record;if(record)accept(role,await api('advice.cancel',{id:record.id}));},
  reset(){for(const role of Object.keys(states))publish(role,{record:null,error:''});},
  async flush(){await Promise.all([...new Set([...drafts.keys(),...writes.keys()])].map(flush));},
  dispose(){for(const timer of timers.values())clearTimeout(timer);for(const timer of polls.values())clearInterval(timer);store.flush().catch(()=>{});}
 };
 return store;
}
