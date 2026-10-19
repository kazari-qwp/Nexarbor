import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {installApplicationPresets,applications} from '../../../adapters/harness/studio/application-presets.mjs';
import {editorLibrary} from '../../../adapters/harness/framework/editor-library.js';
import {storedNetworks} from '../../../adapters/harness/framework/stored-networks.js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
test('three applications are real full-network files with private copies and runtime requirements, preserved after edits, archive and deletion',async()=>{
 const base=path.join(root,'build/application-presets-tests');await fs.mkdir(base,{recursive:true});const home=await fs.mkdtemp(path.join(base,'run-'));const presets=await installApplicationPresets(home,root);assert.equal(presets.length,3);
 const library=editorLibrary(home);let state=await library('editor.library');assert.equal(state.presets.length,3);
 for(const app of applications){const preset=presets.find(p=>p.application===app.id),source=JSON.parse(await fs.readFile(path.join(root,'configs',app.id,'network.json'),'utf8'));assert.equal(preset.name,app.name);assert.equal(preset.storageKind,'network');assert.equal(state.assets.preset.items[preset.id].folder,'stored-networks');assert.equal(path.dirname(preset.file),path.join(home,'network_presets/networks'));assert.deepEqual(JSON.parse(await fs.readFile(preset.file,'utf8')),source);assert.deepEqual(preset.snapshot.files,source.files);}
 const town=presets.find(p=>p.application==='npc_town_v3');assert.equal(town.runtime.templates.length,2);assert.ok(town.runtime.components.includes('capabilities/template_instantiation'));
 const changed=JSON.parse(await fs.readFile(town.file,'utf8'));changed.network.nodes[0].name='用户改过的存储网络';await fs.writeFile(town.file,JSON.stringify(changed));await library('editor.library.update',{action:'asset.archive',kind:'preset',entries:[{id:town.id}]});const removed=presets.find(p=>p.application==='fixed_groups_v3');await storedNetworks(home).remove(removed.id);
 await installApplicationPresets(home,root);state=await library('editor.library');assert.equal(state.presets.length,2);assert.equal(state.presets.find(p=>p.id===town.id).snapshot.nodes[0].name,'用户改过的存储网络');assert.ok(state.assets.preset.items[town.id].archivedAt);assert.equal(state.bookmarks.length,0);assert.equal(state.history.length,0);
});
