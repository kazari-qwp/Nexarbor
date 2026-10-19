// Browser-compatible request port. No UI, graph state, or provider imports.
export function createEditorClient({token='',endpoint='/api',fetch:send=globalThis.fetch}={}){
 return async function request(operation,params={}){
  const response=await send(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation,params})});
  const result=await response.json();if(!response.ok||result.error)throw new Error(result.error??'请求失败');return result.value;
 };
}
