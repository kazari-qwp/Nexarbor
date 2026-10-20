import {ContextMenu} from './context-menu.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {Bot,X,Maximize2,Minimize2,GitBranch,Square} from 'lucide-react';import {ConversationMessages,MessageComposer} from './studio/conversation.jsx';import './advisor-window.css';
export function AdviceMenu({value,onClose,onChoose}){return <ContextMenu x={value.x} y={value.y} label="咨询对象操作" className="advice-context-menu" onClose={onClose}>{value.target.kind!=='preset'&&<button role="menuitem" onClick={()=>onChoose('component',false)}>咨询模块／工具 Agent</button>}<button role="menuitem" onClick={()=>onChoose('network',false)}>咨询网络 Agent</button><button role="menuitem" onClick={()=>onChoose(value.target.kind==='preset'?'network':'component',true)}><GitBranch size={13}/>建立修改分支</button></ContextMenu>;}
const defaultSize={width:700,height:610,right:24,bottom:24};
const finite=(value,fallback)=>Number.isFinite(value)?value:fallback;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function fitWindow(value={}){
 const width=clamp(finite(value?.width,defaultSize.width),Math.min(360,window.innerWidth-24),window.innerWidth-24);
 const height=clamp(finite(value?.height,defaultSize.height),Math.min(280,window.innerHeight-48),window.innerHeight-48);
 return {width,height,right:clamp(finite(value?.right,24),12,window.innerWidth-width-12),bottom:clamp(finite(value?.bottom,24),12,window.innerHeight-height-36)};
}

