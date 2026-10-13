import {mkdir,readFile,writeFile,rename,rm} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const queues=new Map();
export class JsonState {
  constructor(directory,seed={}){this.directory=directory;this.file=path.join(directory,'state.json');this.seed=seed;}
  async read(){try{return JSON.parse(await readFile(this.file,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;return structuredClone(this.seed);}}
  async mutate(fn){const prior=queues.get(this.file)??Promise.resolve();const next=prior.then(async()=>{
    await mkdir(this.directory,{recursive:true});const lock=path.join(this.directory,'.write-lock');await mkdir(lock);let temporary;
    try{const data=await this.read(),value=await fn(data);temporary=path.join(this.directory,randomUUID()+'.tmp');await writeFile(temporary,JSON.stringify(data,null,2),'utf8');await rename(temporary,this.file);return value;}
    finally{if(temporary)await rm(temporary,{force:true});await rm(lock,{recursive:true,force:true});}
  });const tail=next.catch(()=>{});queues.set(this.file,tail);try{return await next;}finally{if(queues.get(this.file)===tail)queues.delete(this.file);}}
}
