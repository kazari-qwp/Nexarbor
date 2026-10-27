import test from 'node:test';
import assert from 'node:assert/strict';
import ELK from 'elkjs/lib/elk.bundled.js';
import {arrangeGraph} from '../src/layout.js';
import {sourceColor,edgeColors,nodeDimensions} from '../src/graph-appearance.js';
test('dense arrangement balances a long chain, avoids overlap and keeps IDs',async()=>{
 const nodes=Array.from({length:40},(_,i)=>({id:String(i),position:{x:0,y:i*200},...nodeDimensions(i%5===0?'subnode':'node')}));
 const edges=nodes.slice(1).map((n,i)=>({id:'e'+i,source:String(i),target:n.id}));
 const before=structuredClone({nodes,edges}),elk=new ELK();
 const result=await arrangeGraph(nodes,edges,elk,[],{dense:true});
 assert.deepEqual({nodes,edges},before);assert.equal(Object.keys(result).length,40);
 const boxes=nodes.map(n=>({...n,...result[n.id]}));
 const w=Math.max(...boxes.map(n=>n.x+n.width))-Math.min(...boxes.map(n=>n.x)),h=Math.max(...boxes.map(n=>n.y+n.height))-Math.min(...boxes.map(n=>n.y));
 assert.ok(w/h>.6&&w/h<2.1,`aspect=${w/h}`);
 for(let i=0;i<boxes.length;i++)for(const b of boxes.slice(i+1)){const a=boxes[i];assert.ok(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y);}
 assert.deepEqual(await arrangeGraph(nodes,edges,elk,[],{dense:true}),result);
});
test('source colours share a bright stable palette',()=>{
 assert.equal(sourceColor('npc/lin'),sourceColor('npc/lin'));
 assert.ok(edgeColors.includes(sourceColor('npc/lin')));
});
