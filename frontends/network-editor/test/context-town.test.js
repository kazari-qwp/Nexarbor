// Current project declarations are already migrated; opening them never runs a legacy converter.
import {test} from 'node:test';import assert from 'node:assert/strict';
import {readProjectBundle} from '../../../adapt/harness/studio/project.mjs';
const project=new URL('../../../resources/examples/npc-town/',import.meta.url);
test('town context and memory are explicit modules on real agents with independent source documents',async()=>{
 const {fileURLToPath}=await import('node:url'),bundle=await readProjectBundle(fileURLToPath(project)),copy=structuredClone(bundle.document);
 const agents=bundle.document.network.nodes.filter(n=>n.type==='agent');assert.equal(agents.length,7);
 for(const agent of agents){
  const modules=new Map(agent.tables.modules.map(m=>[m.module_id,m]));
  assert.ok(modules.has('agents.memory'));assert.ok(modules.has('context.assembler'));assert.ok(modules.has('tool_discovery'));assert.ok(!modules.has('agents.context'));
  assert.ok(Object.hasOwn(bundle.document.files,agent.data.path));
  assert.ok(agent.execution.prepare.some(p=>p.module==='context.assembler'&&p.node===agent.node_id));
 }
 assert.ok(!bundle.document.network.nodes.some(n=>n.type==='subnode'));assert.deepEqual(bundle.document,copy);
});
test('newborn declarations retain configurable names and references in actual module table bindings',async()=>{
 const {fileURLToPath}=await import('node:url'),bundle=await readProjectBundle(fileURLToPath(project));
 assert.equal(bundle.runtime.templates.length,2);
 for(const t of bundle.runtime.templates){
  assert.ok(t.document.network.nodes.length<=16);assert.ok(t.bindings.some(b=>b.input==='name'));assert.ok(t.bindings.some(b=>b.input==='home'));assert.ok(t.bindings.some(b=>b.input==='/parents/0'));
  const child=t.document.network.nodes.find(n=>n.type==='agent');assert.ok(child.tables.modules.some(m=>m.module_id==='context.assembler'));assert.equal(t.document.files[child.data.path],'');
  assert.ok(t.attachments.every(a=>!a.source.startsWith('context/')));assert.ok(!JSON.stringify(t).includes('agents.context'));
 }
});
