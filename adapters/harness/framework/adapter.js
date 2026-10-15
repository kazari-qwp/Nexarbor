import {ComponentExtensions} from './extensions.js';
// Native Harness handles and transport conversion; application policy lives in Python.
import path from 'node:path';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {Bridge} from './bridge.js';
import {requestRoute} from './request-route.js';
import {InstructionHistory} from './instructions.js';
import {ToolPermissions} from './tool-permissions.js';
import {applyCapabilities,updateCapabilityTools} from './capabilities.js';
import {assertCompleteOutput} from './response-status.js';
import {networkDirectory} from './storage.js';
import {trackApprovals} from './approval-state.js';
import {installWindowsPythonCompat} from './windows-python.js';
import {prepareWindowsWorkspace} from './windows-workspace.js';
import {installWindowsTerminal} from './windows-terminal.js';

const user=(text,source={kind:'user'})=>createUserMessage({source,content:[{type:'text',text}]});
const plain=value=>JSON.parse(JSON.stringify(value,(_key,item)=>item instanceof Error?String(item.message):typeof item==='function'?undefined:item));

export async function createAdapter(ctx,config={}){
  installWindowsPythonCompat(ctx);
  const runtimes=new Map(),starting=new Map(),closing=new Map(),owned=new WeakSet();
  ctx.on('agent/created',async({agent})=>{
    const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
    const workspace=path.resolve(config.workspace??path.join(root,'workspace'));
    if(owned.has(agent.ctx)||agent.session.header.origin==='subagent'||!agent.session.header.cwd||path.resolve(agent.session.header.cwd)!==workspace)return;
    if(closing.has(agent.id))await closing.get(agent.id);
    if(runtimes.has(agent.id))return;
    if(starting.has(agent.id))return starting.get(agent.id);
    const pending=createRuntime(ctx,config,agent,owned);
    starting.set(agent.id,pending);
    try{runtimes.set(agent.id,await pending);}finally{starting.delete(agent.id);}
  });
  async function closeRuntime(id){
    if(closing.has(id))return closing.get(id);
    const runtime=runtimes.get(id);if(!runtime)return;
    runtimes.delete(id);
    const pending=(async()=>{try{await runtime.components.dispose();}finally{await runtime.bridge.close();}})();
    closing.set(id,pending);
    try{await pending;}finally{closing.delete(id);}
  }
  ctx.on('agent/disposed',({agent})=>closeRuntime(agent.id));
  const components={
    disable:async id=>Promise.all([...runtimes.values()].map(runtime=>runtime.components.disable(id))),
    dispose:async()=>{for(const id of [...runtimes.keys()])await closeRuntime(id);await Promise.all([...closing.values()]);}
  };
  ctx.provide('datanetComponents',components);
  ctx.effect(()=>()=>components.dispose(),'datanet.adapter');
  return {runtimes,components};
}

