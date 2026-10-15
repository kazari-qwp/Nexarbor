// Observe the native approval waterfall without deciding or changing permissions.
export function trackApprovals(agent){
  const pending=new Map();
  agent.ctx.on('approval/request',async(request,next)=>{
    if(request.agent!==agent)return next();
    const key=request.callId??Symbol('approval');
    pending.set(key,{tool:request.toolName,call_id:request.callId??null,reason:request.reason??null,since:Date.now()});
    try{return await next();}finally{pending.delete(key);}
  });
  return ()=>[...pending.values()];
}
