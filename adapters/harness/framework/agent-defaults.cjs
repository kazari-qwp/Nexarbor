const fs=require('node:fs'),path=require('node:path');
module.exports=function readAgentDefaults(root=path.resolve(__dirname,'../../..')){
 const file=path.join(root,'configs/agent-defaults.json'),value=JSON.parse(fs.readFileSync(file,'utf8'));
 for(const key of ['context_window','max_tokens'])if(!Number.isSafeInteger(value[key])||value[key]<1)throw Error('configs/agent-defaults.json: '+key+' must be a positive integer');
 return {context_window:value.context_window,max_tokens:value.max_tokens};
};
