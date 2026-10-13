import {readFile,readdir} from 'node:fs/promises';
import path from 'node:path';

export async function loadToolboxes(directory,overrides={},components){
  const registry={};
  for(const entry of await readdir(directory,{withFileTypes:true})){
    if(!entry.isDirectory())continue;
    const manifest=JSON.parse(await readFile(path.join(directory,entry.name,'component.json'),'utf8'));
    if(!manifest.box)continue;
    const box=JSON.parse(await readFile(path.join(directory,entry.name,manifest.box),'utf8'));
    registry[box.id]={...box,enabled:components.active(manifest.id)};
  }
  Object.assign(registry,overrides);
  Object.defineProperty(registry,'catalog',{value:new Map([...components.catalog.values()].flatMap(m=>Object.entries(m.toolPolicies??{})))});
  Object.defineProperty(registry,'components',{value:components});
  return registry;
}

function validateOptions(options,policy){
  if(!options||typeof options!=='object'||Array.isArray(options))throw new Error('Invalid tool options');
  for(const [key,value] of Object.entries(options)){
    const spec=policy.properties?.[key];if(!spec)throw new Error('Unknown toolbox option: '+key);
    if(spec.type==='array'){
      if(!Array.isArray(value)||value.some(x=>typeof x!=='string'||spec.enum&&!spec.enum.includes(x)))throw new Error('Invalid array option: '+key);
    }else if(typeof value!==spec.type||spec.enum&&!spec.enum.includes(value))throw new Error('Invalid option: '+key);
  }
}

export function resolveToolboxes(registry,names,allowed){
  if(!Array.isArray(names)||new Set(names).size!==names.length)throw new Error('Toolboxes must be unique IDs');
  const framework=new Map(),official=new Set(),skills=new Set(),providers=new Set(),expanded=[],active=new Set(),done=new Set();let allSkills=false;
  function visit(id){
    if(active.has(id))throw new Error('Cyclic toolbox includes: '+id);if(done.has(id))return;
    const box=registry[id];if(!box||box.id!==id)throw new Error('Unknown toolbox: '+id);
    if(box.enabled===false){done.add(id);return;}
    active.add(id);for(const child of box.includes??[])visit(child);active.delete(id);done.add(id);expanded.push(id);
  }
  for(const id of names){if(allowed&&!allowed.includes(id))throw new Error('Toolbox is not granted: '+id);visit(id);}
  for(const id of expanded){const box=registry[id];
    for(const item of box.tools){
      if(item.source==='harness')official.add(item.name);
      else if(item.source==='datanet'){
        if(!registry.components.allows(item.name))continue;
        const options=item.options??{},policy=registry.catalog.get(item.name)??{};validateOptions(options,policy);
        const previous=framework.get(item.name);
        if(previous){
          if(policy.merge){const merged={...previous};for(const [key,method] of Object.entries(policy.merge))merged[key]=method==='max'?Math.max(previous[key]??policy.defaults?.[key]??0,options[key]??policy.defaults?.[key]??0):Boolean(previous[key]||options[key]);framework.set(item.name,merged);}
          else if(JSON.stringify(previous)!==JSON.stringify(options))throw new Error('Conflicting toolbox options: '+item.name);
        }else framework.set(item.name,{...policy.defaults,...options});
      }else throw new Error('Unknown tool source');
    }
    for(const provider of box.skillProviders??[])providers.add(provider);
    if(box.skills==='*')allSkills=true;else for(const skill of box.skills??[])skills.add(skill);
  }
  if((allSkills||skills.size||providers.size)&&!official.has('skill'))throw new Error('Skill grants require official skill loader');
  return {names:[...names],expanded,framework,official:{tools:[...official],skills:allSkills?'*':[...skills],skillProviders:[...providers]}};
}
