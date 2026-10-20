import {useEffect,useRef} from 'react';
// 浏览位置与退出恢复单独保存；不触碰网络和撤销队列。
export function useWorkspaceSession({api,ready,capture,onError,watch,beforeFlush}){
 const latest=useRef(),queue=useRef(Promise.resolve()),timer=useRef(),lastDocument=useRef();latest.current={capture,onError,ready,beforeFlush};
 const flush=()=>{clearTimeout(timer.current);if(!latest.current.ready)return Promise.resolve();const value=latest.current.capture(),document=value.document;if(value.dirty&&document===lastDocument.current)delete value.document;const job=queue.current.then(async()=>{await latest.current.beforeFlush?.();return api('workspace.view',value);}).then(result=>{lastDocument.current=value.dirty?document:undefined;return result;});queue.current=job.catch(()=>{});return job;};
 const schedule=()=>{clearTimeout(timer.current);timer.current=setTimeout(()=>flush().catch(latest.current.onError),1000);};
 useEffect(()=>{if(ready)schedule();return()=>clearTimeout(timer.current);},watch);
 useEffect(()=>{const bridge={flush};window.nexarborWorkspace=bridge;return()=>{clearTimeout(timer.current);if(window.nexarborWorkspace===bridge)delete window.nexarborWorkspace;};},[]);
 return {flush,schedule};
}