// A panel render failure must not unmount the network editor and its unsaved edits.
export class AdvisorWindow extends React.Component{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 componentDidUpdate(previous){if(previous.value.serial!==this.props.value.serial&&this.state.failed)this.setState({failed:false});}
 render(){
  if(!this.state.failed)return <AdvisorContent {...this.props}/>;
  return <div className="advisor-shell"><section role="dialog" aria-label="Agent 咨询" className="advisor-window advisor-failed" style={fitWindow()}>
   <header className="advisor-title"><Bot size={17}/><strong>咨询窗口显示异常</strong><button aria-label="关闭咨询" onClick={this.props.onClose}><X size={16}/></button></header>
   <div role="alert" className="advisor-failure"><p>请关闭后重新打开咨询。已保存的对话可以从咨询历史继续查看。</p><button onClick={this.props.onClose}>关闭咨询窗口</button></div>
  </section></div>;
 }
}
function AdvisorContent({api,value,getContext,onClose,onModify}){
 const [record,setRecord]=useState(null),[history,setHistory]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[max,setMax]=useState(false),[size,setSize]=useState(()=>fitWindow()),[text,setText]=useState('');const frame=useRef(),drag=useRef(),latestSize=useRef(size),layoutChanged=useRef(false);
 const updateSize=next=>{const fitted=fitWindow(next);latestSize.current=fitted;setSize(fitted);return fitted;};
 const run=async fn=>{setBusy(true);setError('');try{return await fn();}catch(e){setError(e.message);}finally{setBusy(false);}};
 const refreshHistory=()=>api('advice.list').then(setHistory);
 const open=async(role=value.role,target=value.target)=>{const next=await api('advice.open',{role,target,...getContext()});setRecord(next);await refreshHistory();return next;};
 useEffect(()=>{let live=true;run(async()=>{const next=value.id?await api('advice.read',{id:value.id}):await open();if(live){setRecord(next);if(value.modify){const work=await api('advice.modify',{id:next.id});onModify(work,next);}}});return()=>{live=false;};},[value.serial]);
 useEffect(()=>{
  let live=true;
  api('advice.ui').then(v=>{if(live&&!layoutChanged.current&&v?.advisor)updateSize(v.advisor);}).catch(()=>{});
  const fit=()=>updateSize(latestSize.current);window.addEventListener('resize',fit);
  return()=>{live=false;window.removeEventListener('resize',fit);};
 },[]);
 useEffect(()=>{if(record?.job?.status!=='running')return;let live=true;const poll=()=>api('advice.read',{id:record.id}).then(v=>{if(live)setRecord(v);}).catch(e=>{if(live)setError(e.message);});const timer=setInterval(poll,1000);return()=>{live=false;clearInterval(timer);};},[record?.id,record?.job?.status]);
 const persist=next=>{layoutChanged.current=true;const fitted=updateSize(next);api('advice.ui',{key:'advisor',value:fitted}).catch(()=>{});};
 const startDrag=event=>{
  if(event.button!==0||event.target.closest('button,select')||max||drag.current)return;
  event.preventDefault();layoutChanged.current=true;
  const box=frame.current.getBoundingClientRect(),start=updateSize({width:box.width,height:box.height,right:window.innerWidth-box.right,bottom:window.innerHeight-box.bottom});
  drag.current={pointer:event.pointerId,x:event.clientX,y:event.clientY,size:start};
  event.currentTarget.setPointerCapture(event.pointerId);
 };
 const moveDrag=event=>{
  const start=drag.current;if(!start||start.pointer!==event.pointerId)return;
  // Compute a concrete value while the gesture is alive. React may process it after pointerup.
  updateSize({...start.size,right:start.size.right+start.x-event.clientX,bottom:start.size.bottom+start.y-event.clientY});
 };
 const finishDrag=event=>{
  const start=drag.current;if(!start||start.pointer!==event.pointerId)return;
  event.stopPropagation();if(event.type==='pointerup')moveDrag(event);
  drag.current=null;
  if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  persist(latestSize.current);
 };
 const saveResize=()=>{
  if(max||drag.current||!frame.current)return;
  const box=frame.current.getBoundingClientRect(),current=latestSize.current;
  if(Math.abs(box.width-current.width)>2||Math.abs(box.height-current.height)>2)persist({...current,width:box.width,height:box.height});
 };
 const active=record?.job?.status==='running';
 return <div className="advisor-shell"><section ref={frame} role="dialog" aria-label="Agent 咨询" className={'advisor-window'+(max?' maximized':'')} style={max?{}:size} onPointerUp={saveResize} onPointerCancel={saveResize}>
 <header className="advisor-title" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onLostPointerCapture={finishDrag}><Bot size={17}/><strong>{record?.role==='component'?'模块／工具 Agent':'网络 Agent'}</strong><button title={max?'还原窗口':'展开咨询页面'} aria-label={max?'还原咨询窗口':'展开咨询页面'} onClick={()=>setMax(!max)}>{max?<Minimize2 size={14}/>:<Maximize2 size={14}/>}</button><button aria-label="关闭咨询" onClick={onClose}><X size={16}/></button></header>
 <div className="advisor-context"><span title={record?.target.id}>{record?.target.name??record?.target.id??'当前网络'}{record?.target.node?' · 节点 '+record.target.node:''}</span><select aria-label="咨询职责" disabled={busy||active} value={record?.role??value.role} onChange={e=>run(()=>open(e.target.value,record?.target))}><option value="component" disabled={record?.target.kind==='network'||record?.target.kind==='preset'}>模块／工具 Agent</option><option value="network">网络 Agent</option></select><button disabled={!record||busy||active} onClick={()=>run(async()=>{const work=await api('advice.modify',{id:record.id});onModify(work,record);})}><GitBranch size={13}/>{record?.workspace?'查看工作分支':'打开工作分支'}</button></div>
 <details className="advisor-history"><summary>咨询历史与本轮对象</summary><select aria-label="咨询历史" value={record?.id??''} onChange={e=>run(async()=>setRecord(await api('advice.read',{id:e.target.value})))}>{history.map(h=><option key={h.id} value={h.id}>{h.role==='network'?'网络':'模块／工具'} · {h.target.name??h.target.id??'当前网络'} · {h.turns} 轮</option>)}</select><p>{record?.snapshot?`全网 ${record.snapshot.nodes} 个节点；重点节点：${record.snapshot.selection.nodes.join('、')||'无'}；选中边 ${record.snapshot.selection.edges.length} 条`:'正在读取上下文…'}</p><small title={record?.snapshot.id}>快照提交：{record?.snapshot.id?.slice(0,12)}</small><p>本轮回答绑定当时的快照。下一次发送会读取当前网络与选中项；要求修改时 Agent 会在工作分支继续。</p></details>
 <ConversationMessages messages={record?.job?.messages??[]} previews={record?.job?.previews??[]} api={api} onError={setError}/><div className="advisor-status">{active?'正在分析…':record?.job?.error??(record?.job?'本轮已结束':'可询问，也可以直接要求修改')}{active&&<button onClick={()=>run(async()=>setRecord(await api('advice.cancel',{id:record.id})))}><Square size={12}/>停止</button>}</div>{error&&<div role="status" className="studio-conversation-error">{error}</div>}<MessageComposer value={text} onChange={setText} disabled={busy||active||!record} api={api} onError={setError} onSend={async(question,attachments)=>{const next=await api('advice.send',{id:record.id,text:question,attachments,...getContext()});setRecord(next);setText('');await refreshHistory();}}/>
 </section></div>;
}
