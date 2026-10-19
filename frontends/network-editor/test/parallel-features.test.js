import test from 'node:test';import assert from 'node:assert/strict';
import {segmentDistance,hitRenderedEdges} from '../src/edge-picker.js';
import {parallelTownDocument,parallelTownTemplates} from '../../../adapters/harness/studio/town-layout.mjs';
const path=(id,y,zoom=1)=>({dataset:{id},querySelector:()=>({getBoundingClientRect:()=>({left:0,right:100*zoom,top:y-1,bottom:y+1}),getScreenCTM:()=>({a:zoom,b:0,c:0,d:zoom,e:0,f:y}),getTotalLength:()=>100,getPointAtLength:x=>({x,y:0})})});
test('edge hit detection uses screen distances and offers all visible overlapping paths',()=>{
 assert.equal(segmentDistance({x:3,y:4},{x:0,y:0},{x:0,y:0}),5);
 const dom={querySelectorAll:()=>[path('one',10),path('two',10),path('hidden',10),path('far',30)]};
 assert.deepEqual(hitRenderedEdges(dom,{x:50,y:12},new Set(['one','two','far'])),['one','two']);
 assert.deepEqual(hitRenderedEdges({querySelectorAll:()=>[path('zoom',10,2)]},{x:180,y:16},new Set(['zoom'])),['zoom']);
 assert.deepEqual(hitRenderedEdges(dom,{x:200,y:12},new Set(['one','two'])),[]);
});
const edge=target=>({target_node_id:target,metadata:{channels:['tick'],threshold:1,multiplier:1,attributes:{}}});
const node=(id,targets,modules={})=>({node_id:id,name:id==='world/settle'?'活动汇合':id,modules,offered_tools:[],connections:{interfaces:targets.map(edge)}});
test('known sample update preserves local state, custom content and external channels, and is idempotent',()=>{
 const activity={'agents.activity':{state:{activities:[{key:'old'}]}},'messages.box':{config:{send_cost:1},state:{messages:[{text:'保留'}]},access:{channels:['chat']}}};
 const source={network:{nodes:[node('world/time',['npc/a']),node('npc/a',['npc/b'],structuredClone(activity)),node('npc/b',['world/settle'],structuredClone(activity)),node('world/settle',['world/save']),node('world/save',['world/pulse'])]},files:{'memory.md':'保留记忆'}};
 const {document,changed}=parallelTownDocument(source);assert.equal(changed,true);assert.equal(source.network.nodes.length,5);assert.equal(document.network.nodes.length,4);assert.deepEqual(document.files,source.files);
 assert.deepEqual(document.network.nodes[0].connections.interfaces.map(e=>e.target_node_id),['npc/a','npc/b']);assert.deepEqual(document.network.nodes[1].modules['messages.box'].state,{messages:[{text:'保留'}]});assert.ok(document.network.nodes[1].modules['messages.box'].access.channels.includes('activity'));assert.equal(parallelTownDocument(document).changed,false);
 source.network.nodes[3].modules.custom={state:{value:1}};assert.equal(parallelTownDocument(source).changed,false);
 const templates=parallelTownTemplates([{document:{network:{nodes:[node('child',['world/settle'],activity)]}},attachments:[{source:'npc/lu',metadata:{channels:['tick']}}]}]);assert.equal(templates[0].document.network.nodes[0].connections.interfaces[0].target_node_id,'world/save');assert.equal(templates[0].attachments[0].source,'world/time');
});
