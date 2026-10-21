import {textWindow} from './text-window.mjs';
// Short, actionable feedback first; the full immutable log stays available by job ID.
export function validationFeedback(check){
 const clip=(text,limit)=>text.length>limit?text.slice(0,Math.floor(limit*.6))+'\n…（中间省略，完整内容按 job 分页）…\n'+text.slice(-Math.floor(limit*.4)):text;
 const raw=String(check.log??''),clean=raw.replace(/Executing <[^\r\n]* took [^\r\n]* seconds/g,'').replace(/\r\n/g,'\n');
 const lines=clean.split('\n'),count=/测试数量：(\d+)/.exec(clean)?.[1]??/Ran (\d+) tests?/.exec(clean)?.[1];
 const footer=lines.filter(s=>/^(Ran \d+ tests?|OK$|FAILED |PASS[:：])/.test(s));
 const errors=[];
 for(const match of clean.matchAll(/^(ERROR|FAIL): ([^\n]+)\n([-]+\n)?([\s\S]*?)(?=\n[=-]{10,}|\nRan \d+ tests?|(?![\s\S]))/gm)){
  const body=match[4].trim().split('\n'),last=body.findLastIndex(s=>/^[\w.]+(?:Error|Exception|Failure|Interrupt|Exit)\b/.test(s));
  const message=clip(last>=0?body.slice(last).join('\n'):body.slice(-5).join('\n'),1200);
  const frames=[...match[4].matchAll(/File "([^"]+)", line (\d+)/g)],frame=frames.findLast(f=>/(?:^|[\\/])(?:tests[\\/]|module\.py$)/.test(f[1]));
  errors.push({test:match[2],message,...(frame?{location:frame[1].replace(/^.*[\\/](?=tests[\\/]|module\.py$)/,'').replaceAll('\\','/')+':'+frame[2]}:{})});
 }
 const failures=errors.slice(0,8).map(e=>e.test+'\n'+(e.location?'  '+e.location+'\n':'')+e.message).join('\n\n');
 const log=check.status==='passed'?footer.join('\n')||clean.trim().slice(-2000):failures?footer.join('\n')+'\n\n'+failures+(errors.length>8?'\n另有 '+(errors.length-8)+' 项失败，按 job 读取完整日志。':''):clean.trim().slice(-6000);
 return {status:check.status,job:check.id,...(count?{test_count:Number(count)}:{}),...(check.warnings?.length?{warnings:check.warnings.slice(0,8)}:{}),log:clip(log,6000),log_lines:raw.split('\n').length,hint:'需要完整上下文时用 validate(job=此编号,start_line=1,line_count=120)，长行可按回执 next_char 用 start_char 续读；读取日志不会重跑测试。'};
}

export function validationLog(check,args){
 const {text,...page}=textWindow(String(check.log??''),args,{defaultLines:120,maxLines:200,keepSeparator:false});
 return {status:check.status,job:check.id,...page,log:text};
}
