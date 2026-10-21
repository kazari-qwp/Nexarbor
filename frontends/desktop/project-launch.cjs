const fs=require('node:fs/promises'),path=require('node:path');
async function requireProject(directory){
 const file=path.join(directory,'nexarbor.json');let value;
 try{value=JSON.parse(await fs.readFile(file,'utf8'));}catch(error){if(error.code==='ENOENT')throw Error('找不到项目文件 nexarbor.json');if(error instanceof SyntaxError)throw Error('项目文件 nexarbor.json 格式损坏');throw error;}
 if(value?.format!=='nexarbor-project/v1'||!value.resources||typeof value.resources!=='object'||!value.networks||typeof value.networks!=='object')throw Error('项目文件 nexarbor.json 格式不正确');
 return value;
}
function briefReason(error){
 const message=String(error?.message??error??'项目无法读取');
 if(/Harness.*缺少原生服务|dsh-working-directory/.test(message))return 'Harness 版本不兼容，请在“设置 → DeepSeek Harness 路径”选择 0.2.1 或兼容版本';
 if(/runtime\.lock|could not be acquired/i.test(message))return '项目正被其他进程使用，暂时无法打开';
 if(/ECONNREFUSED|ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|ERR_CONNECTION_CLOSED/i.test(message))return '工作台连接已经失效';
 if(/ENOENT|FileNotFoundError|No such file|cannot find|找不到|不存在/i.test(message))return /nexarbor\.json/.test(message)?'找不到项目文件 nexarbor.json':'项目所需的文件或运行环境不存在';
 if(/项目模块读取失败|SyntaxError|IndentationError/.test(message))return '项目内的模块文件损坏或代码格式错误';
 if(/ModuleNotFoundError|No module named/.test(message))return '运行环境缺少所需依赖';
 if(/DatabaseError|disk image is malformed|not a database/i.test(message))return '项目运行记录损坏，无法读取';
 if(/JSONDecodeError|in JSON|JSON at position|not valid JSON|Unexpected token|Unexpected end|格式损坏/i.test(message))return '项目文件格式损坏，无法读取';
 if(/EISDIR|ENOTDIR/i.test(message))return '项目文件的路径不正确';
 if(/EACCES|EPERM|PermissionError|access.*denied/i.test(message))return '没有权限读取项目文件';
 if(/additional properties|Failed validating|ValidationError/i.test(message))return '网络配置不符合组件要求';
 const lines=message.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);let reason=lines.at(-1)??'项目无法读取';
 reason=reason.replace(/^(?:[\w.]*Error|Exception):\s*/,'').replace(/https?:\/\/\S+/g,'工作台地址');return reason.length>140?reason.slice(0,137)+'…':reason;
}
module.exports={requireProject,briefReason};
