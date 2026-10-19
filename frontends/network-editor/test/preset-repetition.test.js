import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {storedNetworks} from '../../../adapters/harness/framework/stored-networks.js';import {normalizeHistory} from '../../../adapters/harness/framework/editor-history.js';import {startStudio} from '../../../adapters/harness/studio/host.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
test('preset quantity roundtrips on disk and expands in the core without changing the live graph',async()=>{
 const directory=await fs.mkdtemp(path.join(root,'build/preset-repetition-')),document=JSON.parse(await fs.readFile(path.join(root,'configs/fixed_groups_v3/presets/collaboration.json'),'utf8')),store=storedNetworks(directory);let host;
 try{const stored=await store.save({storageKind:'fragment',document,editor:{name:'测试'}});assert.equal((await store.list({summary:true})).presets[0].repeat_unit_count,3);assert.equal((await store.load(stored.id)).snapshot.repeat_unit_count,3);
 host=await startStudio({directory});const before=await host.request('state',{}),five=await host.request('preset.expand',{snapshot:stored.snapshot,count:5});assert.equal(five.nodes.filter(n=>n.type==='agent').length,5);assert.equal(five.nodes.filter(n=>n.node_id==='board_tasks').length,1);assert.equal(new Set(five.nodes.map(n=>n.node_id)).size,7);assert.equal(new Set(five.nodes.filter(n=>n.type==='agent').map(n=>n.parameters.file_path)).size,5);assert.equal((await host.request('state',{})).live.commit,before.live.commit);
 await assert.rejects(host.request('preset.expand',{snapshot:stored.snapshot,count:1.5}),/整数/);document.network.repeat_unit_count=0;await assert.rejects(store.save({storageKind:'fragment',document,editor:{name:'错误'}}),/无效/);
 }finally{await host?.close();}
});
test('history distinguishes quantity while ignoring new instance and subnode identities',()=>{
 const nodes=[{node_id:'a',type:'node',parameters:{},connections:{interfaces:[]},modules:{},execution:{prepare:[{node:'sub',module:'m',operation:'read'}],tool_sources:['sub']}},{node_id:'sub',type:'subnode',parameters:{parent_id:'a'},connections:{interfaces:[]},modules:{}}],snapshot={nodes,files:{},repeat_unit_count:3,repeat_unit:['a']};
 const original=normalizeHistory({snapshot});const copy=structuredClone(snapshot);copy.nodes[0].node_id='b';copy.nodes[0].execution.prepare[0].node='sub2';copy.nodes[0].execution.tool_sources=['sub2'];copy.nodes[1].node_id='sub2';copy.nodes[1].parameters.parent_id='b';copy.repeat_unit=['b'];assert.equal(original.configKey,normalizeHistory({snapshot:copy}).configKey);copy.repeat_unit_count=4;assert.notEqual(original.configKey,normalizeHistory({snapshot:copy}).configKey);
});

test('a single prototype with a count is a network preset rather than a single-node template',async()=>{
 const {contentType}=await import('../src/resources.js');const snapshot={nodes:[{node_id:'member',type:'node',parameters:{},modules:{},connections:{interfaces:[]}}],files:{},repeat_unit_count:5,repeat_unit:['member']};
 assert.equal(contentType({snapshot}),'network');assert.equal(normalizeHistory({snapshot}).kind,'network');
});
