import {readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

export const CATEGORIES=['tools','skills','network_presets','toolboxes','agent_presets','nodes'];

export async function readCatalog(root){
  const catalog=new Map();
  for(const kind of CATEGORIES){
    let entries;try{entries=await readdir(path.join(root,'components',kind),{withFileTypes:true});}catch(error){if(error.code==='ENOENT')continue;throw error;}
    for(const entry of entries){if(!entry.isDirectory())continue;
      const directory=path.join(root,'components',kind,entry.name),file=path.join(directory,'component.json');
      let manifest;try{manifest=JSON.parse(await readFile(file,'utf8'));}catch(error){if(error.code==='ENOENT')continue;throw error;}
      if(manifest.id!==kind+'/'+entry.name||manifest.kind!==kind)throw new Error('Component identity must match its directory: '+file);
      catalog.set(manifest.id,{...manifest,directory});
    }
  }
  return catalog;
}

export function resolveComponents(catalog,profile={}){
  const enabled=new Set([...catalog].filter(([id,m])=>profile[id]??m.enabled!==false).map(([id])=>id));
  for(const id of Object.keys(profile))if(!catalog.has(id))throw new Error('Unknown component: '+id);
  let changed;do{changed=false;for(const id of [...enabled]){
    const missing=(catalog.get(id).requires??[]).filter(dep=>!enabled.has(dep));
    if(missing.length){enabled.delete(id);changed=true;}
  }}while(changed);
  return enabled;
}

/** A catalog loader using Cordis event dispatch and disposers; no second event bus. */
export class ComponentRuntime {
  constructor(ctx,catalog,enabled){this.ctx=ctx;this.catalog=catalog;this.enabled=enabled;this.disposers=new Map();this.tools=new Map();this.patterns=[];}
  active(id){return !this.closed&&(id==='foundation'||this.enabled.has(id));}
  track(id,dispose){if(typeof dispose==='function'){const list=this.disposers.get(id)??[];list.push(dispose);this.disposers.set(id,list);}return dispose;}
  on(id,scope,event,callback){
    return this.track(id,scope.on(event,(...args)=>this.active(id)?callback(...args):undefined));
  }
  section(id,scope,definition){return this.track(id,scope.systemPrompt.section(definition));}
  guard(id,scope,callback){return this.track(id,scope.tools.guard((...args)=>this.active(id)?callback(...args):undefined));}
  owner(name){return this.tools.get(name)??(name.endsWith('_channel')?this.tools.get(name.slice(0,-8)):undefined)??this.patterns.find(([pattern])=>pattern.test(name))?.[1];}
  allows(name){const owner=this.owner(name);return !!owner&&this.active(owner);}
  async load(r,foundation){
    const modules=[];this.modules=new Map();this.runtime=r;
    for(const [id,m] of this.catalog){
      for(const name of m.tools??[]){if(this.tools.has(name))throw new Error('Duplicate tool owner: '+name);this.tools.set(name,id);}
      for(const pattern of m.toolPatterns??[])this.patterns.push([new RegExp(pattern),id]);
      if(m.entry){const module=await import(pathToFileURL(path.join(m.directory,m.entry)).href);modules.push({id,module});this.modules.set(id,module);module.fallback?.(r);}
    }
    foundation.define(r);
    for(const {id,module} of modules)if(this.active(id))module.define?.(r);
    const steps=foundation.steps.map(step=>({...step,id:'foundation'}));
    for(const {id,module} of modules)if(this.active(id))for(const step of module.steps??[])steps.push({...step,id});
    steps.sort((a,b)=>a.order-b.order);
    for(const step of steps)await step.run(r);
    for(const {id,module} of modules)if(this.active(id))await module.install?.(r);
    this.ctx.effect(()=>()=>this.dispose(),"datanet.components");
    return r;
  }
  async dispose(){
    if(this.closed)return;this.closed=true;
    const pending=[];
    for(const list of this.disposers.values())for(const dispose of [...list].reverse())try{pending.push(dispose())}catch{}
    this.disposers.clear();this.enabled.clear();await Promise.allSettled(pending);
  }
  disable(id){
    if(!this.catalog.has(id))throw new Error('Unknown component: '+id);
    const removed=[];
    const visit=target=>{for(const other of [...this.enabled])if((this.catalog.get(other).requires??[]).includes(target))visit(other);
      if(this.enabled.delete(target)){removed.push(target);for(const dispose of (this.disposers.get(target)??[]).reverse())dispose();this.disposers.delete(target);
      const module=this.modules.get(target);const stopped=module?.uninstall?.(this.runtime);
      if(stopped?.catch)stopped.catch(error=>this.runtime.trace?.({type:'component_uninstall_error',component:target,error:String(error)}));
      module?.fallback?.(this.runtime);
      if(this.runtime.diagnostics)this.runtime.diagnostics.reports=this.runtime.reports;
    }};
    visit(id);return removed;
  }
}
