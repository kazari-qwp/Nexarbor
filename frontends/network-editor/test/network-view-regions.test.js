import test from 'node:test';import assert from 'node:assert/strict';
import {planRegions,visibleRefs} from '../src/network-view-regions.js';
test('small graphs need no second look; detail windows cover the whole diagram with substantial overlap',()=>{
 const size={width:1500,height:1100};assert.equal(planRegions([0,0,900,800],size).regions.length,0);
 for(const bounds of [[-20,-30,4600,2500],[0,0,8000,300],[0,0,300,6500]]){
  const p=planRegions(bounds,size),[x,y,w,h]=bounds;assert.ok(p.regions.length>1);
  assert.equal(p.regions[0].bounds[0],x);assert.equal(p.regions[0].bounds[1],y);
  const last=p.regions.at(-1).bounds;assert.ok(Math.abs(last[0]+last[2]-x-w)<.0001);assert.ok(Math.abs(last[1]+last[3]-y-h)<.0001);
  for(const a of p.regions)for(const b of p.regions){if(a.row===b.row&&b.column===a.column+1)assert.ok((a.bounds[0]+a.bounds[2]-b.bounds[0])/a.bounds[2]>=.2-1e-8);if(a.column===b.column&&b.row===a.row+1)assert.ok((a.bounds[1]+a.bounds[3]-b.bounds[1])/a.bounds[3]>=.2-1e-8);}
 }
 const nodes=[{ref:'N1',x:0,y:0,width:112,height:112},{ref:'N2',x:2000,y:0,width:112,height:112}];assert.deepEqual(visibleRefs(nodes,[0,0,1200,900]),['N1']);
});
