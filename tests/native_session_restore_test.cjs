const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),nativeRoot='C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules/@deepseek-ai';
const native=name=>require(path.join(nativeRoot,name));
(async()=>{
 const {Context}=native('cordis'),session=native('dsh-session'),persistence=native('dsh-session-persistence-jsonl');
 const {installSessionEventPersistence,durableEvent}=await import(pathToFileURL(root+'/adapters/harness/runtime/session-events.js'));
 const dir=await fs.mkdtemp(path.join(root,'build/session-restore-'));
 const make=async()=>{const ctx=new Context();await ctx.plugin(persistence.default,{root:dir,compression:'zstd'});return ctx};
 const ctx=await make();installSessionEventPersistence(ctx);installSessionEventPersistence(ctx);
 const id=session.SessionId('restore-probe'),header=session.Session.create(id).header;
 const events=[{type:'datanet/request-tail',seq:0,time:1,data:{turn:1,step:1,messages:[{role:'user',content:[{type:'text',text:'tail snapshot'}]}]}},{type:'datanet/request-recovery',seq:1,time:2,data:{attempt:1,maxCorrections:2}}];
 const handle=await ctx.sessionPersistence.create(header);await handle.append(events);await handle.flush();await handle.close();await ctx.fiber.dispose();
 const reopened=await make(),read=await reopened.sessionPersistence.open(id,'read');const result=await read.read();
 assert.equal(result.events.length,2);for(let i=0;i<2;i++)assert.deepEqual(result.events[i],{...events[i],ignorable:true});
 assert.equal(session.Session.create(id,result.events,header).deriveMessages().length,0);
 assert.equal(durableEvent({type:'some-other-extension',data:{}}).ignorable,undefined);
 assert.equal(events[0].ignorable,undefined);
 await read.close();await reopened.fiber.dispose();console.log('PASS native compressed persistence: close/reopen, two opaque events retained, no derived messages, immutable input, strict other-event handling');
})().catch(e=>{console.error(e);process.exit(1)});
