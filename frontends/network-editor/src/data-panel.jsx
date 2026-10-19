import React,{useState} from 'react';

// 所有操作先在后端的独立数据副本中执行；写入结果只进入当前草稿。
export function DataPanel({node,files,api,onChange}){
 const [key,setKey]=useState(node.type==='value'?'value':node.type==='text_file'?'content':'example'),[text,setText]=useState('{}'),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const run=async operation=>{
  setBusy(true);setError('');try{
   let value=text;if(!['text_file','knowledge_collection'].includes(node.type)||['csv','sqlite'].includes(node.parameters?.storage))try{value=JSON.parse(text);}catch{}
   const arguments_=operation==='inspect'?{}:operation==='query'?{request:{method:'filter',filters:{}}}:{key,...(operation==='write'?{value,mode:'upsert'}:{})};
   const response=await api('data.preview',{node,files,operation,arguments:arguments_});setResult(response.result);
   if(operation==='write'){
    if(response.result.status!=='ok')throw Error(response.result.errors?.join('；')||'数据写入失败');
    onChange({beforeNode:node,beforeFiles:files,node:response.node,files:response.files});
   }else if(operation==='read'&&response.result.items?.length){
    const item=response.result.items[0],data=node.type==='value'?item.value:['knowledge_collection','text_file'].includes(node.type)?item.content:item;setText(typeof data==='string'?data:JSON.stringify(data,null,2));
   }
  }catch(e){setError(e.message);}finally{setBusy(false);}
 };
 return <section className="data-panel" aria-label="节点本地数据"><p className="muted">编辑独立数据副本；保存到草稿后，点击“应用网络”生效。</p><div className="form-row"><button disabled={busy} onClick={()=>run('inspect')}>查看数据结构</button><button disabled={busy||['value','text_file'].includes(node.type)} onClick={()=>run('query')}>列出记录</button></div><label>主键<input aria-label="数据主键" value={key} onChange={e=>setKey(e.target.value)}/></label><button disabled={busy} onClick={()=>run('read')}>读取数据</button><label>数据内容（JSON 或正文）<textarea aria-label="数据内容" rows={8} value={text} onChange={e=>setText(e.target.value)}/></label><button className="primary" disabled={busy||node.modules?.['data.local']?.config.read_only} onClick={()=>run('write')}>保存数据到草稿</button>{error&&<p role="alert" className="notice">{error}</p>}{result&&<details open><summary>数据结果</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(result,null,2)}</pre></details>}</section>;
}
