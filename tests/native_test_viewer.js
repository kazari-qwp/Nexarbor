// Test-client presentation only. Native logs and Agent lifecycles are untouched.
import {setTimeout as delay} from 'node:timers/promises';
import {readFile} from 'node:fs/promises';
import {registerEditorLauncher} from './editor-launcher.js';
export const inject=['sessionPersistence','sessionProjectionCache','sessionTitle'];
export async function apply(ctx,config){
  if(config.editorConnection)registerEditorLauncher(ctx,async()=>({...JSON.parse(await readFile(config.editorConnection,'utf8')),connection_file:config.editorConnection}));
  const headers=[];
  for(const id of config.sessions){
    const handle=await ctx.sessionPersistence.open(id,'read');
    try{
      const source=await handle.read();
      ctx.sessionProjectionCache.coldSnapshot(handle.header,handle.inheritedEventCount,source.events);
      headers.push(handle.header);
    }finally{await handle.close();}
  }
  for(let attempt=0;attempt<100;attempt++){
    if(headers.every(header=>ctx.sessionProjectionCache.cachedSnapshot(header)?.values.title))break;
    await delay(10);
  }

  for(const header of headers){
    const projection=ctx.sessionProjectionCache.cachedSnapshot(header);
    if(!projection)throw new Error('Native session title cache was not populated');
    const metadata=projection.values.sessionListMetadata;
    // The stock sidebar consumes this stock event; these are derived read hints,
    // never synthetic Session events or changed Agent ownership.
    ctx.emit('api-session/added',{
      sessionId:header.id,updatedAt:Math.max(header.createdAt,metadata?.lastPromptAt??0),
      agentAvailable:false,running:false,blank:metadata?.blank??false,cwd:header.cwd,
      ...(header.origin===undefined?{}:{origin:header.origin}),
      projections:{kind:'cached',asOfSeq:projection.asOfSeq,values:projection.values}
    });
  }

}
