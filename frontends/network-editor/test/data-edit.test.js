import test from 'node:test';import assert from 'node:assert/strict';import {mergeDataEdit} from '../src/data-edit.js';
test('data replies preserve unrelated edits and refuse changed target configuration or owned files',()=>{
 const node={node_id:'one',parameters:{directory:'data/one'},modules:{}},before={network:{nodes:[node,{node_id:'two',parameters:{}}]},files:{'data/one/page.md':'old','other.md':'before'}},value={beforeNode:structuredClone(node),beforeFiles:structuredClone(before.files),node:structuredClone(node),files:{'data/one/page.md':'new'}};
 const current=structuredClone(before);current.network.nodes[1].name='keep edit';current.files['other.md']='keep text';const result=mergeDataEdit(current,value);assert.equal(result.network.nodes[1].name,'keep edit');assert.equal(result.files['other.md'],'keep text');assert.equal(result.files['data/one/page.md'],'new');assert.equal(before.files['data/one/page.md'],'old');
 current.files['data/one/new.md']='concurrent addition';assert.throws(()=>mergeDataEdit(current,value),/数据已经变化/);delete current.files['data/one/new.md'];current.network.nodes[0].name='changed';assert.throws(()=>mergeDataEdit(current,value),/配置已经变化/);
});
