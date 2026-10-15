const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),nativeRoot='C:/Users/Dried Fish/AppData/Local/Programs/DeepSeek Harness/resources/app.asar/dsh/node_modules/@deepseek-ai';
const native=name=>require(path.join(nativeRoot,name));let seq=0;
(async()=>{
 const {Context}=native('cordis');const ctx=new Context();
 for(const name of ['dsh-system-prompt','dsh-tools','dsh-agent','dsh-jobs-local','dsh-tool-jobs','dsh-shell-env','dsh-subprocess-local','dsh-pwsh-local','dsh-tool-pwsh'])await ctx.plugin(native(name).default??native(name),name==='dsh-pwsh-local'?{pwshPath:'C:/Users/Dried Fish/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'}:{});
 let notices=0;const fiber=ctx.plugin(()=>{}),owner={id:'command-policy-owner',ctx:fiber.ctx,status:'running',inject:()=>notices++,followup:()=>notices++,session:{id:'command-policy-owner',header:{version:4,id:'command-policy-owner',createdAt:0,cwd:root}}};await ctx.agents.register(owner);
 const {create}=await import(pathToFileURL(root+'/extensions/foundation/capabilities/command_execution/harness.js'));
 const policy=create({ctx:owner.ctx,agent:owner});policy.configure({foregroundWaitMs:80,hardLimitMs:5000,cleanupWaitMs:3000});
 const call=(name,args)=>ctx.tools.execute({signal:new AbortController().signal,callId:'call-'+(++seq),name,arguments:args,agent:owner});
 const childCommand=`$child=Start-Process -FilePath 'C:/Users/Dried Fish/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe' -ArgumentList '-NoLogo -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 60"' -WindowStyle Hidden -PassThru;Write-Output "CHILD=$($child.Id)";while($true){Start-Sleep -Milliseconds 20}`;
 const start=Date.now(),reply=await call('pwsh',{command:childCommand,description:'bounded infinite parent and child',timeoutMs:600000});assert.ok(!reply.isError,JSON.stringify(reply));assert.ok(Date.now()-start<2500,'foreground remained blocked');const id=reply.value.jobId;assert.ok(id,JSON.stringify(reply));
 const list=await call('job_list',{});assert.ok(!list.isError);let pid;
 while(Date.now()-start<4000&&!pid){await new Promise(r=>setTimeout(r,50));const text=ctx.jobs.readAt(id,0,owner.id).chunks.map(x=>x.text).join('');pid=/CHILD=(\d+)/.exec(text)?.[1];}
 assert.ok(pid,'child pid was never observed');const output=await call('job_output',{job_id:id});assert.ok(!output.isError);
 await ctx.jobs.wait(id,7000,owner.id);assert.equal(ctx.jobs.get(id,owner.id).status,'killed');
 const probe=await call('pwsh',{command:`if(Get-Process -Id ${pid} -ErrorAction SilentlyContinue){Write-Output 'CHILD_LIVE'}else{Write-Output 'CHILD_GONE'}`,description:'read child liveness'});
 const probeId=probe.value?.jobId;if(probeId)await ctx.jobs.wait(probeId,3000,owner.id);const text=probeId?ctx.jobs.readAt(probeId,0,owner.id).chunks.map(x=>x.text).join(''):probe.content.map(x=>x.text??'').join('');assert.ok(text.includes('CHILD_GONE'),text);
 policy.configure({foregroundWaitMs:80,hardLimitMs:60000,cleanupWaitMs:3000});
 const next=await call('pwsh',{command:'Start-Sleep -Seconds 60',description:'cleanup on task completion'});const nextId=next.value.jobId;const before=notices;owner.status='idle';owner.ctx.emit('agent/status',{agent:owner,status:'idle'});await ctx.jobs.wait(nextId,5000,owner.id);assert.equal(ctx.jobs.get(nextId,owner.id).status,'killed');await new Promise(r=>setTimeout(r,50));assert.equal(notices,before,'cleanup woke completed owner');
 owner.status='running';const manual=await call('pwsh',{command:'Start-Sleep -Seconds 60',description:'manual cancellation'});const kill=await call('job_kill',{job_id:manual.value.jobId});assert.ok(!kill.isError);await ctx.jobs.wait(manual.value.jobId,5000,owner.id);assert.equal(ctx.jobs.get(manual.value.jobId,owner.id).status,'killed');
 await policy.dispose();await ctx.fiber.dispose();console.log('PASS native pwsh: bounded foreground, job list/output/kill, hard limit kills child tree, turn cleanup, no cleanup wakeup');
})().catch(e=>{console.error(e);process.exit(1)});
