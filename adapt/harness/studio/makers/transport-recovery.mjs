export function transportRecovery(job,result,now=Date.now()){
 if(result.status!=='failed'||result.reason?.kind!=='error'||result.reason.error?.code!=='MALFORMED_RESPONSE'||(job.transport_recoveries??0)>=2||job.deadline-now<15000)return null;
 const details=(result.tool_input_errors??[]).slice(0,3).map(item=>item.tool+' 参数不是合法 JSON（'+item.characters+'字符'+(item.position==null?'':'，位置'+item.position)+'）').join('；');
 return '上次模型输出未形成合法工具参数，相关调用未执行。'+(details?details+'。':'')+'保留当前工作副本和委托进度，继续原任务；减小单批修改和嵌套，必要时重新读取目标。不要原样重复损坏参数，不改变模型或预算。';
}
