// Protocol recovery stays on the native request-error extension point.
import {createUserMessage} from '@deepseek-ai/dsh-llm';

export const TOOL_JSON_RECOVERY_NOTICE='上一次工具调用的参数不是合法JSON，工具未执行。请重新生成正确的工具调用。';

export function installRequestRecovery(ctx,agent){
  let position='',corrections=0;
  return ctx.on('agent/request-error',async(payload,next)=>{
    if(payload.agent!==agent||payload.failure?.code!=='MALFORMED_RESPONSE'||!payload.failure.message?.endsWith('tool input is invalid JSON'))return next();
    const current=payload.turn+':'+payload.step;
    if(current!==position){position=current;corrections=0;}
    if(payload.signal.aborted||corrections>=2)return next();
    const attempt=++corrections;
    const failed=agent.session.snapshotEvents().findLast(event=>event.type==='assistant/attempt');
    const details=[];
    for(const frame of failed?.data?.stream??[]){
      const block=frame.chunk?.type==='block-end'?frame.chunk.block:null;
      if(block?.type!=='tool-call')continue;
      try{JSON.parse(block.arguments);}catch(error){details.push('工具：'+block.name+'\n参数原文：\n'+block.arguments+'\nJSON解析错误：'+error.message);}
    }
    // Failed stream attempts are already archived by Harness. Only feedback is admitted.
    const message=createUserMessage({source:{kind:'user',document:'recovery:tool-json'},content:[{type:'text',text:TOOL_JSON_RECOVERY_NOTICE+'\n原始错误：'+payload.failure.message+(details.length?'\n'+details.join('\n'):'')}]});
    agent.session.append('user/message',message,{surfaceOp:'append'});
    agent.session.append('datanet/request-recovery',{turn:payload.turn,step:payload.step,attempt,maxCorrections:2,failure:payload.failure});
    return {kind:'retry'};
  });
}

export function create({ctx,agent}){const release=installRequestRecovery(ctx,agent);return {configure:()=>({ok:true}),dispose:()=>release()};}
