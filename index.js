import path from 'node:path';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {readCatalog,resolveComponents,ComponentRuntime} from './adapters/harness/framework/components.js';
import * as base from './adapters/harness/framework/foundation.js';
import * as lifecycle from './adapters/harness/framework/agent-lifecycle.js';
const foundation={define(r){base.define(r);lifecycle.define(r)},steps:[...base.steps,...lifecycle.steps]};

export const name='datanet-harness';
export const inject=['agents','sessions','tools','skills','systemPrompt','sessionTitle'];
export async function apply(ctx,config={}){
  const root=path.dirname(fileURLToPath(import.meta.url));
  const profile=JSON.parse(await readFile(path.join(root,'components','profile.json'),'utf8'));
  const catalog=await readCatalog(root),components=new ComponentRuntime(ctx,catalog,resolveComponents(catalog,{...profile,...config.components}));
  const runtime={ctx,config,components,root};
  ctx.provide('datanetComponents',components);
  return components.load(runtime,foundation);
}
