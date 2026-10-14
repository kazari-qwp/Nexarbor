// All execution remains in Harness; this component owns only budgets and cleanup.
const terminalKinds=new Set(['pwsh','bash','pty-send']);
const active=job=>job.status==='running'||job.status==='stopping';
export function create({ctx,agent}){
  const jobs=ctx.get('jobs');if(!jobs)throw new Error('Command policy requires native jobs');
  let config,closed=false;const timers=new Map();
  const clear=id=>{clearTimeout(timers.get(id));timers.delete(id);};
  const arm=job=>{
    if(closed||!config||job.owner!==agent.id||!terminalKinds.has(job.kind)||!active(job))return;
    clear(job.id);const timer=setTimeout(()=>{timers.delete(job.id);try{jobs.kill(job.id,agent.id,'command hard limit reached');}catch{}},Math.max(0,job.startedAt+config.hardLimitMs-Date.now()));timer.unref?.();timers.set(job.id,timer);
  };
  async function stop(reason='current task ended'){
    const owned=jobs.list(agent.id).filter(job=>job.owner===agent.id&&terminalKinds.has(job.kind)&&active(job));
    // Install settlement waiters before killing: cleanup notices must not wake a finished owner.
    const settled=owned.map(job=>jobs.wait(job.id,config?.cleanupWaitMs??5000,agent.id).catch(()=>null));
    for(const job of owned){clear(job.id);try{jobs.kill(job.id,agent.id,reason);}catch{}}
    await Promise.all(settled);return {stopped:owned.map(job=>job.id)};
  }
  const unsubscribe=jobs.events.subscribe({owner:agent.id},event=>{
    if(event.type==='registered')arm(event.job);
    if(event.type==='settled'||event.type==='removed')clear(event.job.id);
  });
  const releaseExecute=ctx.on('tools/execute',async(exec,next)=>{
    if(!config||(exec.agent&&exec.agent!==agent))return next();
    const original=exec.arguments;
    if(exec.name==='pwsh'||exec.name==='bash')exec.arguments={...original,timeoutMs:Math.min(original?.timeoutMs??config.foregroundWaitMs,config.foregroundWaitMs)};
    else if(exec.name==='job_output'&&original?.wait)exec.arguments={...original,timeout_ms:Math.min(original.timeout_ms??config.foregroundWaitMs,config.foregroundWaitMs)};
    try{return await next();}finally{exec.arguments=original;}
  });
  const releaseStatus=ctx.on('agent/status',payload=>{
    if(config&&payload.agent===agent&&payload.status==='idle')return stop();
  });
  async function dispose(){if(closed)return;closed=true;unsubscribe();releaseExecute();releaseStatus();await stop('command component removed');for(const id of timers.keys())clear(id);}
  ctx.on('dispose',dispose);
  return {
    configure(options){
      for(const key of ['foregroundWaitMs','hardLimitMs','cleanupWaitMs'])if(!Number.isSafeInteger(options[key])||options[key]<1)throw new Error('Invalid command policy '+key);
      if(options.hardLimitMs<options.foregroundWaitMs)throw new Error('Hard limit must cover foreground wait');
      config={...options};for(const job of jobs.list(agent.id))arm(job);return {ok:true};
    },stop:()=>stop(),dispose
  };
}
