// Preserve the state API while transmitting repeated file bodies once.
export const resourceFormat='nexarbor-resource-pool/v1';
const documents=value=>[value.live?.document,value.draft?.document,value.workspace?.document].filter(Boolean);
export function packStateResources(state){
 const resources=[],texts=new Map(),binary=new Map(),ids=new Map();
 const file=value=>{const map=value&&typeof value==='object'?binary:texts,key=value&&typeof value==='object'?value.data:value;if(!map.has(key)){map.set(key,resources.length);resources.push(value);}return map.get(key);};
 for(const document of documents(state))ids.set(document,{...document,files:Object.fromEntries(Object.entries(document.files??{}).map(([name,value])=>[name,file(value)]))});
 const value={...state};for(const key of ['live','draft','workspace'])if(value[key]?.document)value[key]={...value[key],document:ids.get(value[key].document)};
 return {value,resource_format:resourceFormat,resources};
}
export function unpackStateResources(result){
 if(result.resource_format!==resourceFormat)return result.value;
 for(const document of documents(result.value))document.files=Object.fromEntries(Object.entries(document.files).map(([name,index])=>{const value=result.resources[index];return [name,value&&typeof value==='object'?{...value}:value];}));
 return result.value;
}
