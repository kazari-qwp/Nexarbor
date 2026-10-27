// Actual Electron frontend screenshot used by the production view_network tool.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {readProjectSnapshot} from '../adapt/harness/studio/makers/project-observer.mjs';
import {NetworkObserver} from '../adapt/harness/studio/makers/network-observer.mjs';
import {NetworkRenderer} from '../adapt/harness/studio/makers/network-renderer.mjs';
const directory=path.resolve(process.argv[2]);await fs.mkdir(directory,{recursive:true});
const snapshot=await readProjectSnapshot(path.resolve('resources/examples/npc-town'));
const observer=new NetworkObserver(snapshot,'actual-town-renderer'),renderer=new NetworkRenderer(directory);
try{
 const response=await observer.execute('view_network',{types:['agent','pulse'],image:true,show_channels:true},scene=>renderer.render(scene));
 assert.equal(response.format,'nexarbor-tool-content/v1');const content=response.content.find(item=>item.type==='image');assert.ok(content);
 const bytes=Buffer.from(content.data,'base64');assert.equal(bytes.subarray(1,4).toString(),'PNG');assert.ok(bytes.length>10000);
 const image=path.join(directory,'actual-town-network.png');await fs.writeFile(image,bytes);
 const metadata=JSON.parse(response.content.find(item=>item.type==='text').text);assert.ok(metadata.counts.shown_nodes>1);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({status:'passed',bytes:bytes.length,image,metadata,paid_requests:0},null,2));
 console.log(JSON.stringify({status:'passed',bytes:bytes.length,image,counts:metadata.counts,paid_requests:0}));
}finally{renderer.close();}
