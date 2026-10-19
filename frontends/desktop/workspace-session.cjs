const exists=require('node:fs').existsSync;const fs=require('node:fs/promises'),path=require('node:path'),{randomUUID}=require('node:crypto');
class WorkspaceSession{
 constructor(home){this.home=path.resolve(home);this.file=path.join(this.home,'desktop-session.json');this.queue=Promise.resolve();}
 async read(){try{return JSON.parse(await fs.readFile(this.file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;return {version:1,applications:{}};}}
 async remember(spec){const job=this.queue.then(async()=>{await fs.mkdir(path.dirname(this.file),{recursive:true});const value=await this.read();value.last=spec;value.applications??={};if(spec.application)value.applications[spec.application]=spec;const temp=this.file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(value,null,2));await fs.rename(temp,this.file);});this.queue=job.catch(()=>{});return job;}
 async application(id,fallback){const value=await this.read();if(value.applications?.[id])return value.applications[id].directory;const legacy=path.join(this.home,'network_runs',id);if(exists(path.join(legacy,'checkpoints.sqlite3')))return legacy;const existing=path.join(this.home,'.nexarbor/runs',id);try{await fs.access(path.join(existing,'checkpoints.sqlite3'));return existing;}catch{}return fallback??existing;}
}
module.exports={WorkspaceSession};
