import {useEffect,useRef,useState} from 'react';

export function useExternalText({api,document,onChange,note}){
 const sessions=useRef(new Map()),polling=useRef(false),current=useRef();current.current={document,onChange,note};
 const [conflict,setConflict]=useState(null),conflictRef=useRef(null);
 const showConflict=value=>{conflictRef.current=value;setConflict(value);};
 const target=value=>{const doc=current.current.document(),node=doc?.network.nodes.find(node=>node.node_id===value.node);return node?.type==='text_file'&&node.parameters.file_path===value.path?doc:null;};
 const merge=async value=>{
  let doc=target(value);if(!doc){sessions.current.delete(value.session);return;}
  if(value.external){sessions.current.set(value.session,value);if(doc.files[value.path]!==value.content){const next=structuredClone(doc);next.files[value.path]=value.content;current.current.onChange(next);}return;}
  const ours=doc.files[value.path]??'';
  // An unchanged external copy can safely receive a newer workbench draft.
  if(value.content===value.base&&ours!==value.base){const ack=await api('text.external.update',{session:value.session,digest:value.digest,content:ours});sessions.current.set(value.session,{...value,...ack});return;}
  if(ours!==value.base&&ours!==value.content){showConflict({...value,ours});return;}
  const ack=await api('text.external.update',{session:value.session,digest:value.digest});sessions.current.set(value.session,{...value,...ack});
  // The user may have edited or deleted the node while the acknowledgement was in flight.
  doc=target(value);if(!doc){sessions.current.delete(value.session);return;}
  const latest=doc.files[value.path]??'';
  if(latest!==value.base&&latest!==value.content){showConflict({...value,ours:latest});return;}
  if(latest!==value.content){const next=structuredClone(doc);next.files[value.path]=value.content;current.current.onChange(next);current.current.note('外部修改已同步到草稿；校验并更新网络后生效');}
 };
 const poll=async()=>{
  if(conflictRef.current||polling.current)return;polling.current=true;
  try{for(const [id,previous]of sessions.current){if(conflictRef.current)break;if(!target(previous)){sessions.current.delete(id);continue;}let value;try{value=await api('text.external.read',{session:id,digest:previous.external&&current.current.document()?.files[previous.path]===undefined?undefined:previous.digest});}catch(error){sessions.current.delete(id);current.current.note(error);continue;}if(value.changed)try{await merge(value);}catch(error){current.current.note(error);}}}finally{polling.current=false;}
 };
 useEffect(()=>{const focus=()=>{poll().catch(current.current.note);},timer=setInterval(focus,2000);window.addEventListener('focus',focus);return()=>{clearInterval(timer);window.removeEventListener('focus',focus);};},[]);
 const open=async(node,operation='text.external.open')=>{const doc=current.current.document(),value=await api(operation,{node,content:doc.files[node.parameters.file_path]??''});sessions.current.set(value.session,value);await merge(value);};
 const resolve=async useExternal=>{
  const value=conflictRef.current;if(!value)return;
  try{
   let doc=target(value);if(!doc){sessions.current.delete(value.session);showConflict(null);return;}
   const ours=doc.files[value.path]??'',latest=await api('text.external.read',{session:value.session});
   if(latest.digest!==value.digest){showConflict({...latest,ours});return;}
   const ack=await api('text.external.update',{session:value.session,digest:value.digest,...(!useExternal?{content:ours}:{})});sessions.current.set(value.session,{...value,...ack});
   doc=target(value);
   if(useExternal&&doc){const fresh=doc.files[value.path]??'';if(fresh!==ours&&fresh!==value.content){showConflict({...value,ours:fresh});return;}const next=structuredClone(doc);next.files[value.path]=value.content;current.current.onChange(next);}
   showConflict(null);
  }catch(error){current.current.note(error);}
 };
 return {open,reveal:node=>open(node,'text.external.reveal'),conflict,resolve};
}
