// Allow the full supported, finite execution deadline plus cleanup.
const longOperations=new Set(['studio_pulse','executor_run','executor_prepare','executor_invoke','executor_visit']);
export function studioRpcTimeout(method,params={}){
 if(longOperations.has(method))return 86460000;
 if(method==='data_preview'||method==='module_access')return 86460000;
 return 45000;
}
