// Generic bridge for component-owned Harness extensions.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
export class ComponentExtensions{
  constructor(agentFor){this.agentFor=agentFor;this.entries=new Map();this.catalog=new Map();}
  configure(entries){this.catalog=new Map(entries.map(entry=>[entry.id,entry]));}
  async invoke(p){
    if(!/^[a-z_]+\/[a-z_]+$/.test(p.component))throw new Error('Invalid component id');
    const key=p.component+':'+p.actor;
    if(!this.entries.has(key)){
      if(p.action==='dispose')return {ok:true};
      const manifest=this.catalog.get(p.component);
      if(!manifest||typeof manifest.harness!=='string')throw new Error('Component has no active Harness extension');
      const directory=manifest.directory;
      const file=path.resolve(directory,manifest.harness),relative=path.relative(directory,file);
      if(relative.startsWith('..')||path.isAbsolute(relative))throw new Error('Extension outside component');
      const {agent}=this.agentFor(p.actor),module=await import(pathToFileURL(file).href);
      this.entries.set(key,module.create({ctx:agent.ctx,agent}));
    }
    const extension=this.entries.get(key);
    if(typeof extension[p.action]!=='function')throw new Error('Unknown component action');
    const result=await extension[p.action](p.arguments??{});
    if(p.action==='dispose')this.entries.delete(key);return result??{ok:true};
  }
}
