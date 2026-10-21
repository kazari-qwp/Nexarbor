// Small atomic edits for owned manifests and runtime metadata; no application rules.
const own=(value,key)=>value!==null&&typeof value==='object'&&Object.hasOwn(value,key);
function pointer(value){
 if(typeof value!=='string'||value!==''&&!value.startsWith('/'))throw Error('JSON 路径使用空字符串或 / 开头的指针');
 if(/~(?![01])/u.test(value))throw Error('JSON 路径仅接受 ~0 与 ~1 转义');
 return value===''?[]:value.slice(1).split('/').map(part=>part.replaceAll('~1','/').replaceAll('~0','~'));
}
function index(value,size,append=false){if(value==='-'&&append)return size;if(!/^(0|[1-9][0-9]*)$/.test(value))throw Error('JSON 数组需要非负整数索引');const i=Number(value);if(!Number.isSafeInteger(i)||i>size||i===size&&!append)throw Error('JSON 数组索引越界');return i;}
function locate(root,parts){let value=root;for(const key of parts){if(Array.isArray(value))value=value[index(key,value.length)];else{if(!own(value,key))throw Error('JSON 路径不存在：'+key);value=value[key];}}return value;}
export function editJson(source,operations){
 if(!Array.isArray(operations)||!operations.length||operations.length>200)throw Error('JSON 编辑需要 1–200 条操作');
 let document=structuredClone(source);
 for(const operation of operations){
  if(!operation||typeof operation!=='object'||Array.isArray(operation)||!['set','remove','copy'].includes(operation.op))throw Error('JSON 操作必须是 set、remove 或 copy');
  const keys=operation.op==='set'?['op','path','value']:operation.op==='copy'?['op','path','from']:['op','path'];
  if(keys.some(k=>!Object.hasOwn(operation,k))||Object.keys(operation).some(k=>!keys.includes(k)))throw Error('JSON 操作字段不匹配：'+keys.join(', '));
  const parts=pointer(operation.path),value=operation.op==='copy'?structuredClone(locate(document,pointer(operation.from))):structuredClone(operation.value);
  if(!parts.length){if(operation.op==='remove')throw Error('不能删除 JSON 根');document=value;continue;}
  const key=parts.pop(),parent=locate(document,parts);
  if(Array.isArray(parent)){const i=index(key,parent.length,operation.op!=='remove');if(operation.op==='remove')parent.splice(i,1);else parent[i]=value;}
  else{if(parent===null||typeof parent!=='object')throw Error('JSON 父路径必须是对象或数组');if(operation.op==='remove'){if(!own(parent,key))throw Error('待删除的 JSON 路径不存在');delete parent[key];}else Object.defineProperty(parent,key,{value,writable:true,configurable:true,enumerable:true});}
 }
 return document;
}
