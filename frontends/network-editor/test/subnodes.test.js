import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {editorNode} from '../../../adapt/harness/framework/editor-nodes.js';
import {edgesOf,layoutNodes,filterGraph} from '../src/model.js';
import {projectModules,moduleViewId,moduleConnection} from '../src/module-projection.js';
import {copySubnet,pasteSubnet} from '../src/subnets.js';
const manifest=JSON.parse(await fs.readFile(new URL('../../../modules/context_assembler/module.json',import.meta.url),'utf8'));
const catalog={modules:{'context.assembler':{label:'上下文组装器',frontend:manifest.frontend,schema:manifest.config_schema}}};
function fixture(){
 const owner=editorNode('agent','owner','居民'),document=editorNode('node','document','规则');
 owner.tables.modules=[{module_id:'context.assembler',channels:['system','docs'],strength:2,config:{channels:['relay'],system_prompt_channels:['system'],context_channels:['docs'],inputs_channels:[],tail_channels:['clock']},state:{value:'preserved'}}];
 owner.links=[{target_id:'document',channels:['system'],threshold:1,processor:{type:'multiplier',factor:1},attributes:{}}];
 return {network:{nodes:[owner,document]},files:{[owner.data.path]:'# memory'}};
}
const scene=doc=>projectModules(doc,catalog,{},layoutNodes(doc),edgesOf(doc));
test('module subnodes are derived presentation and never change runtime records',()=>{
 const doc=fixture(),before=structuredClone(doc),view=scene(doc),card=view.nodes.find(n=>n.data.host);
 assert.equal(view.nodes.length,3);assert.equal(doc.network.nodes.length,2);assert.deepEqual(doc,before);
 assert.equal(card.id,moduleViewId('owner','context.assembler'));assert.equal(card.data.host.node_id,'owner');
 assert.equal(view.edges.find(e=>!e.ownership).source,card.id);assert.equal(doc.network.nodes[0].links[0].target_id,'document');
 assert.equal(view.edges.filter(e=>e.ownership).length,1);
});
test('each channel group reads the actual module configuration',()=>{
 const doc=fixture();doc.network.nodes[0].tables.modules[0].config.system_prompt_channels=['new-system'];
 const card=scene(doc).nodes.find(n=>n.data.host);
 assert.deepEqual(card.data.channelGroups.find(g=>g.label==='系统提示').channels,['new-system']);
 assert.equal(card.data.channelGroups.length,5);
});
test('connections and local view resolve module cards to their real host',()=>{
 const doc=fixture(),view=scene(doc),id=moduleViewId('owner','context.assembler');
 const edge=moduleConnection({source:id,target:'document',sourceHandle:'系统提示'},view.nodes);
 assert.equal(edge.source,'owner');assert.equal(edge.target,'document');assert.deepEqual(edge.channels,['system']);
 const filtered=filterGraph(view.nodes,view.edges,{local:{actor:'owner',reachable:{system:[{id:'owner'},{id:'document'}]}}});
 assert.equal(filtered.nodes.length,3);
});
test('copying a host preserves its module and generates a fresh display identity',async()=>{
 const doc=fixture(),snapshot=copySubnet(doc,['owner'],'external');assert.equal(snapshot.nodes.length,1);
 const pasted=await pasteSubnet(doc,{snapshot},{x:500,y:300});const owner=pasted.document.network.nodes.at(-1);
 assert.notEqual(owner.node_id,'owner');assert.equal(owner.tables.modules[0].state.value,'preserved');
 assert.notEqual(moduleViewId(owner.node_id,'context.assembler'),moduleViewId('owner','context.assembler'));
 assert.ok(pasted.document.network.nodes.every(n=>n.type!=='module_view'&&n.type!=='subnode'));
});
