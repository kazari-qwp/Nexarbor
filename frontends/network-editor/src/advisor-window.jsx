import {AgentDialogue,useAgentConversation} from './agent-dialogue.jsx';
import {ContextMenu} from './context-menu.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {Bot,X,Maximize2,Minimize2,GitBranch} from 'lucide-react';import './advisor-window.css';
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
 close=()=>{this.props.conversations.reset();this.props.onClose();};
 componentDidUpdate(previous){if(previous.value.serial!==this.props.value.serial&&this.state.failed)this.setState({failed:false});}
 render(){
  if(!this.state.failed)return <AdvisorContent {...this.props}/>;
  return <div className="advisor-shell"><section role="dialog" aria-label="Agent 咨询" className="advisor-window advisor-failed" style={fitWindow()}>
   <header className="advisor-title"><Bot size={17}/><strong>咨询窗口显示异常</strong><button aria-label="关闭咨询" onClick={this.close}><X size={16}/></button></header>
   <div role="alert" className="advisor-failure"><p>请关闭后重新打开咨询。已保存的对话可以从咨询历史继续查看。</p><button onClick={this.close}>关闭咨询窗口</button></div>
  </section></div>;
 }
}
function AdvisorContent({api,value,getContext,onClose,onModify,onExpand,conversations}){
 const [role,setRole]=useState(value.role),[max,setMax]=useState(false),[size,setSize]=useState(()=>fitWindow());const frame=useRef(),drag=useRef(),latestSize=useRef(size),layoutChanged=useRef(false);
 const {record}=useAgentConversation(conversations,role);
 const updateSize=next=>{const fitted=fitWindow(next);latestSize.current=fitted;setSize(fitted);return fitted;};
 useEffect(()=>{let live=true;setRole(value.role);conversations.open({role:value.role,...(value.id?{id:value.id}:{}),...(value.target?{target:value.target}:{}),...getContext()}).then(async record=>{if(live&&value.modify)onModify(await conversations.modify(value.role,getContext()),record);}).catch(()=>{});return()=>{live=false;};},[value.serial]);
 useEffect(()=>{
  let live=true;
  api('advice.ui').then(v=>{if(live&&!layoutChanged.current&&v?.advisor)updateSize(v.advisor);}).catch(()=>{});
  const fit=()=>updateSize(latestSize.current);window.addEventListener('resize',fit);
  return()=>{live=false;window.removeEventListener('resize',fit);};
 },[]);
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
 return <div className="advisor-shell"><section ref={frame} role="dialog" aria-label="Agent 咨询" className={'advisor-window'+(max?' maximized':'')} style={max?{}:size} onPointerUp={saveResize} onPointerCancel={saveResize}>
 <header className="advisor-title" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onLostPointerCapture={finishDrag}><Bot size={17}/><strong>{record?.role==='component'?'模块／工具 Agent':'网络 Agent'}</strong><button disabled={!record} title={max?'还原窗口':'展开咨询页面'} aria-label={max?'还原咨询窗口':'展开咨询页面'} onClick={()=>onExpand&&record?onExpand(record,role):setMax(!max)}>{max?<Minimize2 size={14}/>:<Maximize2 size={14}/>}</button><button aria-label="关闭咨询" onClick={onClose}><X size={16}/></button></header>
 <AgentDialogue api={api} store={conversations} role={role} onRole={setRole} getContext={getContext} onWorkspace={onModify}/>
 </section></div>;
}