async function createRuntime(ctx,config,rootAgent,owned){
  const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
  const workspace=path.resolve(config.workspace??path.join(root,'workspace'));
  const base=path.resolve(config.storage??path.join(workspace,'.datanet'));
  const directory=networkDirectory(base,rootAgent.id);
  await mkdir(directory,{recursive:true});
  await prepareWindowsWorkspace(workspace);
  const native=new Map(),scopes=new WeakMap(),executions=new Map(),sessions=new Map();
  const history=new InstructionHistory(createUserMessage),permissions=new ToolPermissions(createUserMessage);
  let bridge;
  const call=(method,params={},timeout)=>bridge.call(method,params,timeout);
  const agentFor=actor=>{const value=native.get(actor);if(!value)throw new Error('Agent is not mounted: '+actor);return value;};
  const extensionRoot=path.resolve(config.extensionRoot??path.join(root,'extensions','.none'));
  const extensions=new ComponentExtensions(extensionRoot,agentFor);
  function render(view,entry){
    for(const section of view.sections??[]){
      if(entry.sections.has(section.owner+':'+section.name))continue;
      entry.sections.add(section.owner+':'+section.name);
      entry.agent.ctx.systemPrompt.section({name:section.name,order:section.order,interpolate:false,text:()=>entry.view.sections?.find(s=>s.owner===section.owner&&s.name===section.name)?.text??''});
    }
    entry.view=view;
  }
  async function event(actor,name,payload={}){
    if(bridge?.closed)return native.get(actor)?.view??{};
    const result=await call('application/event',{actor,name,payload:plain(payload)},0);
    const entry=native.get(actor);if(entry)render(result,entry);
    return result;
  }
  function attach(actor,agent){
    owned.add(agent.ctx);
    const entry={actor,agent,view:{},sections:new Set(),tools:new Map(),pendingApprovals:trackApprovals(agent)};native.set(actor,entry);scopes.set(agent.ctx,actor);
    history.bind(agent.ctx,agent);permissions.state(agent.ctx);
    agent.ctx.systemPrompt.section({name:'datanet:role',order:90,interpolate:false,text:()=>entry.view.prompt??''});
    const own=payload=>!payload?.agent||payload.agent===agent;
    installWindowsTerminal(agent.ctx,agent,workspace);
    agent.ctx.on('agent/prepare-context',async()=>{await event(actor,'context/prepare');});
    agent.ctx.on('agent/request-tail',async(_payload,next)=>{
      const tail=await next();if(bridge?.closed)return tail;
      await event(actor,'context/admitted',{message_ids:agent.session.deriveMessages().map(m=>m.id)});
      return [...tail,...(await call('application/tail',{actor})).map(text=>({role:'user',content:[{type:'text',text}]}))];
    });
    agent.ctx.on('agent/pre-step',async(payload,next)=>{if(own(payload))await event(actor,'agent/pre-step',{messages:agent.session.deriveMessages()});return next();});
    agent.ctx.on('agent/request',async(payload,next)=>{if(own(payload)){await ctx.sessions.flush(agent.session);await event(actor,'agent/request');}return requestRoute(await next(),config.modelRoute);});
    agent.ctx.on('tools/pre-execute',async(exec,next)=>{
      if(own(exec)){
        const reason=await call('application/guard',{actor,name:exec.name,arguments:exec.arguments??{}});
        if(reason)throw new Error(reason);
        await event(actor,'tool/native-before',{name:exec.name,arguments:exec.arguments??{}});
      }
      return next();
    });
    agent.ctx.on('tools/result',async(exec,result)=>{if(own(exec))await event(actor,'tool/result',{name:exec.name,call_id:exec.callId??null,arguments:exec.arguments??{},result});});
    agent.ctx.on('agent/error',async payload=>{if(own(payload))await event(actor,'agent/error',{error:String(payload.error??'agent error'),failure:payload.error?.failure??{code:payload.error?.code,message:String(payload.error?.message??payload.error??'agent error')}});});
    agent.ctx.on('agent/turn-stopping',async payload=>{if(own(payload))await event(actor,'agent/turn-stopping');});
    agent.ctx.on('agent/status',async payload=>{if(own(payload))await event(actor,'agent/status',{status:payload.status,messages:agent.session.deriveMessages()});});
    agent.ctx.on('agent/inbox/discarded',async({message})=>{await event(actor,'message/discarded',{message_id:message.id});});
    return entry;
  }
  async function host(operation,p){
    if(operation==='component-extension')return extensions.invoke(p);
    if(operation==='tools'){
      const entry=agentFor(p.actor),ac=entry.agent.ctx,active=new Set(p.definitions.map(d=>d.name));
      for(const [name,dispose] of entry.tools)if(!active.has(name)){dispose();entry.tools.delete(name);}
      for(const definition of p.definitions){
        if(entry.tools.has(definition.name))continue;
        const dispose=permissions.register(ac,{...definition,output:{schema:{},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},execute:async(args,exec)=>{
          if(exec?.agent&&exec.agent!==entry.agent)throw new Error('Tool belongs to another Agent');
          const id=randomUUID();executions.set(id,{exec,actor:p.actor});
          try{return await call('application/invoke',{actor:p.actor,name:definition.name,arguments:args,execution_id:id},0);}
          finally{executions.delete(id);}
        }});
        entry.tools.set(definition.name,dispose);
      }
      return {ok:true};
    }
    if(operation==='load-document')return history.load(agentFor(p.actor).agent.ctx,p.document,p.text);
    if(operation==='view-update'){render(p.view,agentFor(p.actor));return {ok:true};}
    if(operation==='document-present')return history.has(agentFor(p.actor).agent.ctx,p.document);
    if(operation==='inbox-snapshot'){const agent=agentFor(p.actor).agent;return [...agent.session.deriveMessages(),...(agent.inbox?.nextTurn??[]),...(agent.inbox?.nextStep??[])];}
    if(operation==='create'){
      const parent=agentFor(p.parent).agent;
      const setup=async(ac,agent)=>{
        attach(p.actor,agent);
        const capabilities=await applyCapabilities(ac,agent,p.grant.official,ctx,p.binding.officialPreset,permissions);
        await call('agent_progress',{target:p.actor,officialPreset:capabilities.officialPreset});
      };
      const options={sessionId:p.binding.session_id,parentAgent:parent,meta:{cwd:workspace,agentPreset:p.binding.officialPreset??'standard'},agentOptions:p.binding.agentOptions,setup};
      let handle;
      if(p.resume){
        try{handle=await ctx.agents.resume({resumeSessionId:p.binding.session_id,parentAgent:parent,agentOptions:p.binding.agentOptions,setup});}
        catch(error){if(p.binding.status!=='prepared'||!/not found|does not exist|ENOENT/i.test(String(error)))throw error;handle=await ctx.agents.create(options);}
      }else handle=await ctx.agents.create(options);
      const entry=agentFor(p.actor);entry.handle=handle;sessions.set(p.actor,{handle});
      ctx.sessionTitle.rename(handle.agent.session,'DataNet · '+p.actor);await ctx.sessions.flush(handle.agent.session);
      return {session_id:handle.agent.id};
    }
    if(operation==='capabilities'){const entry=agentFor(p.actor);return updateCapabilityTools(entry.agent.ctx,entry.agent,p.grant.official,ctx,permissions);}
    if(operation==='inspect'){const entry=agentFor(p.actor);return {session_id:entry.agent.id,status:entry.agent.status,options:entry.agent.options,pending_approvals:entry.pendingApprovals()};}
    if(operation==='messages')return agentFor(p.actor).agent.session.deriveMessages();
    if(operation==='dispose-agent'){const entry=agentFor(p.actor);await ctx.sessions.flush(entry.agent.session);await entry.handle.dispose();native.delete(p.actor);sessions.delete(p.actor);return {ok:true};}
    if(operation==='run'){
      const agent=agentFor(p.actor).agent,execution=executions.get(p.execution_id),signal=execution?.exec?.signal;
      const start=agent.session.deriveMessages().length;
      const cancel=()=>agent.cancel('user');let expired=false;
      signal?.throwIfAborted();signal?.addEventListener('abort',cancel,{once:true});
      const timer=setTimeout(()=>{expired=true;cancel();},p.timeout_ms??180000);
      try{
        agent.followup(user(p.text));await agent.whenIdle();signal?.throwIfAborted();
        if(expired)throw new Error('Agent execution timeout');
        const messages=agent.session.deriveMessages().slice(start);assertCompleteOutput(messages);
        return {messages,session_id:agent.id};
      }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);await ctx.sessions.flush(agent.session);}
    }
    if(operation==='make-message')return user(p.text,{kind:'agent-message',form:'relay',senderSessionId:agentFor(p.from).agent.id});
    if(operation==='steer'){agentFor(p.actor).agent.steer(p.message??user(p.text));return {ok:true};}
    if(operation==='cancel-agent'){agentFor(p.actor).agent.cancel('user');return {ok:true};}
    if(operation==='conclude'){const entry=executions.get(p.execution_id);if(!entry)throw new Error('No native tool execution');entry.exec.concludeTurn();return {ok:true};}
    throw new Error('Unsupported Harness operation: '+operation);
  }
  const source=path.join(root,'.venv','Scripts','python.exe'),useSource=!config.backend&&existsSync(source);
  bridge=new Bridge(config.backend??(useSource?source:path.join(root,'adapters/harness/runtime/backend/datanet-backend.exe')),directory,config.backendArgs??(useSource?[path.join(root,'adapters/harness/backend/server.py')]:[]),{
    DATANET_PRODUCT_ROOT:root,DATANET_COMPONENT_ROOT:extensionRoot,DATANET_COMPONENT_PROFILE:JSON.stringify(config.components??{}),PYTHONDONTWRITEBYTECODE:'1'
  },host);
  try{await call('ping');await call('application/start',{config},0);}catch(error){await bridge.close();throw error;}
  {
    const entry=attach('root',rootAgent);
    const view=await call('application/root',{session_id:rootAgent.id},0);render(view,entry);
    const official=await applyCapabilities(rootAgent.ctx,rootAgent,view.grant.official,ctx,undefined,permissions);
    await call('agent_progress',{target:'root',officialPreset:official.officialPreset});
  }
  const components={disable:async id=>{const result=await call('application/disable',{component:id},0);for(const entry of native.values())render(await call('application/view',{actor:entry.actor}),entry);return result;},dispose:async()=>{for(const {handle} of sessions.values())await handle.dispose();}};
  return {bridge,components,sessions,scopes,instructionHistory:history,get rootAgent(){return rootAgent;},workspace,directory};
}
