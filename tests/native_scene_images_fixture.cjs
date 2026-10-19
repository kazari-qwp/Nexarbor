// 原生工具图片进入下一次模型请求，并随日志前缀保存；使用本地模型替身，不调用 API。
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const keep=setInterval(()=>{},1000);setTimeout(()=>process.exit(2),25000).unref();
(async()=>{
 const [directory,input]=process.argv.slice(2),root=path.resolve(__dirname,'..'),loader=await require('../adapters/harness/studio/runtime/loader.cjs')(),{native}=loader,{Context}=native('cordis'),host=new Context(),output=require('../adapters/harness/studio/runtime/tool-content.cjs');
 for(const [name,service]of [['dsh-llm','LlmRuntime'],['dsh-session','SessionStore'],['dsh-session-projection','SessionProjectionRegistry'],['dsh-system-prompt','SystemPrompt'],['dsh-tools','ToolRuntime'],['dsh-agent','AgentRegistry']])await host.plugin(native(name)[service]??native(name).default);
 await host.plugin(native('dsh-attachment-local').LocalAttachmentStore,{dshHome:directory});
 const persistence=native('dsh-session-persistence-jsonl');await host.plugin(persistence.default??persistence,{root:path.join(directory,'native-logs')});
 await host.plugin((await loader.load(root+'/adapters/harness/runtime/agent-loop/lib/index.js')).default,{agents:[]});
 const llm=native('dsh-llm'),raw=JSON.parse(await fs.readFile(input,'utf8'));
 class Model extends llm.LlmAdapter{
  requests=[];async resolveModel(provider,id){return {provider,id,name:id,inputModalities:['text','image']};}
  async *stream(options){this.requests.push(options);const block=this.requests.length===1?{type:'tool-call',id:'map-call',name:'query_map',arguments:'{}'}:{type:'text',text:'已收到地图图片。'};yield {type:'block-start',index:0,blockType:block.type};if(block.type==='text')yield {type:'text-delta',index:0,text:block.text};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};}
 }
 const model=new Model();host.llm.registerAdapter(['mock'],model);
 const agent=await host.agentLoop.create(native('dsh-session').SessionId('scene-map-fixture'),{provider:'mock',model:'vision'},{cwd:directory});
 agent.ctx.tools.register({name:'query_map',description:'查询地图',parameters:{type:'object',properties:{}},output:{schema:{},render:output.render},execute:()=>output.prepare({host,native},raw)});
 agent.followup(llm.createUserMessage({source:{kind:'user'},content:[{type:'text',text:'查询地图'}]}));await agent.whenIdle();
 assert.equal(model.requests.length,2);
 const image=model.requests[1].messages.flatMap(m=>m.content??[]).find(b=>b.type==='image');assert.ok(image?.attachment?.attachmentId);
 assert.ok(!JSON.stringify(model.requests[1].messages).includes(raw.content[1].data));
 const previews=await output.previews({host,native},agent.session.deriveMessages());assert.match(previews[image.attachment.attachmentId],/^data:image\/png;base64,/);
 assert.deepEqual(output.render({}, {plain:'ordinary'}),[{type:'text',text:'{"plain":"ordinary"}'}]);
 await assert.rejects(output.prepare({host,native},{format:raw.format,content:[{type:'image',mediaType:'image/svg+xml',data:'AAAA'}]}),/格式/);
 await host.sessions.flush(agent.session);
 const {NativePositions}=await loader.load(root+'/adapters/harness/framework/checkpoints.js'),positions=new NativePositions(host),cursor=await positions.capture(agent.session),prefix=await require('../adapters/harness/studio/makers/portable-images.cjs').exportImages({host,native},await positions.exportPrefix(cursor));
 assert.equal(prefix.images.length,1);await fs.writeFile(path.join(directory,'image-prefix.json'),JSON.stringify(prefix));
 await host.fiber.dispose();clearInterval(keep);console.log(JSON.stringify({passed:true,paidCalls:0,session:cursor.session_id,modelReceivedImage:true}));
})().catch(error=>{console.error(error);process.exit(1)});
