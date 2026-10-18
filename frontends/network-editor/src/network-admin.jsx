import React,{useState} from 'react';
export function NetworkAdminPanel({api,node,onApplied}){
 const [requirement,setRequirement]=useState(''),[task,setTask]=useState(''),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const run=async(operation,args={})=>{setBusy(true);setError('');try{const value=await api('module.call',{node:node.node_id,module:'network.administrator',operation,arguments:args});if(value.status!=='ok')throw Error(value.error);setResult(value.data);if(value.data?.task)setTask(value.data.task);if(operation==='apply')await onApplied?.();}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <section className="network-admin-panel">
  <p>先应用网络及授权，再制作。只处理此节点实际可达的范围；制作在独立副本中进行，提交保留已有运行状态。</p>
  <button disabled={busy} onClick={()=>run('inspect')}>查看可达副本</button>
  <textarea aria-label="局部网络制作需求" placeholder="我想在这里建立一个讨论组，共享任务板……" value={requirement} onChange={e=>setRequirement(e.target.value)}/>
  <button disabled={busy||!requirement.trim()} onClick={()=>run('build',{requirement,key:crypto.randomUUID()})}>委托制作局部网络</button>
  <input aria-label="管理员制作任务号" placeholder="制作任务号" value={task} onChange={e=>setTask(e.target.value)}/>
  <div><button disabled={busy||!task} onClick={()=>run('status',{task})}>查询进度</button><button disabled={busy||!task} onClick={()=>run('apply',{task})}>提交已完成草稿</button><button disabled={busy||!task} onClick={()=>run('cancel',{task})}>取消制作</button></div>
  {busy&&<p>处理中……</p>}{error&&<p role="alert">{error}</p>}{result&&<details open><summary>管理员结果</summary><pre style={{maxHeight:260,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(result,null,2)}</pre></details>}
 </section>;
}
