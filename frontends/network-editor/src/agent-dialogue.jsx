import React,{useSyncExternalStore} from 'react';
import {GitBranch,Plus,Square} from 'lucide-react';
import {ConversationMessages,MessageComposer} from './studio/conversation.jsx';
import './agent-dialogue.css';
export function useAgentConversation(store,role){return useSyncExternalStore(store.subscribe,()=>store.snapshot(role));}
export function AgentDialogue({store,role,onRole,api,getContext,onWorkspace,beforeSwitch,beforeSend,blocked=false,label='询问 Agent'}){
 const {record,history,draft,busy,error}=useAgentConversation(store,role),active=record?.job?.status==='running',loading=busy||blocked,focus=record?.focus?.target??record?.target;
 const run=fn=>Promise.resolve().then(fn).catch(error=>store.setError(role,error));
 return <div className="agent-dialogue">
  <div className="agent-dialogue-controls"><select aria-label="Agent 类型" value={role} disabled={loading} onChange={event=>{const next=event.target.value;run(async()=>{await beforeSwitch?.();onRole(next);await store.open({role:next,...getContext()});});}}><option value="component">模块／工具 Agent</option><option value="network">网络 Agent</option></select>
   <select aria-label="对话历史" value={record?.id??''} disabled={loading} onChange={event=>{const id=event.target.value;run(async()=>{await beforeSwitch?.();await store.open({role,id});});}}><option value="" disabled>正在载入对话…</option>{history.map(item=><option key={item.id} value={item.id}>{item.target.name??item.target.id??'新对话'} · {item.turns} 轮</option>)}</select>
   <button aria-label="新对话" title="新对话" disabled={loading} onClick={()=>run(async()=>{await beforeSwitch?.();return store.open({role,newConversation:true,...(focus?{target:focus}:{}),...(record?.focus?.workspace?{workspace:record.focus.workspace}:{}),...getContext()});})}><Plus size={13}/><span>新对话</span></button>
   {onWorkspace&&<button aria-label="查看工作分支" title="查看工作分支" disabled={!record||loading||active} onClick={()=>run(async()=>onWorkspace(await store.modify(role,getContext()),store.snapshot(role).record))}><GitBranch size={13}/><span>工作分支</span></button>}
  </div>
  <details className="agent-dialogue-context"><summary><span>对话与上下文</span><span className="agent-dialogue-target" title={focus?.name??focus?.id}>本轮：{focus?.name??focus?.id??'当前网络'}</span></summary><p>本轮对象：{focus?.name??focus?.id??'当前网络'}{focus?.node?' · 节点 '+focus.node:''}</p><p>默认继续上次对话。切换对象只更新本轮关注内容；咨询与制作共享记录。</p>{record?.snapshot&&<p>上一轮快照：全网 {record.snapshot.nodes} 个节点；重点：{record.snapshot.selection.nodes.join('、')||'无'}；选中边 {record.snapshot.selection.edges.length} 条。</p>}<small>下一次发送会读取当前网络及选中项。修改在各对象自己的工作分支中保留。</small></details>
  <ConversationMessages messages={record?.job?.messages??[]} previews={record?.job?.previews??[]} api={api} onError={error=>store.setError(role,error)}/>
  <div className="agent-dialogue-status">{active?'正在处理…':record?.job?.error??(record?.job?'本轮已结束':'可以提问，也可以直接要求修改')}{active&&<button onClick={()=>run(()=>store.cancel(role))}><Square size={12}/>停止 Agent</button>}</div>
  {error&&<div role="status" className="studio-conversation-error">{error}</div>}
  <MessageComposer inputDisabled={!record||loading} label={label} value={draft.text} onChange={text=>store.setDraft(role,{text})} attachments={draft.attachments} onAttachmentsChange={next=>store.setDraft(role,{attachments:typeof next==='function'?next(store.snapshot(role).draft.attachments):next})} disabled={loading||active||!record} onError={error=>store.setError(role,error)} onSend={async(text,attachments)=>{await beforeSend?.();return store.send(role,text,attachments,getContext());}}/>
 </div>;
}
