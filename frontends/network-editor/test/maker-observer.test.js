import {fileURLToPath} from 'node:url';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';
import {makerTools} from '../../../adapt/harness/studio/makers/tools.mjs';
test('global makers observe candidate/current/environment without an extra authorization switch',async t=>{
 let callback,created;const calls=[];const runner={start:async()=>({ready:true}),close:async()=>{},request:async(method,p)=>{if(method==='create'){created=p;return {session_id:'local-maker'};}if(method==='run'){
 const call=(tool,args)=>callback('maker-tool',{task:created.task,tool,arguments:args});
 const first=await call('view_network',{image:false,source:'candidate'});assert.equal(first.counts.total_nodes,1);const ref=first.nodes[0].ref;
 assert.equal((await call('inspect_nodes',{nodes:[ref]})).nodes.length,1);
 assert.equal((await call('view_network',{image:false,source:'current'})).counts.total_nodes,1);
 calls.push('candidate','stable-index','authorization');return {status:'completed',messages:[],events:[]};}if(method==='cancel')return {};
 }};
 const directory=await fs.mkdtemp(path.resolve(fileURLToPath(new URL('../../../build/',import.meta.url)),'observe-maker-')),host=await startStudio({directory,applicationPresets:[],makerRunnerFactory:async(_p,cb)=>{callback=cb;return runner;}});t.after(()=>host.close());
 const work=await host.request('studio.create',{kind:'network',sample:'blank',name:'观察测试'});
 await host.request('studio.copy_current',{id:work.id});
 await host.request('studio.save',{id:work.id,file:'tests/test_observed_graph.py',expected:'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',content:'import unittest\nfrom app.studio.network_testing import NetworkHarness\n\nclass ObservedGraphTest(unittest.IsolatedAsyncioTestCase):\n    async def test_current_graph_is_copied(self):\n        h = NetworkHarness()\n        try:\n            self.assertIsNotNone(h.network.get("root"))\n            self.assertEqual(len(h.network), 1)\n        finally:\n            await h.close()\n'});
 let result=await host.request('studio.agent.start',{id:work.id,requirement:'仅用于离线观察测试',allow_network_testing:false,auto_publish:false,timeout:30});
 for(let i=0;i<120&&result.status==='running';i++){await new Promise(r=>setTimeout(r,100));result=await host.request('studio.agent.read',{task:result.id});}
 assert.equal(result.status,'completed',JSON.stringify(result));assert.deepEqual(calls,['candidate','stable-index','authorization','candidate','stable-index','authorization']);assert.ok(result.passes.some(pass=>pass.kind==='self-review'));
 const current=await host.rpc('studio_observe',{id:work.id,source:'current'});assert.equal(current.network.nodes.length,1);
 await host.rpc('studio_environment',{id:work.id,action:'reset',source:'candidate'});const environment=await host.rpc('studio_observe',{id:work.id,source:'environment'});assert.equal(environment.network.nodes.length,1);
 assert.ok(makerTools('network').some(t=>t.name==='view_network'));assert.ok(makerTools('module',false,true).some(t=>t.name==='read_resource'));assert.ok(!makerTools('module').some(t=>t.name==='view_network'));
 });

test('concurrent maker reads pin one snapshot and keep the explicitly chosen source',async()=>{
 const {MakerManager}=await import('../../../adapt/harness/studio/makers/manager.mjs');let reads=0;
 const make=id=>({network:{nodes:[{node_id:id,name:id,type:'node',tables:{modules:[]},links:[]}]},files:{}});
 const manager=new MakerManager('unused',async(method,p)=>{if(method==='studio_observe'){reads++;await new Promise(r=>setTimeout(r,10));return make(p.source);}if(method==='studio_catalog')return {library:{}};return {};});
 const job={id:'x',workspace:'w',status:'running',kind:'network',allow_network_testing:true,allow_component_creation:false,hidden_modules:[],tool_events:[]};manager.jobs.set('x',job);
 await manager.observe(job,'view_network',{source:'current',image:false});
 const [a,b]=await Promise.all([manager.observe(job,'inspect_nodes',{nodes:['N1'],section:'summary'}),manager.observe(job,'view_network',{image:false})]);
 assert.equal(a.nodes[0].id,'current');assert.equal(b.source,'current');assert.equal(reads,1);
 await manager.tool({task:'x',tool:'write_file',arguments:{path:'network.json',content:'{}'}});
 const again=await manager.observe(job,'view_network',{image:false});assert.equal(again.source,'current');assert.equal(reads,2);
 manager.renderer.close();
});
