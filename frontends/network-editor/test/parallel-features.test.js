import test from 'node:test';import assert from 'node:assert/strict';
import {segmentDistance,hitRenderedEdges} from '../src/edge-picker.js';
import {readProjectBundle} from '../../../adapt/harness/studio/project.mjs';import {fileURLToPath} from 'node:url';
const path=(id,y,zoom=1)=>({dataset:{id},querySelector:()=>({getBoundingClientRect:()=>({left:0,right:100*zoom,top:y-1,bottom:y+1}),getScreenCTM:()=>({a:zoom,b:0,c:0,d:zoom,e:0,f:y}),getTotalLength:()=>100,getPointAtLength:x=>({x,y:0})})});
test('edge hit detection uses screen distances and offers all visible overlapping paths',()=>{
 assert.equal(segmentDistance({x:3,y:4},{x:0,y:0},{x:0,y:0}),5);
 const dom={querySelectorAll:()=>[path('one',10),path('two',10),path('hidden',10),path('far',30)]};
 assert.deepEqual(hitRenderedEdges(dom,{x:50,y:12},new Set(['one','two','far'])),['one','two']);
 assert.deepEqual(hitRenderedEdges({querySelectorAll:()=>[path('zoom',10,2)]},{x:180,y:16},new Set(['zoom'])),['zoom']);
 assert.deepEqual(hitRenderedEdges(dom,{x:200,y:12},new Set(['one','two'])),[]);
});
test('canonical town declares agents on the same signal layer and keeps each module state independent',async()=>{
 const bundle=await readProjectBundle(fileURLToPath(new URL('../../../resources/examples/npc-town/',import.meta.url))),before=structuredClone(bundle.document),nodes=bundle.document.network.nodes;
 const agents=nodes.filter(n=>n.type==='agent'),clock=nodes.find(n=>n.node_id==='世界时间');
 assert.deepEqual(clock.links.filter(e=>e.channels.includes('tick')).map(e=>e.target_id).sort(),agents.map(n=>n.node_id).sort());
 for(const agent of agents){assert.ok(agent.links.some(e=>e.target_id==='存档点'&&e.channels.includes('tick')));assert.ok(agent.tables.modules.some(m=>m.module_id==='agents.activity'));assert.ok(agent.tables.modules.some(m=>m.module_id==='messages.box'));}
 assert.deepEqual(bundle.document,before);assert.ok(bundle.runtime.templates.every(t=>t.attachments.some(a=>a.source==='世界时间')));
});
