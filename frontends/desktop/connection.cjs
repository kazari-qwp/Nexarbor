const fs=require('node:fs');
function validateAddress(value){
 const url=new URL(value);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||url.username||url.password||url.pathname!=='/'||url.search)throw new Error('工作台仅支持本机连接');
 if(!/^[a-f0-9]{64}$/.test(new URLSearchParams(url.hash.slice(1)).get('token')??''))throw new Error('缺少工作台访问凭据');
 return url.href;
}
function readConnection(file){return validateAddress(JSON.parse(fs.readFileSync(file,'utf8')).url);}
function localNavigation(value){try{const u=new URL(value);return u.protocol==='http:'&&u.hostname==='127.0.0.1'&&!!u.port&&!u.username&&!u.password&&u.pathname==='/';}catch{return false;}}
module.exports={validateAddress,readConnection,localNavigation};
