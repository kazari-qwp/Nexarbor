import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {readProjectBundle} from '../../../adapt/harness/studio/project.mjs';
import {editorLibrary} from '../../../adapt/harness/framework/editor-library.js';
import {storedNetworks} from '../../../adapt/harness/framework/stored-networks.js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
test('published applications are portable project bundles; explicit saved copies preserve runtime, edits, archive and deletion',async()=>{
 const home=await fs.mkdtemp(path.join(root,'build/application-projects-')),store=storedNetworks(home),presets=[];
 for(const name of ['应用1-讨论协作-初始','应用2-资料库-初始','应用3-NPC小镇-初始']){
  const bundle=await readProjectBundle(path.join(root,'项目演示',name));assert.ok(bundle.document.network.nodes.length);assert.ok(bundle.runtime);const preset=await store.save({storageKind:'network',document:bundle.document,editor:{name,runtime:bundle.runtime,positions:bundle.layout??{},display_folder:'stored-networks'}});presets.push(preset);assert.deepEqual(JSON.parse(await fs.readFile(preset.file,'utf8')),bundle.document);assert.equal(path.dirname(preset.file),path.join(home,'network_presets/networks'));
 }
 const library=editorLibrary(home);let state=await library('editor.library');assert.equal(state.presets.length,3);const changed=presets[0];const document=JSON.parse(await fs.readFile(changed.file,'utf8'));document.network.nodes[0].name='用户改过的副本';await fs.writeFile(changed.file,JSON.stringify(document));await library('editor.library.update',{action:'asset.archive',kind:'preset',entries:[{id:changed.id}]});await store.remove(presets[1].id);
 state=await editorLibrary(home)('editor.library');assert.equal(state.presets.length,2);assert.equal(state.presets.find(p=>p.id===changed.id).snapshot.nodes[0].name,'用户改过的副本');assert.ok(state.assets.preset.items[changed.id].archivedAt);assert.equal(state.bookmarks.length,0);assert.equal(state.history.length,0);assert.notEqual((await readProjectBundle(path.join(root,'项目演示/应用1-讨论协作-初始'))).document.network.nodes[0].name,'用户改过的副本');
});
