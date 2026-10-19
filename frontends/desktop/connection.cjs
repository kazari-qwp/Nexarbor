const fs=require('node:fs');
function validateAddress(value){
 const url=new URL(value);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||url.username||url.password||url.pathname!=='/'||url.search)throw new Error('工作台仅支持本机连接');
 if(!/^[a-f0-9]{64}$/.test(new URLSearchParams(url.hash.slice(1)).get('token')??''))throw new Error('缺少工作台访问凭据');
 return url.href;
}
function readConnection(file){return validateAddress(JSON.parse(fs.readFileSync(file,'utf8')).url);}
function localNavigation(value){try{const u=new URL(value);return u.protocol==='http:'&&u.hostname==='127.0.0.1'&&!!u.port&&!u.username&&!u.password&&u.pathname==='/';}catch{return false;}}
async function activeConnection(file,{timeout=1500}={}){
 try{
  const address=readConnection(file),url=new URL(address),token=new URLSearchParams(url.hash.slice(1)).get('token');
  const response=await fetch(new URL('/api',url),{method:'POST',headers:{'Content-Type':'application/json','X-Nexarbor-Token':token},body:JSON.stringify({operation:'state',params:{}}),signal:AbortSignal.timeout(timeout)});
  const result=await response.json();return response.ok&&Array.isArray(result.value?.live?.document?.network?.nodes)?address:null;
 }catch{return null;}
}
module.exports={validateAddress,readConnection,localNavigation,activeConnection};
