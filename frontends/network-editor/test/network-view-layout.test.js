import {fileURLToPath} from 'node:url';
import {readProjectBundle} from '../../../adapt/harness/studio/project.mjs';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import ELK from 'elkjs/lib/elk.bundled.js';
import {placeNetwork} from '../src/network-view-layout.js';
import {planRegions,completeRefs,regionColors} from '../src/network-view-regions.js';
import {NetworkObserver} from '../../../adapt/harness/studio/makers/network-observer.mjs';
const envelope=nodes=>[Math.min(...nodes.map(n=>n.x))-32,Math.min(...nodes.map(n=>n.y))-40,Math.max(...nodes.map(n=>n.x+n.width))+64,Math.max(...nodes.map(n=>n.y+n.height))+80];
function assertClear(nodes){for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j];assert.ok(a.x+a.width+8<=b.x||b.x+b.width+8<=a.x||a.y+a.height+34<=b.y-30||b.y+b.height+34<=a.y-30,'nodes/labels overlap: '+a.ref+' '+b.ref);}}
test('a long chain folds into a compact picture without changing IDs or topology',async()=>{
 const scene={nodes:Array.from({length:30},(_,i)=>({ref:'N'+i,type:'node'})),edges:Array.from({length:29},(_,i)=>({source:'N'+i,target:'N'+(i+1)})),ownership:[]},before=structuredClone(scene);
 const nodes=await placeNetwork(scene,new ELK()),bounds=envelope(nodes);assert.ok(bounds[2]/bounds[3]>.6&&bounds[2]/bounds[3]<2.1);assertClear(nodes);assert.deepEqual(scene,before);assert.equal(new Set(nodes.map(n=>n.ref)).size,30);
});
test('full town is compact and completely covered by useful, differently colored windows',async()=>{
 const snapshot={document:(await readProjectBundle(fileURLToPath(new URL('../../../resources/examples/npc-town/',import.meta.url)))).document},scene=new NetworkObserver(snapshot,'layout-test').view({include_subnodes:true,include_text:true}).scene;
 const nodes=await placeNetwork(scene,new ELK()),bounds=envelope(nodes),plan=planRegions(bounds,{width:1500,height:1250},{nodes});
 assertClear(nodes);assert.ok(bounds[2]/bounds[3]>.6&&bounds[2]/bounds[3]<1.8);assert.ok(plan.regions.length>=2&&plan.regions.length<=4);
 const union=new Set(plan.regions.flatMap(r=>completeRefs(nodes,r.bounds)));assert.equal(union.size,nodes.length);assert.ok(plan.regions.every(r=>r.complete.length>=Math.ceil(nodes.length/5)));
 assert.ok(plan.regions.every(r=>regionColors.includes(r.color)));assert.ok(new Set(plan.regions.map(r=>r.color)).size>1);
 const repeated=plan.regions.reduce((n,r)=>n+r.complete.length,0)-nodes.length;assert.ok(repeated<nodes.length*.4);
 const again=await placeNetwork(scene,new ELK());assert.deepEqual(again,nodes);
});
